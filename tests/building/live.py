"""Opt-in actual native/TLS runs; no simulated success substitution."""
import asyncio
import json
import hashlib
import os
from pathlib import Path
import secrets
import shutil
import time

from blockwire.bcl import default_commands
from blockwire.bcl.client import BCLClient
from blockwire.bcl.gateway import BCLGateway,server_tls
from blockwire.project_agent import ProjectAgent
from blockwire.projects import ProjectJournal
from blockwire.recipes import item_counts
from blockwire.skills.approaching import _reachable
from .reference import House,verify
from .program import frames
from .snapshots import restore,capture,validate
from .fixture import NAME,INVENTORY,START,title,load,close
from .anvil import voxels
from .evidence import write_json

FIXTURES=Path(__file__).parent/'fixtures'
GOAL=('Build a 5 by 5 OUTER footprint cobblestone house at origin (0,-60,0): '
      'walls on Y=-60,-59,-58, full flat 5x5 roof at Y=-57; exactly one north-centre '
      'entrance at X=2,Z=0, empty at Y=-60 and -59, with a solid lintel at Y=-58. '
      'All 3x3 interior cells must be empty through all three wall levels. '
      'Keep the existing grass floor. Leave the north approach clear. Remove ALL '
      'temporary blocks inside/outside the house, descend safely, finish inside '
      'on the original grass floor. Use only ordinary BCL. Provided supplies are '
      '128 cobblestone, 32 dirt, a diamond pickaxe and shovel. No commands or flying. '
      'Plan scaffolds, roof access and descent yourself. Check actual completion.')


