"""Native fault recovery probe. Reconcile a COPY of history; never replay intent."""
import asyncio
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import time
from blockwire.agent import SessionStore
from blockwire.bcl import default_commands
from blockwire.bcl.client import BCLClient
from blockwire.bcl.gateway import BCLGateway,server_tls
from blockwire.project_agent import ProjectAgent
from blockwire.projects import ProjectJournal
from blockwire.recipes import item_counts
from .snapshots import validate,restore,capture
from .fixture import NAME,title,load,close
from .reference import House,verify
from .anvil import voxels
from .live import GOAL

async def recover(player,args):
    private=Path(args.private);root=private.parent
    if not args.from_run or not args.from_run.replace('-','').isalnum():raise ValueError('Explicit simple prior probe ID required')
    old=root/args.from_run;original=json.loads((old/'result.json').read_text())
    if original['metadata'].get('fault')!='lost-ack' or not original.get('fault_probe_passed'):raise ValueError('Verified lost-ack probe required')
    identity={'agent_id':'building-benchmark','world_id':original['metadata']['snapshot_identity'],
              'player_id':json.loads((old/'initial.json').read_text())['scene']['player_uuid']}
    lease=SessionStore(private/'fixture-lease.sqlite',{'agent_id':'benchmark-fixture','world_id':identity['world_id'],'player_id':identity['player_id']})
    lease.acquire()
    try:return await _recover(player,args,old,original,identity)
    finally:lease.release()

async def _recover(player,args,old,original,identity):
    if not args.run_id.replace('-','').isalnum():raise ValueError('Simple unique run ID required')
    out=Path(args.private).parent/args.run_id;out.mkdir(mode=0o700,exist_ok=False)
    original_hash=hashlib.sha256((old/'project.sqlite').read_bytes()).hexdigest()
    restore(old/'ended-world',Path(args.saves)/NAME,out/'previous-closed-world',lambda:title(player))
    scene=load(player);shutil.copy2(old/'project.sqlite',out/'project.sqlite')
    reg=default_commands();token=secrets.token_urlsafe(48)
    cert=Path('build/bcl-verification/private/gateway.pem');key=Path('build/bcl-verification/private/gateway-key.pem')
    gateway=BCLGateway(player,token,out/'gateway-state',registry=reg)
    server=await gateway.listen('127.0.0.1',0,server_tls(cert,key));url=f'wss://127.0.0.1:{server.sockets[0].getsockname()[1]}/v1'
    record={'scope':'Fault recovery/idempotence only, NOT whole-building success','from_run':args.from_run,'exchanges':[]}
    try:
        with ProjectJournal(out/'project.sqlite',identity,args.from_run,GOAL,policy='blocks_v1') as journal:
            pending=journal.p['pending'];assert pending,'Expected durable unacknowledged intent'
            old_actor=journal.p['binding']['actor_session'];journal.bind(scene,allow_rebind=True)
            record.update(pending_retained_before_rebind=pending,actor_replaced=scene['actor_session']!=old_actor,
                          pending_cleared_without_replay=journal.p['pending'] is None)
            async with BCLClient(url,token,cert,session_id=args.run_id,agent_id=identity['agent_id'],world_id=identity['world_id'],player_uuid=scene['player_uuid'],actor_session=scene['actor_session'],timeout=60.) as client:
                agent=ProjectAgent(client,journal,None,reg,duration=120.,audit=record['exchanges'].append);agent.deadline=time.monotonic()+120.
                await agent.exchange('S0 sync\nS1 absolute\nV2 X0.5 Y-59.0 Z0.5\nV0\nI0')
                # A new explicit request, only AFTER the native visible target is
                # freshly correct. No old program/request/task is resubmitted.
                assert journal.p['progress']['0,-60,0']['status']=='correct'
                before=item_counts(player.inventory())
                response=await agent.exchange('I4 Bminecraft:cobblestone P"[0,-60,0]"',intent=True)
                after=item_counts(player.inventory())
                ops=response.get('result',{}).get('operations',[])
                record.update(inventory_before=before,inventory_after=after,
                    idempotent_result=ops,inventory_unchanged=before==after,
                    no_placement=bool(ops and all(o.get('reason')=='desired_block_already_observed' for o in ops)),
                    original_journal_unchanged=hashlib.sha256((old/'project.sqlite').read_bytes()).hexdigest()==original_hash)
                record['passed']=all(record[k] for k in ('actor_replaced','pending_cleared_without_replay','inventory_unchanged','no_placement','original_journal_unchanged'))
    finally:
        server.close();await server.wait_closed();await gateway.aclose()
        if gateway.failed:raise RuntimeError('Quarantined worker: no snapshot claim')
        if player.observe().get('actor_session')!=scene['actor_session']:raise RuntimeError('Actor replaced during probe')
        close(player)
        (out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    capture(Path(args.saves)/NAME,out/'ended-world',lambda:title(player))
    # Structural goal remains incomplete; this must NOT count as a house success.
    h=House();record['structural_verification']=verify(h,voxels(out/'ended-world',h.workspace()|h.floors()),native={})
    (out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    return record
