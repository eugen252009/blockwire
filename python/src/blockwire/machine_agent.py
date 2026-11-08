"""Explicit event-fed LLM host for machine-v1. No gameplay planner or native reads."""
import argparse,asyncio,json,os,time
from pathlib import Path
from pydantic import ValidationError
from .bcl.client import BCLClient
from .machine_actions import action_registry
from .machine_mcp import EventInbox
from .tool_decider import OpenAIToolDecider
from .machine_plan import MachinePlan
from .machine_perception import describe_events
from .machine_composition import operation_cost


async def run(client,decider,goal,directory,*,duration=600.,max_decisions=20,model_timeout=30.,max_actions=100,extended_run=False):
    if client.profile!='machine-v1':raise ValueError('Machine gateway required')
    if not isinstance(goal,str) or not 1<=len(goal)<=2048:raise ValueError('Bounded explicit goal required')
    if type(extended_run)is not bool:raise ValueError('Explicit boolean extended-run authorization required')
    duration_cap,decision_cap,operation_cap=(86400,1000,1000000) if extended_run else (1800,100,1000)
    if type(max_actions)is not int or not 1<=max_actions<=operation_cap:raise ValueError('Action budget required')
    if type(max_decisions)is not int or not 1<=max_decisions<=decision_cap:raise ValueError('Decision budget required')
    if type(duration) not in (int,float) or not 1<=duration<=duration_cap:raise ValueError('Bounded duration required')
    if type(model_timeout) not in (int,float) or not .1<=model_timeout<=60:raise ValueError('Bounded model timeout')
    path=Path(directory)
    path.mkdir(mode=0o700,parents=True,exist_ok=True)
    if path.is_symlink() or path.stat().st_mode&0o077:raise ValueError('Private run directory required')
    if any(path.iterdir()):raise ValueError('Fresh empty run directory required; never resume pending work')
    fd=os.open(path/'STARTED',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.fsync(fd);os.close(fd)
    def sync_directory():
        fd=os.open(path,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    sync_directory()
    def record(name,data):
        with (path/name).open('x') as f:
            os.chmod(path/name,0o600);json.dump(data,f,allow_nan=False);f.flush();os.fsync(f.fileno())
        sync_directory()
    record('limits.json',{'extended_run':extended_run,'duration_seconds':duration,'max_decisions':max_decisions,
                         'max_operations':max_actions,'model_timeout_seconds':model_timeout})
    inbox=EventInbox(client.bind['actor_session']);deadline=time.monotonic()+duration;history=[];calls=0;operations=0;plan=MachinePlan(notes='').model_dump()
    result={'status':'stopped','goal_verified':False,'reason':'decision_budget_exhausted'}
    invalid_streak=0;search_pages=0
    def task_context():
        rows=[]
        for key,future in list(client.tasks.items())[-4:]:
            row={'task_id':key,'terminal':future.done()}
            if future.done():
                reply=future.result();outcome=reply.get('result',{})
                row.update(status=reply.get('status'),reason=outcome.get('reason'),
                    diagnostics=outcome.get('diagnostics',[]),gameplay_verified=False,
                    operations=[{k:op.get(k) for k in ('index','command','status','reason','input_release')}
                                for op in outcome.get('operations',[])[:32]])
            rows.append(row)
        return rows
    async with client:
        async def collect():
            try:
                while True:
                    if client.reader.done():raise ConnectionError('Gateway stream lost; no reconnect')
                    try:event=await asyncio.wait_for(client.events.get(),.25)
                    except asyncio.TimeoutError:continue
                    inbox.receive(event)
                    if event['event_type'] in {'player.dead','player.not_in_world','player.respawned','transport.disconnected','control.quarantined'}:
                        raise RuntimeError('Terminal actor/control event')
            except asyncio.CancelledError:raise
            except Exception as error:
                inbox.failure=type(error).__name__
                await client.__aexit__(None,None,None)
        collector=asyncio.create_task(collect())
        try:
            configured=await client.report(['state.scene','state.inventory','state.navigation','state.crafting','command.completed'])
            if configured['status']!='completed':raise RuntimeError('Reporting admission failed')
            initial_deadline=min(deadline,time.monotonic()+10)
            while len(inbox.state)<4:
                if inbox.failure or time.monotonic()>=initial_deadline:raise RuntimeError('Initial event state unavailable')
                await asyncio.sleep(.05)
            for step in range(max_decisions):
                if inbox.failure:raise RuntimeError('Event stream failed; no new decision/action')
                remaining=deadline-time.monotonic()
                if remaining<model_timeout+1:result['reason']='insufficient_request_deadline';break
                context={'goal':goal,'plan':plan,'plan_is_unverified':True,'events':describe_events(inbox.drain()),'control_state':client.control_state,'recent_requests':history[-8:],
                         'remaining_seconds':remaining,'remaining_model_calls':max_decisions-calls,
                         'remaining_action_budget':max_actions-operations-search_pages,'active_tasks':task_context(),
                         'rules':'Actions are low-level inputs, NOT pathfinding or verified gameplay outcomes. Compose independently. Interrupt cancels old work; explicit resume requires control.released.'}
                # Charge/record BEFORE inference. A timed-out request is never repeated.
                record(f'{step:03d}-request.json',context);calls+=1
                try:
                    decision=await asyncio.wait_for(asyncio.to_thread(decider.decide,context),model_timeout)
                except ValidationError as error:
                    # The typed decider validates before dispatch; no action from
                    # this rejected call has run. Charge it and expose diagnostics,
                    # not an automatic repair/replay. Transport/refusal/JSON errors
                    # are deliberately NOT caught here.
                    diagnostics=[{'type':row['type'],'loc':[str(v)[:64] for v in row['loc']],
                                  'message':row['msg'][:512]}
                                 for row in error.errors(include_url=False,include_input=False,include_context=False)[:8]]
                    rejection={'status':'rejected_before_dispatch','diagnostics':diagnostics,
                               'native_actions_dispatched':0,'automatic_retry':False}
                    record(f'{step:03d}-rejected.json',rejection)
                    history.append({'decision':{'kind':'rejected'},'reply':rejection})
                    invalid_streak+=1
                    if invalid_streak>=3:
                        result.update(status='failed',reason='repeated_invalid_tool_arguments',no_retry=True);break
                    await asyncio.sleep(.1)
                    continue
                invalid_streak=0
                record(f'{step:03d}-decision.json',decision)
                if inbox.failure or time.monotonic()>=deadline:raise RuntimeError('Stop before action admission')
                if decision['kind']=='plan':
                    plan=MachinePlan.model_validate({'notes':decision['notes']}).model_dump()
                    record(f'{step:03d}-plan.json',plan);continue
                if decision['kind']=='finish':
                    result['reason']='planner_finished_unverified'
                    result['model_stop_reason']=decision.get('reason')
                    break
                if decision['kind']=='wait':await asyncio.sleep(decision['wait_seconds']);continue
                if decision['kind']=='perception':
                    from .skills.core import SkillStop,SkillResult
                    if decision['name']=='search':
                        from .skills.search import Search,PAGES
                        parameters=Search.model_validate(decision['parameters']).model_dump(mode='json')
                        if operations+search_pages+PAGES>max_actions:raise RuntimeError('Search page budget exhausted')
                        search_pages+=PAGES
                        record(f'{step:03d}-search-intent.json',{'parameters':parameters,'reserved_search_pages':search_pages})
                        def check_search():
                            if inbox.failure:raise RuntimeError('Event stream failed during search')
                            if time.monotonic()>=deadline:raise SkillStop('timed_out','agent_deadline')
                        reply=await client.search(parameters,check=check_search)
                    elif decision['name']=='look_around':
                        from .skills.looking import describe_look_around
                        event=inbox.state['state.scene'];scene=event['data']['value']
                        if scene.get('actor_session')!=client.bind['actor_session']:raise ValueError('Scene actor mismatch')
                        try:report=describe_look_around(scene)
                        except SkillStop as stop:report=SkillResult(status=stop.status,reason=stop.reason,text=stop.reason)
                        reply={**report.model_dump(mode='json'),'cached':True,
                               'source_metadata':{k:v for k,v in event['data'].items() if k!='value'}}
                    else:raise ValueError('Unknown perception tool')
                    history.append({'decision':decision,'reply':reply});record(f'{step:03d}-perception.json',reply)
                    continue
                charge=(sum(operation_cost(a['name'],a['parameters']) for a in decision['actions']) if decision['kind']=='compose'
                        else operation_cost(decision['skill'],decision['parameters']) if decision['kind']=='act' else 0)
                if operations+search_pages+charge>max_actions:raise RuntimeError('Action operation budget exhausted')
                operations+=charge
                record(f'{step:03d}-dispatch-intent.json',{'decision':decision,'reserved_action_operations':operations})
                if decision['kind']=='compose':reply=await client.compose(decision['actions'])
                elif decision['kind']=='control':
                    if decision['control']=='interrupt':reply=await client.interrupt()
                    elif decision['control']=='resume':reply=await client.resume()
                    else:raise ValueError('Unknown control')
                elif decision['kind']=='act':reply=await client.action(decision['skill'],decision['parameters'])
                else:raise ValueError('Unknown decision')
                history.append({'decision':decision,'reply':reply});record(f'{step:03d}-admission.json',reply)
                # No await of the entire gameplay task: incoming events and interrupt
                # decisions remain possible while a previously admitted program runs.
                await asyncio.sleep(min(2.,max(0.,deadline-time.monotonic())))
        except Exception as error:
            result.update(status='failed',reason=type(error).__name__,no_retry=True)
        finally:
            cleanup='not_confirmed'
            if not inbox.failure and not client.reader.done():
                try:
                    record('before-stop-events.json',inbox.drain())
                    stopped=await client.interrupt()
                    until=time.monotonic()+5
                    while not inbox.failure and time.monotonic()<until:
                        if any(e['event_type']=='control.released' and e['data'].get('generation')==stopped.get('generation') for e in inbox.events):
                            cleanup='released';break
                        await asyncio.sleep(.05)
                except Exception:pass  # Unknown means no replay/reconnect, never success.
            collector.cancel();await asyncio.gather(collector,return_exceptions=True)
            result.update(model_calls=calls,reserved_action_operations=operations,reserved_search_pages=search_pages,plan=plan,history=history,events=inbox.drain(),cleanup=cleanup)
            record('result.json',result)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['url','certificate','token-file','session-id','agent-id','world-id','player-uuid','actor-session','llm-url','model','goal','state-directory']:
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--allow-remote-model',action='store_true')
    parser.add_argument('--model-key-env',default='BLOCKWIRE_LLM_API_KEY')
    parser.add_argument('--duration',type=float,default=600.)
    parser.add_argument('--max-decisions',type=int,default=20)
    parser.add_argument('--max-actions',type=int,default=100)
    parser.add_argument('--model-timeout',type=float,default=30.)
    parser.add_argument('--extended-run',action='store_true',help='Explicitly allow up to 24h, 1000 decisions and 1000000 operations; defaults and per-action/queue bounds stay unchanged.')
    args=parser.parse_args(argv);token=Path(args.token_file)
    if token.is_symlink() or token.stat().st_mode&0o077:raise ValueError('Private token file required')
    registry=action_registry()
    decider=OpenAIToolDecider(args.llm_url,args.model,registry=registry,allowed_skills=set(registry._definitions),control_tools=True,composition_tools=True,
        timeout=args.model_timeout,allow_remote=args.allow_remote_model,api_key=os.environ.get(args.model_key_env))
    client=BCLClient(args.url,token.read_text().strip(),args.certificate,session_id=args.session_id,
        agent_id=args.agent_id,world_id=args.world_id,player_uuid=args.player_uuid,
        actor_session=args.actor_session,profile='machine-v1')
    result=asyncio.run(run(client,decider,args.goal,args.state_directory,duration=args.duration,
        max_decisions=args.max_decisions,model_timeout=args.model_timeout,max_actions=args.max_actions,extended_run=args.extended_run))
    print(json.dumps(result,indent=2));return 0 if result['status']=='stopped' else 2

if __name__=='__main__':raise SystemExit(main())