def native_proof(scene,nav,house,actor):
    valid=(scene.get('actor_session')==actor and nav.get('actor_session')==actor
           and scene.get('alive') is True and scene.get('in_world') is True
           and nav.get('ready') is True and nav.get('profile')=='stepped_full_blocks_v1'
           and nav.get('current_center_access') is True
           and scene.get('dimension')==nav.get('dimension')=='minecraft:overworld')
    reachable=set(_reachable(nav,True)) if valid else set()
    door=house.entrance;outside=house.point(house.width//2,0,-1)
    needed=house.interior()|{door,outside}
    return {'actor_session':actor,'interior_accessible':valid and needed<=reachable,
            'safe_player':valid and scene.get('on_ground') is True and scene.get('health',0)>0
                          and tuple(nav.get('current_cell',[])) in house.interior()
                          and tuple(nav.get('current_cell',[])) in reachable
                          and nav.get('on_fire') is False and nav.get('nearby_hostiles')==[],
            'scene':scene,'navigation':nav,'captured_at':time.time()}

def independent_native(player,house,actor):
    """Read-only native verification after the last BCL task, bracketed by actor.

    V0 intentionally compacts navigation metadata. Do not invent omitted actor,
    dimension or threat fields; acquire the existing FULL native read instead.
    """
    before=player.observe();nav=player.navigation(terrain=True);after=player.observe()
    proof=native_proof(after,nav,house,actor)
    if before.get('actor_session')!=actor:
        proof.update(interior_accessible=False,safe_player=False)
    proof['scope']='Read-only full native navigation, actor-bracketed after final gateway task'
    return proof

async def run(player,args):
    from blockwire.agent import SessionStore
    private=Path(args.private);manifest=validate(private/'baseline')
    metadata=json.loads((private/'fixture.json').read_text())
    lease=SessionStore(private/'fixture-lease.sqlite',{'agent_id':'benchmark-fixture',
        'world_id':manifest['identity'],'player_id':metadata['initial_scene']['player_uuid']})
    lease.acquire()
    if shutil.disk_usage(private).free<256*1024*1024:
        lease.release();raise RuntimeError('Insufficient free storage: no restore or native action started')
    try:return await _run(player,args)
    finally:lease.release()

async def _run(player,args):
    if not args.run_id or not args.run_id.replace('-','').replace('_','').isalnum():raise ValueError('Simple unique run ID required')
    private=Path(args.private);baseline=private/'baseline';world=Path(args.saves)/NAME
    run_dir=private.parent/args.run_id;run_dir.mkdir(mode=0o700,exist_ok=False)
    started=time.monotonic();house=House();registry=default_commands();is_b=args.action=='run-b'
    # All deterministic frames are statically validated BEFORE restoring/loading.
    source=(FIXTURES/'build.bcl').read_text() if not is_b else None
    if source:(run_dir/'program.bcl').write_text(source)
    try:compiled=frames(source,registry) if source else None
    except ValueError as error:
        diagnostic=getattr(error,'diagnostic',None)
        (run_dir/'compile-error.json').write_text(json.dumps({'effects_started':False,'diagnostic':diagnostic.to_dict() if diagnostic else str(error)},indent=2)+'\n')
        raise
    if compiled:
        (run_dir/'compiled.json').write_text(json.dumps([{'frame':i,'source_sha256':hashlib.sha256(part.encode()).hexdigest(),'digest':program.digest,'typed_ir':program.to_dict()} for i,(part,program) in enumerate(compiled)],indent=2)+'\n')
    from .audit import fixture_audit
    audit_baseline=fixture_audit(baseline)
    (run_dir/'fixture-audit.json').write_text(json.dumps(audit_baseline,indent=2)+'\n')
    (run_dir/'harness-source.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')},indent=2)+'\n')
    prior=None;expected_start=START;expected_inventory=INVENTORY;project_id=args.run_id
    if args.resume_from:
        if not args.resume_from.replace('-','').isalnum() or args.fault:raise ValueError('Explicit simple debug source required, no mixed faults')
        prior_dir=private.parent/args.resume_from;prior=json.loads((prior_dir/'result.json').read_text())
        if prior['metadata']['test']!='A' or prior.get('passed'):raise ValueError('Failed deterministic debug source required')
        baseline=prior_dir/'ended-world';expected_start=prior['native']['scene']['position'];project_id=prior['metadata'].get('project_id',prior['metadata']['test_id'])
        inventories=[o['output']['inventory'] for f in sorted(prior_dir.glob('*-exchange.json')) for o in json.loads(f.read_text())['response'].get('result',{}).get('operations',[]) if 'inventory' in o.get('output',{})]
        expected_inventory=inventories[-1]
        shutil.copy2(prior_dir/'project.sqlite',run_dir/'project.sqlite')
    if compiled and not 0<=args.start_frame<len(compiled):raise ValueError('Valid explicit start frame required')
    if args.start_frame and prior is None:raise ValueError('Never skip frames in a fresh trial')
    manifest=restore(baseline,world,run_dir/'previous-closed-world',lambda:title(player))
    load_events=[]
    def load_audit(value):
        load_events.append(value)
        (run_dir/'load-events.json').write_text(json.dumps(load_events,indent=2)+'\n')
    scene=load(player,audit=load_audit)
    if max(abs(a-b) for a,b in zip(scene['position'],expected_start))>.05 or item_counts(player.inventory())!=expected_inventory:
        close(player);raise ValueError('Native start position/inventory does not match restored fixture')
    (run_dir/'initial.json').write_text(json.dumps({'scene':scene,'inventory':player.inventory()},indent=2)+'\n')
    token=secrets.token_urlsafe(48);gateway=BCLGateway(player,token,run_dir/'gateway-state',registry=registry)
    # Credentials live ONLY in the private build tree, never in versioned evidence.
    cert=Path(os.environ.get('BLOCKWIRE_BENCHMARK_CERT','build/bcl-verification/private/gateway.pem'))
    key=Path(os.environ.get('BLOCKWIRE_BENCHMARK_KEY','build/bcl-verification/private/gateway-key.pem'))
    server=await gateway.listen('127.0.0.1',0,server_tls(cert,key))
    url=f'wss://127.0.0.1:{server.sockets[0].getsockname()[1]}/v1'
    identity={'agent_id':'building-benchmark','world_id':prior['metadata'].get('world_namespace',prior['metadata']['snapshot_identity']) if prior else manifest['identity'],'player_id':scene['player_uuid']}
    metadata={'test_id':args.run_id,'test':'B' if is_b else 'A','minecraft_version':'26.3',
              'seed':31052026,'snapshot_identity':manifest['identity'],'reference_identity':house.digest(),
              'fault':args.fault,'resume_from':args.resume_from,'start_frame':args.start_frame,
              'project_id':project_id,'world_namespace':identity['world_id'],
              'scope':'Explicit debug continuation, NOT a fresh trial' if prior else 'Fresh restored-snapshot trial',
              'start':scene['position'],'fixture_start':START,'mode':'Survival/Peaceful','language':'BCL/1',
              'max_operations':512,'max_model_calls':60 if is_b else 0,'max_seconds':2700,
              'model':{'provider':'openai-codex','name':'gpt-6.1-sol','thinking':'high'} if is_b else None}
    (run_dir/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    sequence=0;failure=None;native={};agent_result=None;execution_started=time.monotonic()
    def audit(value):
        nonlocal sequence
        write_json(run_dir/f'{sequence:03d}-exchange.json',value);sequence+=1
        print(json.dumps({'exchange':sequence,'source':value['source'],'status':value['response'].get('status')}),flush=True)
        if args.fault=='lost-ack' and any(o.get('reason')=='block_placed' for o in value['response'].get('result',{}).get('operations',[])):
            raise RuntimeError('Injected lost PROJECT acknowledgement after native result, before durable project commit; never replay')
    try:
        with ProjectJournal(run_dir/'project.sqlite',identity,project_id,GOAL,policy='enclosure_v1' if is_b else 'blocks_v1') as journal:
            journal.bind(scene,allow_rebind=bool(prior))
            async with BCLClient(url,token,cert,session_id=args.run_id,agent_id=identity['agent_id'],world_id=identity['world_id'],player_uuid=scene['player_uuid'],actor_session=scene['actor_session'],timeout=150.) as client:
                if is_b:
                    from blockwire.command_decider import CommandJSONDecider
                    # The model sees NO test-A source, reference block list, save
                    # contents or benchmark package. Only explicit tool-free JSON.
                    import sys
                    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'examples'))
                    from project_agent import SYSTEM
                    prompt=SYSTEM+' This is a fixed-size supplied-material mechanical benchmark. '+GOAL
                    argv=[os.environ['PI_BIN'],'--provider','openai-codex','--model','gpt-6.1-sol','--thinking','high','--no-tools','--no-extensions','--no-mcp','--no-skills','--no-context-files','--no-prompt-templates','--no-themes','--no-session','--offline','--print','--mode','text','--system-prompt',prompt]
                    decider=CommandJSONDecider(argv,audit_directory=run_dir/'model',system_prompt=prompt,timeout=175.)
                else:
                    decider=None
                    journal.revise({'site':list(house.origin),'dimension':scene['dimension'],
                                    'sections':['walls','roof'],'blocks':[{'position':list(p),'block':b,'section':'roof' if p[1]==-57 else 'walls'} for p,b in house.blocks().items()]})
                agent=ProjectAgent(client,journal,decider,registry,max_calls=60,duration=2700.,audit=audit)
                if is_b:agent_result=await agent.run()
                else:
                    agent.deadline=time.monotonic()+2700.
                    await agent.exchange('S0 sync\nS1 absolute\nS2 normal\nS3 stop\nS4 60\nV0\nI0')
                    for index,(part,program) in enumerate(compiled):
                        if index<args.start_frame:continue
                        if args.fault=='cancel' and index==1:
                            await agent.exchange('S0 async')
                            executing=asyncio.create_task(agent.exchange(part,intent=True))
                            for _ in range(1000):
                                if agent.active and gateway.jobs.status(agent.active).get('phase')=='acting':break
                                await asyncio.sleep(.005)
                            else:raise RuntimeError('Cancellation probe never observed acting phase')
                            cancelled=await client.cancel(agent.active)
                            (run_dir/'cancel-reply.json').write_text(json.dumps(cancelled,indent=2)+'\n')
                            response=await executing
                        else:response=await agent.exchange(part,intent=True)
                        if response.get('status')!='completed':
                            failure={'layer':'execution','frame':index,'source':part,'result':response};break
                        await agent.exchange('V0\nI0')
                        if args.fault=='truncate' and index==1:
                            failure={'layer':'fault_injection','type':'truncated_program','after_frame':index};break
                # Same final native inspection for A and B, through the gateway.
                # No world mutation permitted in this acquisition step.
                final=await agent.exchange('V0\nI0')
                observations=[o['output'] for o in final.get('result',{}).get('operations',[]) if o.get('output',{}).get('visibility')]
                nav=observations[-1].get('navigation',{}) if observations else {}
                native=independent_native(player,house,scene['actor_session'])
                (run_dir/'project-summary.json').write_text(json.dumps(journal.summary(),indent=2)+'\n')
    except BaseException as error:
        failure={'layer':'host_or_transport','type':type(error).__name__,'reason':str(error)[:2048]}
    finally:
        execution_finished=time.monotonic()
        server.close();await server.wait_closed();await gateway.aclose()
        # Gateway owns controls until cleanup. Never save/restore through a stuck
        # quarantined worker: leave the actor fenced and require host intervention.
        if gateway.failed:raise RuntimeError('Gateway quarantined; no snapshot/safe-state claim')
        if player.menu().get('type')!='TitleScreen':
            if player.observe().get('actor_session')!=scene['actor_session']:
                raise RuntimeError('Actor replaced: do not save/close an unrelated replacement world')
            from blockwire.skills.crafting import ensure_gameplay
            from types import SimpleNamespace
            ensure_gameplay(SimpleNamespace(player=player,check=lambda:None,pause=time.sleep))
        close(player)
    write_json(run_dir/'activation-outcome.json',{'failure':failure,'native':native,'agent_result':agent_result,
        'execution_seconds':execution_finished-execution_started,'world_closed':True})
    ended=capture(world,run_dir/'ended-world',lambda:title(player))
    observed=voxels(run_dir/'ended-world',house.workspace()|house.floors())
    verification=verify(house,observed,native=native)
    exchanges=[json.loads(p.read_text()) for p in sorted(run_dir.glob('*-exchange.json'))]
    operations=[o for x in exchanges for o in x['response'].get('result',{}).get('operations',[])]
    from blockwire.statistics import load_statistics,statistics_report
    relative=Path('players/stats')/(scene['player_uuid']+'.json')
    statistics=statistics_report(load_statistics(run_dir/'ended-world'/relative),load_statistics(baseline/relative))
    (run_dir/'statistics.json').write_text(json.dumps(statistics,indent=2)+'\n')
    model_requests=[json.loads(p.read_text()) for p in sorted((run_dir/'model').glob('*-request.json'))] if is_b else []
    summary=json.loads((run_dir/'project-summary.json').read_text()) if (run_dir/'project-summary.json').exists() else {}
    feedback_decisions=sum(bool(r['context'].get('last_action_result') and r['context']['last_action_result'].get('status') not in {'completed','succeeded'}) for r in model_requests)
    result={'metadata':metadata,'elapsed_seconds':time.monotonic()-started,'execution_seconds':execution_finished-execution_started,'failure':failure,
            'verified_native_placement_events':sum(o.get('reason')=='block_placed' and o.get('status')=='succeeded' for o in operations),
            'saved_statistics':statistics,
            'llm_calls':len(model_requests),'plan_revisions':max(0,summary.get('revision',1)-1),
            'feedback_conditioned_decisions':feedback_decisions,'compiler_rejections':sum(x['response'].get('phase')=='compile' for x in exchanges),
            'agent_result':agent_result,'executed_operations':len(operations),
            'failed_actions':sum(o.get('status')!='succeeded' for o in operations),
            'last_successful_operation':next((o for o in reversed(operations) if o.get('status')=='succeeded'),None),
            'verification':verification,'native':native,'ended_snapshot_identity':ended['identity'],
            'objective_verified':verification['objective_verified'],
            'passed':not failure and verification['objective_verified'] and (not is_b or bool(agent_result and agent_result.get('objective_verified')))}
    if args.fault:
        expected_failure=(args.fault=='truncate' and failure and failure.get('type')=='truncated_program'
                          or args.fault=='lost-ack' and failure and 'Injected lost PROJECT' in failure.get('reason','')
                          or args.fault=='cancel' and failure and failure.get('result',{}).get('status')=='cancelled')
        result['fault_probe_passed']=bool(expected_failure and not verification['objective_verified'])
        result['scope']='Injected fault qualification ONLY, not a complete building trial'
    for filename,value in [('verification.json',verification),('result.json',result)]:
        write_json(run_dir/filename,value)
    return result
