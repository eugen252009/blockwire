"""Explicit external model -> persistent project -> existing BCL TLS gateway.

No house plan or progression script. --describe is offline. Credentials/state/audit
paths are operator-selected and must never be shipped in a bundle.
"""
import argparse,asyncio,json,uuid
from pathlib import Path
from blockwire.projects import ProjectJournal
from blockwire.project_agent import ProjectAgent,ProjectDecision
from blockwire.bcl import default_commands
from blockwire.bcl.client import BCLClient
from blockwire.command_decider import CommandJSONDecider

SYSTEM='''You are an independent Minecraft project planner. Choose the site, design, material types, acquisition, access, phases, construction order and repairs yourself. Use only the supplied BCL registry; no Python, slash commands, cheats or fabricated observations. Return ONLY JSON matching the supplied ProjectDecision schema. Persist your complete intended structure as plan before construction. Plan blocks are desired positions, while I3 P is a SUPPORT position, F is its face; Atrue optionally chooses a mechanical standing pose. I4 Bblock P[targetX,targetY,targetZ] is the preferable mechanical single-voxel adapter: it chooses only currently observed neighboring supports and faces, searches native standing poses and delegates exact verified placement; it does NOT choose design or scaffolding. I3 remains explicit support/face control. I1 equips. An explicit already-observed correct I3 destination is idempotent, not a new consumed item. V2 aims; V0 observes bounded surfaces and native navigation. Invisible/unknown is NOT missing or correct. Materials and craft options are arithmetic, not instructions. Do not repeatedly inspect unchanged views: choose another view, access, materials or revise your plan when blocked. The runtime rejects false finishes. For enclosure_v1 include connected interior floor cells, one adjacent entrance, height >=2, complete corner/side walls and roof over all interior/entrance cells. All declared blocks must match. Natural walls are permitted only when actually observed; no manual supplies are implied. begin_verification starts a fresh non-world-mutating proof sweep: inspect the whole declared structure and provide current native interior/entrance geometry. Surface proof expires after 120 seconds, geometry after 10: batch multiple V2/V0 views in one bounded BCL frame when checking a structure; every V0 is reconciled. Re-seeing expired old surfaces is not new construction progress. You may walk/aim to inspect, but any mining/placement invalidates the sweep. Your free-text finish is never proof of project completion. Maintain access to and from work positions as your design changes. The native graph permits only known full-block one-step edges; a completed surface is not proof that you can reach the interior from a roof. Temporary access and its materials are YOUR planning choices. No house template or action order is provided. Schema: '''+json.dumps(ProjectDecision.model_json_schema())

def parser():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--describe',action='store_true')
 for flag in ['url','token-file','certificate','state','audit','model-argv-file','project-id','agent-id','world-id','player-uuid','actor-session','goal']:p.add_argument('--'+flag)
 p.add_argument('--session-id',help='Explicit BCL session for inspection/reconnect; default creates a fresh activation ID, never replays old work.')
 p.add_argument('--policy',choices=['enclosure_v1','blocks_v1'],default='enclosure_v1')
 p.add_argument('--resume',action='store_true');p.add_argument('--rebind',action='store_true')
 p.add_argument('--max-calls',type=int,default=60);p.add_argument('--duration',type=float,default=2700.)
 return p

async def run(args):
 identity={'agent_id':args.agent_id,'world_id':args.world_id,'player_id':args.player_uuid}
 if Path(args.state).exists() and not args.resume:raise ValueError('Existing project requires explicit --resume')
 argv=json.loads(Path(args.model_argv_file).read_text())
 session=args.session_id or ('project-'+uuid.uuid4().hex)
 import re
 if not re.fullmatch(r'[a-zA-Z0-9_.:-]{1,128}',session):raise ValueError('Bounded BCL session ID required')
 audit=Path(args.audit)/session;audit.mkdir(parents=True,exist_ok=False,mode=0o700)
 model=CommandJSONDecider(argv,system_prompt=SYSTEM,audit_directory=audit/'model',timeout=175.)
 sequence=[0]
 def record(value):
  sequence[0]+=1
  with (audit/f'{sequence[0]:04d}-exchange.json').open('x') as out:json.dump(value,out,indent=2)
 with ProjectJournal(args.state,identity,args.project_id,args.goal,policy=args.policy) as journal:
  async with BCLClient(args.url,Path(args.token_file).read_text().strip(),args.certificate,session_id=session,agent_id=args.agent_id,world_id=args.world_id,player_uuid=args.player_uuid,actor_session=args.actor_session,timeout=150.) as client:
   response=await client.send('S0 sync\nV0')
   scene=response['result']['operations'][-1]['output'];journal.bind(scene,allow_rebind=args.rebind)
   return await ProjectAgent(client,journal,model,default_commands(),max_calls=args.max_calls,duration=args.duration,audit=record).run()

def main():
 p=parser();args=p.parse_args()
 if args.describe:print(json.dumps({'decision_schema':ProjectDecision.model_json_schema(),'policy':'Existing BCL/native execution only; explicit actor/world/model/TLS selection; no automatic reconnect/replay.'},indent=2));return
 for name in ['url','token_file','certificate','state','audit','model_argv_file','project_id','agent_id','world_id','player_uuid','actor_session','goal']:
  if not getattr(args,name):p.error('--'+name.replace('_','-')+' required')
 print(json.dumps(asyncio.run(run(args)),indent=2))
if __name__=='__main__':main()
