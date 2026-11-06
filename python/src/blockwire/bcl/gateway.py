"""Explicit loopback TLS BCL/1 gateway. The native Minecraft TLS bridge is unchanged."""
import argparse,asyncio,hmac,ipaddress,json,os,ssl,threading,time
from pathlib import Path
from uuid import uuid4
from websockets.asyncio.server import serve
from ..client import Bridge,BridgeError,Player,CallableBackend
from ..controller import Event
from ..errors import classify,FaultKind,InvariantViolation
from ..llm import strict_json
from ..recipes import item_counts
from .compiler import BCLError,Diagnostic,compile_report,compile_bcl
from ..feedback import FeedbackStore,InputDenied
from .registry import default_commands,DEFAULT_PERMISSIONS
from .runtime import BCLJobs


def server_tls(certificate,key):
    key=Path(key)
    if key.is_symlink() or (os.name=='posix' and key.stat().st_mode&0o077):raise ValueError('Private nonsymlink TLS key required (0600)')
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(certificate),str(key));return context


class BCLGateway:
    def __init__(self,player,token,state_directory,*,registry=None,permissions=DEFAULT_PERMISSIONS,cleanup_grace=10.,send_timeout=5.,event_filter=None,allow_respawn=False,native_events=None,reporting_policy=None,feedback_directory=None,input_policy=None,profile='legacy'):
        Bridge(token)  # Reuse existing strict API-key validation; never make a native connection here.
        if profile not in {'legacy','machine-v1'}:raise ValueError('Unknown gateway profile')
        self.profile=profile;self.search_busy=False
        if profile=='machine-v1':
            from .machine import machine_commands
            if registry is not None:raise ValueError('Machine profile uses its fixed action registry')
            registry=machine_commands()
        self.token=token;self.registry=registry or default_commands();self.failed=False
        if type(cleanup_grace) not in (int,float) or not .01<=cleanup_grace<=30 or type(send_timeout) not in (int,float) or not .01<=send_timeout<=30:raise ValueError('Bounded cleanup/send timeouts required')
        if event_filter is not None and not callable(event_filter):raise ValueError('Trusted local event filter required')
        self.cleanup_grace,self.send_timeout=cleanup_grace,send_timeout
        if type(allow_respawn) is not bool:raise ValueError('Explicit respawn permission required')
        self.allow_respawn=allow_respawn
        self.event_filter=event_filter
        self.controllers={};self.session_states={};self.reapers=set();self.roles={}
        self.native_lock=threading.RLock()
        def dispatch(q):
            with self.native_lock:
                if self.failed:raise BridgeError('transport_error_no_reconnect')
                try:return player.backend.call(q['op'],**{k:v for k,v in q.items() if k!='op'})
                except BridgeError as e:
                    if classify(e) in {FaultKind.TRANSPORT,FaultKind.INVARIANT}:self.failed=True
                    raise
                except Exception as error:
                    self.failed=True
                    raise InvariantViolation('native_backend_invariant_failed') from error
        self.player=Player(CallableBackend(dispatch));self.jobs=BCLJobs(self.registry,self.player,state_directory,permissions)
        self.connections=set();self.bound=set();self.sinks={};self.sample_lock=asyncio.Lock();self.sampled_at=0.;self.sample=None;self.sample_id=0
        self.auto_events=None
        if input_policy is not None and feedback_directory is None:raise ValueError('Persistent audit directory required for input policy')
        self.feedback=FeedbackStore(feedback_directory,input_policy) if feedback_directory is not None else None
        if native_events is not None:
            from .auto_events import AutoReporter,register_events
            register_events(self.registry);self.auto_events=AutoReporter(self,native_events,reporting_policy)
    async def publish(self,event,*,session_id=None):
        """Trusted host providers may publish REGISTERED events; never a client-frame operation."""
        if not isinstance(event,Event) or event.name not in self.registry.events:raise ValueError('Unregistered event')
        for sid,sink in list(self.sinks.items()):
            if session_id is None or sid==session_id:await sink(event.name,event.data)
    async def authorize(self,connection,request):
        if request.path!='/v1' or request.headers.get('Origin') is not None or not hmac.compare_digest(request.headers.get('Authorization',''),'Bearer '+self.token):
            return connection.respond(403,'Forbidden\n')
        if len(self.connections)>=8:return connection.respond(503,'Connection bound reached\n')
    async def observe(self):
        async with self.sample_lock:
            if self.failed:raise BridgeError('transport_error_no_reconnect')
            if time.monotonic()-self.sampled_at>=.5:
                observed_at_ms=int(time.time()*1000);observed_monotonic_ns=time.monotonic_ns()
                scene=await asyncio.to_thread(self.player.observe)
                lifecycle='player.not_in_world' if not scene.get('in_world',True) else 'player.dead' if not scene.get('alive') else 'player.alive'
                inventory=await asyncio.to_thread(self.player.inventory) if lifecycle=='player.alive' else None
                if inventory is not None and scene.get('actor_session')!=inventory.get('actor_session'):raise BridgeError('actor_session_changed')
                self.sample={'lifecycle':lifecycle,'actor_session':scene.get('actor_session'),'player_uuid':scene.get('player_uuid'),'alive':scene.get('alive'),
                    'dimension':scene.get('dimension'),'player.position':{'position':scene.get('position')},'player.health':{'health':scene.get('health'),'hunger':scene.get('hunger')},
                    'inventory.changed':{'inventory':item_counts(inventory)} if inventory is not None else None}
                if self.profile=='machine-v1' and lifecycle=='player.alive':
                    from ..decision_context import native_navigation
                    self.sample_id+=1
                    self.sample.update({'sample_id':self.sample_id,'observed_at_ms':observed_at_ms,'observed_monotonic_ns':observed_monotonic_ns,
                        'state.scene':scene,'state.inventory':inventory})
                    from ..machine_crafting import crafting_report
                    self.sample['state.crafting']=crafting_report(inventory)
                    with self.jobs.lock:
                        wants_navigation=any('state.navigation' in s.subscriptions for s in self.jobs.sessions.values())
                    if wants_navigation:
                        navigation=await asyncio.to_thread(self.player.navigation,terrain=True)
                        self.sample['state.navigation']=native_navigation(scene,inventory,navigation)
                self.sampled_at=time.monotonic()
            return self.sample
    async def handler(self,ws):
        if len(self.connections)>=8:await ws.close(1013,'Connection bound');return
        self.connections.add(ws);out=asyncio.Queue(maxsize=64);sid=None;session=None;owned=set();closed=set();seen={};operation_counts={};progress_seen={};seq=0;input_records={}
        connection_id=str(uuid4());role='controller';actor_key=None;machine=None;report_seen={};report_sent={};resume_tasks=set();search_pages=None
        async def emit(message):
            nonlocal seq
            message=dict(message)
            if len(json.dumps(message,allow_nan=False).encode())>30000 and isinstance(message.get('result'),dict):
                r=message['result'];message['result']={k:v for k,v in r.items() if k not in {'history','operations'}}
                message['result']['operations']=[{k:v for k,v in row.items() if k!='output'} for row in r.get('operations',[])]
                message['result']['details_omitted']=True
            if len(json.dumps(message,allow_nan=False).encode())>30000:
                await ws.close(1013,'Outbound frame bound exceeded');raise RuntimeError('outbound_frame_bound')
            seq+=1;message={**message,'language':'BCL/1','session_id':sid,'connection_id':connection_id,'sequence':seq}
            try:out.put_nowait(message)
            except asyncio.QueueFull:
                await ws.close(1013,'Event queue overflow')
                raise RuntimeError('event_queue_overflow')
        async def event(name,data,**correlation):
            critical=name in {'player.dead','player.respawned','player.not_in_world','transport.disconnected','control.released','control.quarantined'}
            if session is None or (not critical and name not in session.subscriptions):return
            if not critical and self.event_filter is not None and not self.event_filter(name,data,session.store.identity):return
            from .auto_events import EVENTS
            from .machine import STATE_EVENTS
            if name in STATE_EVENTS and out.qsize()>=48:
                self.jobs.close_session(sid)
                await ws.close(1013,'State report backpressure; no silent loss')
                raise RuntimeError('state_report_backpressure')
            if name in EVENTS:
                if data.get('actor_session')!=session.actor_session:return
                # Observation traffic cannot occupy the last sixteen lifecycle/response slots.
                if out.qsize()>=48:
                    if self.auto_events:self.auto_events.metrics['gateway_dropped']+=1
                    return
            definition=self.registry.events[name];e=Event(name,data)
            await emit({'type':'event','event_type':e.name,'opcode':definition['opcode'],'direction':'server_to_client','data':e.data,**correlation})
        async def sender():
            while True:
                message=await out.get()
                try:await asyncio.wait_for(ws.send(json.dumps(message,allow_nan=False)),self.send_timeout)
                finally:out.task_done()
        async def reporter():
            from .machine import STATE_EVENTS
            while True:
                await asyncio.sleep(.25)
                if session is None or self.profile!='machine-v1':continue
                wanted=session.subscriptions & STATE_EVENTS.keys()
                if not wanted:continue
                sample=await self.observe()
                if sample['actor_session']!=session.actor_session or sample['player_uuid']!=session.store.identity['player_id']:
                    self.jobs.close_session(sid);raise BridgeError('actor_session_changed')
                for name in sorted(wanted):
                    value=sample.get(name)
                    if value is None:continue
                    comparable={k:v for k,v in value.items() if k not in {'sampled_at_ms','text'}}
                    changed=report_seen.get(name)!=comparable
                    if not changed and time.monotonic()-report_sent.get(name,0.)<2.:continue
                    report_seen[name]=comparable;report_sent[name]=time.monotonic()
                    await event(name,{'actor_session':session.actor_session,'sample_id':sample['sample_id'],
                        'observed_at_ms':sample['observed_at_ms'],'observed_monotonic_ns':sample['observed_monotonic_ns'],
                        'changed':changed,'value':value})
        async def resume_control(identifier):
            try:
                response=await machine.resume()
                await emit({'type':'response','request_id':identifier,'status':'completed',**response})
            except Exception:
                quarantined=machine.state=='quarantined'
                if quarantined:await event('control.quarantined',{'actor_session':session.actor_session,'reason':'UNKNOWN_NO_RETRY','generation':machine.generation})
                await emit({'type':'response','request_id':identifier,'status':'failed',
                            'diagnostics':[{'code':'UNKNOWN_NO_RETRY' if quarantined else 'CONTROL_RELEASE_REQUIRED'}]})
        async def watcher():
            while True:
                await asyncio.sleep(.25)
                if session is None:continue
                if machine is not None:
                    if self.jobs.halted and machine.state!='quarantined':
                        machine.state='quarantined'
                        await event('control.quarantined',{'actor_session':session.actor_session,'reason':'UNKNOWN_NO_RETRY'})
                    notification=await machine.advance()
                    if notification:await event(*notification)
                for identifier in list(owned-closed):
                    result=self.jobs.status(identifier);j=self.jobs.jobs[identifier];runner=j['runner']
                    if j['result'] is None and runner:
                        progress={k:result.get(k) for k in ('phase','bcl_index','bcl_total','progress')}
                        if progress_seen.get(identifier)!=progress:
                            progress_seen[identifier]=progress
                            await emit({'type':'progress','request_id':j['prepared'].request_id,'task_id':identifier,'status':'running','progress':progress})
                    results=j['result'].get('operations',[]) if j['result'] is not None else runner.driver.results[:] if runner else []
                    n=operation_counts.get(identifier,0)
                    for row in results[n:]:
                        data={**row,'gameplay_verified':False,'verification_scope':'native command/input postconditions only'} if machine is not None else row
                        await event('command.completed',data,task_id=identifier,request_id=j['prepared'].request_id)
                    operation_counts[identifier]=len(results)
                    if j['result'] is not None:
                        if machine is not None:result={**result,'gameplay_verified':False,'verification_scope':'native command/input postconditions only; NOT block placement, harvesting or external goal'}
                        closed.add(identifier)
                        if self.feedback and identifier in input_records:
                            await asyncio.to_thread(self.feedback.outcome,input_records[identifier],result['status'],result.get('reason',''))
                        await emit({'type':'response','request_id':j['prepared'].request_id,'task_id':identifier,
                            'status':'completed' if result['status']=='succeeded' else result['status'],'result':result,
                            'modal':session.modal.to_dict(),'coordinate_context':session.coordinate_context.to_dict()})
                if session.subscriptions & {'player.position','player.health','inventory.changed','player.dead','player.respawned','player.not_in_world'} or role=='controller':
                    try:
                        sample=await self.observe()
                        life=sample['lifecycle']
                        if life in {'player.dead','player.not_in_world'}:
                            if machine is not None and role=='controller':machine.quarantine()
                            self.jobs.close_session(sid)
                            if seen.get('lifecycle')!=life:await event(life,{'actor_session':sample['actor_session']})
                            seen['lifecycle']=life
                            if life=='player.dead':seen['was_dead']=True
                            continue
                        if sample['actor_session']!=session.actor_session or sample['player_uuid']!=session.store.identity['player_id']:
                            if (seen.get('was_dead') or seen.get('lifecycle')=='player.dead') and sample['player_uuid']==session.store.identity['player_id']:
                                await event('player.respawned',{'actor_session':sample['actor_session'],'requires_explicit_new_session':True})
                                await asyncio.wait_for(out.join(),self.send_timeout)
                                self.jobs.close_session(sid)
                                await ws.close(1000,'Respawn observed; bind a new explicit actor session')
                                return
                            raise BridgeError('actor_session_changed')
                        seen['lifecycle']=life
                        for name in ('player.position','player.health','inventory.changed'):
                            if name in session.subscriptions and sample[name] is not None and seen.get(name)!=sample[name]:
                                seen[name]=sample[name];await event(name,sample[name])
                    except Exception as error:
                        if machine is not None and role=='controller':machine.quarantine()
                        self.jobs.close_session(sid)
                        if classify(error)==FaultKind.TRANSPORT:await event('transport.disconnected',{'requires_explicit_reconnect':True})
                        await emit({'type':'error','status':'failed','diagnostics':[{'code':'ACTOR_OR_CONNECTION_LOST'}]})
                        await ws.close(1011,'Actor or native connection lost');return
        sending=asyncio.create_task(sender());watching=asyncio.create_task(watcher());reporting=asyncio.create_task(reporter())
        def supervise(task):
            if not task.cancelled():task.exception()  # Retrieve failure; a dead producer/consumer must close the socket, not remain silent.
            if ws.state.name=='OPEN':
                if machine is not None and role=='controller':machine.quarantine()
                asyncio.create_task(ws.close(1011,'Gateway background task terminated'))
        sending.add_done_callback(supervise);watching.add_done_callback(supervise);reporting.add_done_callback(supervise)
        try:
            async for body in ws:
                msg={};kind=None;audit_record=None
                try:
                    if not isinstance(body,str):raise ValueError('Text JSON frames only')
                    msg=strict_json(body);kind=msg.get('type');request_id=msg.get('request_id')
                    if kind=='bind':
                        allowed={'type','language','session_id','agent_id','world_id','player_uuid','actor_session'}
                        if sid is not None or set(msg)-allowed-{'role','profile'} or not allowed<=set(msg) or msg['language']!='BCL/1':raise ValueError('Invalid/incompatible bind')
                        if msg.get('profile','legacy')!=self.profile:raise ValueError('Explicit gateway profile mismatch')
                        if self.profile=='machine-v1' and self.jobs.halted:raise ValueError('UNKNOWN_NO_RETRY: machine gateway quarantined')
                        candidate=msg['session_id'];role=msg.get('role','controller')
                        if role not in {'controller','observer'}:raise ValueError('Invalid session role')
                        if candidate in self.bound:raise BCLError(Diagnostic('SESSION_BUSY','Connected or cleanup pending; no replay/rebind until release.',phase='gateway'))
                        # Fresh identity proof before binding any modal state; no game mutation.
                        self.sampled_at=0.  # Binding requires fresh identity, not an old event cache.
                        sample=await self.observe()
                        if self.failed or sample['actor_session']!=msg['actor_session'] or sample['player_uuid']!=msg['player_uuid']:
                            raise ValueError('Actor binding mismatch')
                        if self.profile=='machine-v1':
                            from ..machine_actions import trace
                            from .machine_control import fresh_release
                            try:
                                if role=='controller':await fresh_release(self.player,msg['actor_session'])
                                else:await asyncio.to_thread(trace,self.player,msg['actor_session'])
                            except BridgeError:raise
                            except (ValueError,RuntimeError) as error:raise ValueError('Compatible native trace and fresh released inputs required before control binding') from error
                        identity={'agent_id':msg['agent_id'],'world_id':msg['world_id'],'player_id':msg['player_uuid']}
                        actor_key=msg['player_uuid']
                        if role=='controller' and actor_key in self.controllers:raise BCLError(Diagnostic('ACTOR_BUSY','One controller per player; observers may bind read-only.',phase='gateway'))
                        session=self.jobs.session(candidate,identity,msg['actor_session'])
                        if ('gateway_role' in session.state and session.state.get('gateway_profile','legacy')!=self.profile) or session.state.get('gateway_role',role)!=role:
                            self.jobs.release_session(candidate)
                            raise ValueError('Persisted role mismatch; use a new session ID')
                        returning_controller=role=='controller' and 'gateway_role' in session.state
                        session.state['gateway_role']=role;session.state['gateway_profile']=self.profile
                        if self.profile=='machine-v1':
                            from .machine_control import MachineControl
                            machine=MachineControl(self.jobs,candidate,session.actor_session,self.player)
                            if returning_controller:machine.state='requested'  # Reconnect is never implicit resume.
                            session.state['modal']['execution_mode']='async'
                            session.state['subscriptions']=[]  # No implicit reporting replay on connection/rebind.
                        session.store.save(session.state)
                        sid=candidate;self.bound.add(sid);self.sinks[sid]=event;self.roles[sid]=role
                        if role=='controller':self.controllers[actor_key]=sid
                        self.session_states[sid]='connected'
                        await emit({'type':'response','request_id':0,'status':'bound','modal':session.modal.to_dict(),
                            'coordinate_context':session.coordinate_context.to_dict(),'role':role,
                            'last_request_id':session.state['last_request_id'],'events_replayed':False,
                            'profile':self.profile,'control_state':machine.state if machine else None,'feedback_supported':self.feedback is not None,'input_policy':self.feedback.policy.describe() if self.feedback else None})
                        continue
                    if session is None:raise ValueError('Bind explicit authorized session first')
                    if kind=='interrupt':
                        if machine is None or role!='controller' or set(msg)!={'type','request_id'}:raise ValueError('Invalid interrupt')
                        if type(request_id)is not int or not 1<=request_id<=9007199254740991:raise ValueError('Invalid request ID')
                        await emit({'type':'response','request_id':request_id,'status':'completed',**machine.interrupt()})
                        continue  # Emergency cancellation never waits for the audit disk or action FIFO.
                    if kind=='action':
                        from .machine import encode_action
                        if machine is None or set(msg)!={'type','request_id','name','parameters'}:raise ValueError('Invalid typed action')
                        msg={'type':'bcl','request_id':request_id,'source':encode_action(self.registry,msg['name'],msg['parameters'])};kind='bcl'
                    if self.feedback:
                        payload={k:msg[k] for k in ['source','task_id','feedback_id','feedback','parameters'] if k in msg}
                        try:audit_record=await asyncio.to_thread(self.feedback.audit,session.store.identity,sid,str(kind)[:64],request_id,payload)
                        except Exception as error:
                            if kind not in {'cancel','feedback_status'}:raise InputDenied('input_audit_unavailable; no new effects') from error
                            # Cancellation remains available even when audit storage is exhausted.
                    if kind=='report':
                        if machine is None or set(msg)!={'type','request_id','events'}:raise ValueError('Invalid reporting configuration')
                        from .machine import STATE_EVENTS
                        from .auto_events import EVENTS
                        names=msg['events']
                        allowed_events=set(STATE_EVENTS)|set(EVENTS)|{'command.completed'}
                        if not isinstance(names,list) or len(names)>12 or any(not isinstance(n,str) or n not in allowed_events or n not in self.registry.events for n in names) or len(set(names))!=len(names):raise ValueError('Unknown/duplicate reporting channel')
                        with self.jobs.lock:
                            _,response=session.prepare('',request_id,control={'type':'report','events':names})
                            if not response.get('deduplicated'):
                                session.state['subscriptions']=list(names);session.store.save(session.state);report_seen.clear();report_sent.clear()
                        await emit({'type':'response',**response,'subscriptions':sorted(session.subscriptions),'snapshot_delivery':'independent events; no action queued'})
                    elif kind=='search':
                        if machine is None or set(msg)!={'type','request_id','parameters'}:raise ValueError('Invalid search page')
                        if search_pages is None:
                            from .search import SearchPages
                            search_pages=SearchPages(self,session,machine,emit,ws)
                        await search_pages.start(request_id,msg['parameters'])
                    elif kind=='resume':
                        if machine is None or role!='controller' or set(msg)!={'type','request_id'}:raise ValueError('Invalid resume')
                        if type(request_id)is not int or not 1<=request_id<=9007199254740991:raise ValueError('Invalid request ID')
                        if resume_tasks:raise ValueError('Resume confirmation already pending')
                        task=asyncio.create_task(resume_control(request_id));resume_tasks.add(task)
                        def resumed(done):
                            resume_tasks.discard(done)
                            if not done.cancelled():done.exception()
                        task.add_done_callback(resumed)
                    elif kind=='bcl':
                        if machine is not None:machine.admit()
                        if set(msg)!={'type','request_id','source'}:raise ValueError('Invalid BCL frame fields')
                        if self.feedback:
                            permissions={'observe','settings','events'} if role=='observer' else self.jobs.permissions
                            program=compile_bcl(msg['source'],self.registry,permissions=permissions)
                            await asyncio.to_thread(self.feedback.admit_bcl,session.store.identity,sid,request_id,msg['source'],program)
                        if role=='observer':
                            report=compile_report(msg['source'],self.registry,permissions={'observe','settings','events'})
                            if not report['ok']:
                                await emit({'type':'response','request_id':request_id,'status':'failed','diagnostics':report['diagnostics']});continue
                            prepared,response=session.prepare(msg['source'],request_id)
                            if prepared is not None:
                                executed=[]
                                try:
                                    for index,o in enumerate(prepared.program.operations):
                                        command=self.registry.resolve(o.namespace,o.opcode)
                                        if command.category=='setting':
                                            self.sampled_at=0.;sample=await self.observe()
                                            if sample['actor_session']!=session.actor_session or sample['player_uuid']!=session.store.identity['player_id']:
                                                raise BridgeError('actor_session_changed')
                                            captured=session.capture_home(request_id,prepared.coordinates[index].home_id,
                                                sample['player.position']['position'],sample['dimension'])
                                            executed.append({'command':o.namespace+':'+o.command,'status':'succeeded',
                                                'reason':'relative_home_captured','coordinate_context':captured.to_dict()})
                                        else:
                                            sample=await self.observe()
                                            if sample['actor_session']!=session.actor_session or sample['player_uuid']!=session.store.identity['player_id']:
                                                raise BridgeError('actor_session_changed')
                                            executed.append({'command':o.command,'output':sample.get('inventory.changed') if o.opcode=='I0' else sample})
                                    outputs=[*response.get('outputs',[]),*executed]
                                    session.update(request_id,status='completed',outputs=outputs)
                                    response={**response,'status':'completed','outputs':outputs,
                                        'modal':session.modal.to_dict(),'coordinate_context':session.coordinate_context.to_dict()}
                                except BridgeError as error:
                                    fault=classify(error);diagnostics=[{'code':fault.value,'message':str(error)[:256]}]
                                    session.fail_homes(request_id,'failed');session.update(request_id,status='failed',diagnostics=diagnostics)
                                    raise
                                except (ValueError,TypeError) as error:
                                    session.fail_homes(request_id,'failed')
                                    diagnostics=[{'code':'INVALID_COORDINATE_HOME','message':str(error)[:256]}]
                                    session.update(request_id,status='failed',diagnostics=diagnostics)
                                    response={**response,'status':'failed','diagnostics':diagnostics,
                                        'modal':session.modal.to_dict(),'coordinate_context':session.coordinate_context.to_dict()}
                        else:response=self.jobs.submit(sid,msg['source'],request_id,session.store.identity,session.actor_session)
                        identifier=response.get('task_id')
                        if identifier and not response.get('deduplicated'):owned.add(identifier)
                        if self.feedback and audit_record is not None:
                            await asyncio.to_thread(self.feedback.outcome,audit_record,response['status'])
                            if identifier and not response.get('deduplicated'):input_records[identifier]=audit_record
                        await emit({'type':'response',**response})
                    elif kind in {'feedback','feedback_status'}:
                        allowed={'type','request_id','feedback_id','feedback'} if kind=='feedback' else {'type','request_id','feedback_id'}
                        if set(msg)!=allowed or not self.feedback:raise ValueError('Feedback is disabled or frame schema invalid')
                        if type(request_id) is not int or not 1<=request_id<=9007199254740991:raise ValueError('Invalid feedback correlation ID')
                        self.sampled_at=0.;sample=await self.observe()
                        if sample['actor_session']!=session.actor_session or sample['player_uuid']!=session.store.identity['player_id']:raise BridgeError('actor_session_changed')
                        if kind=='feedback':
                            result=await asyncio.to_thread(self.feedback.submit,session.store.identity,sid,msg['feedback_id'],msg['feedback'],session.actor_session)
                        else:result=await asyncio.to_thread(self.feedback.status,session.store.identity,sid,msg['feedback_id'])
                        if audit_record is not None:await asyncio.to_thread(self.feedback.outcome,audit_record,'recorded' if kind=='feedback' else 'read')
                        await emit({'type':'response','request_id':request_id,'status':'recorded' if kind=='feedback' else 'completed','result':result})
                    elif kind=='cancel':
                        if machine is not None:raise ValueError('Use out-of-band interrupt; machine cancellation requires the release barrier')
                        if set(msg)!={'type','request_id','task_id'} or msg['task_id'] not in owned:raise ValueError('Not an owned task')
                        with self.jobs.lock:
                            _,response=session.prepare('',request_id,control={'type':'cancel','task_id':msg['task_id']})
                            if not response.get('deduplicated'):self.jobs.cancel(msg['task_id'])
                        await emit({'type':'response',**response})
                    elif kind=='respawn':
                        if machine is not None:raise ValueError('Machine profile never respawns or rebinds actors')
                        if set(msg)!={'type','request_id'} or role!='controller' or not self.allow_respawn:
                            raise BCLError(Diagnostic('PERMISSION_DENIED','Explicit operator respawn permission required.',phase='gateway'))
                        with self.jobs.lock:
                            if any(j['session_id']==sid and j['result'] is None for j in self.jobs.jobs.values()):
                                raise BCLError(Diagnostic('SESSION_BUSY','Cancel/wait for owned actions before respawn.',phase='gateway'))
                        self.sampled_at=0.;sample=await self.observe()
                        if sample['actor_session']!=session.actor_session or sample['player_uuid']!=session.store.identity['player_id']:raise BridgeError('actor_session_changed')
                        if sample['lifecycle']!='player.dead':raise BCLError(Diagnostic('PLAYER_NOT_DEAD','Native respawn requires dead player.',phase='gateway'))
                        with self.jobs.lock:
                            _,response=session.prepare('',request_id,control={'type':'respawn'},accepted_control=True)
                            if not response.get('deduplicated'):session.update(request_id,status='accepted')
                        if not response.get('deduplicated'):
                            seen['lifecycle']='player.dead';seen['was_dead']=True;await event('player.dead',{'actor_session':session.actor_session})
                            await asyncio.to_thread(self.player.respawn,actor_session=session.actor_session)
                            session.update(request_id,status='submitted',reason='native_respawn_requested_not_outcome')
                            response={**response,'status':'submitted','reason':'Await player.respawned; explicitly bind a new session/actor token. No action replay.'}
                        await emit({'type':'response',**response})
                    elif kind=='reset':
                        if machine is not None:raise ValueError('Machine control cannot be reset or implicitly resumed')
                        if set(msg)!={'type','request_id'}:raise ValueError('Invalid reset fields')
                        response=self.jobs.submit(sid,'',request_id,session.store.identity,session.actor_session,reset=True)
                        await emit({'type':'response',**response})
                    else:raise ValueError('Unknown/client-forged message direction or type')
                except InputDenied as e:
                    if self.feedback and audit_record is not None:await asyncio.to_thread(self.feedback.outcome,audit_record,'rejected',str(e))
                    await emit({'type':'response','request_id':msg.get('request_id'),'status':'failed','diagnostics':[{'code':'INPUT_POLICY_DENIED','message':str(e)}]})
                except BCLError as e:
                    if self.feedback and audit_record is not None:await asyncio.to_thread(self.feedback.outcome,audit_record,'rejected',e.diagnostic.code)
                    await emit({'type':'response','request_id':0 if kind=='bind' else msg.get('request_id') if isinstance(msg,dict) else None,'status':'failed','diagnostics':[e.diagnostic.to_dict()]})
                except BridgeError as e:
                    if self.feedback and audit_record is not None:await asyncio.to_thread(self.feedback.outcome,audit_record,'unknown_no_retry',str(e))
                    fault=classify(e)
                    await emit({'type':'response','request_id':msg.get('request_id'),'status':'failed','diagnostics':[{'code':fault.value,'message':str(e)}]})
                    if fault in {FaultKind.ACTOR,FaultKind.TRANSPORT,FaultKind.INVARIANT}:
                        await ws.close(1011,'Actor or transport failure');return
                except (ValueError,TypeError,KeyError) as e:
                    if self.feedback and audit_record is not None:await asyncio.to_thread(self.feedback.outcome,audit_record,'rejected',str(e))
                    await emit({'type':'response','request_id':0 if kind=='bind' else msg.get('request_id') if isinstance(msg,dict) else None,'status':'failed',
                        'diagnostics':[{'code':'PROTOCOL_OR_SESSION_ERROR','message':str(e)[:256]}]})
        finally:
            if search_pages is not None:
                self.jobs.close_session(sid)
                await search_pages.close()
            if sid:
                self.sinks.pop(sid,None);self.jobs.close_session(sid);self.session_states[sid]='cleaning'
                task=asyncio.create_task(self._release_when_clean(sid,actor_key,role))
                self.reapers.add(task)
                def reaped(done):
                    self.reapers.discard(done)
                    if not done.cancelled() and done.exception() is not None:self.session_states[sid]='quarantined_cleanup_failed_restart_required'
                task.add_done_callback(reaped)
                await asyncio.wait({task},timeout=self.cleanup_grace)
                if not task.done():self.session_states[sid]='quarantined_until_cleanup'
            for task in resume_tasks:task.cancel()
            if resume_tasks:await asyncio.gather(*resume_tasks,return_exceptions=True)
            watching.cancel();sending.cancel();reporting.cancel()
            await asyncio.gather(watching,sending,reporting,return_exceptions=True);self.connections.discard(ws)
    async def _release_when_clean(self,sid,actor_key,role):
        while True:
            with self.jobs.lock:pending=any(j['session_id']==sid and j['result'] is None for j in self.jobs.jobs.values())
            if not pending:break
            await asyncio.sleep(.025)
        if self.profile=='machine-v1':
            try:
                if self.jobs.halted:raise RuntimeError('Uncertain cleanup')
                if role=='controller':
                    from .machine_control import fresh_release
                    await fresh_release(self.player,self.jobs.sessions[sid].actor_session)
            except Exception:
                self.jobs.halted=True;self.jobs.cancel()
                self.session_states[sid]='quarantined_cleanup_failed_restart_required';return
        self.jobs.release_session(sid);self.bound.discard(sid);self.roles.pop(sid,None)
        if role=='controller' and self.controllers.get(actor_key)==sid:self.controllers.pop(actor_key,None)
        self.session_states[sid]='released'
        if len(self.session_states)>128:
            for old in list(self.session_states):
                if old!=sid and self.session_states[old]=='released':self.session_states.pop(old)
                if len(self.session_states)<=128:break
    async def aclose(self):
        if self.auto_events:await self.auto_events.close()
        for ws in list(self.connections):await ws.close(1001,'Gateway stopping')
        self.jobs.close()
        if self.reapers:await asyncio.wait(self.reapers,timeout=self.cleanup_grace)
    async def listen(self,host,port,tls):
        if not ipaddress.ip_address(host).is_loopback:raise ValueError('BCL gateway currently supports loopback only')
        if not isinstance(tls,ssl.SSLContext) or tls.protocol!=ssl.PROTOCOL_TLS_SERVER or tls.minimum_version<ssl.TLSVersion.TLSv1_2:raise ValueError('Mandatory TLS server context required')
        server=await serve(self.handler,host,port,ssl=tls,process_request=self.authorize,origins=[None],
                           max_size=32768,max_queue=16,compression=None,open_timeout=5,close_timeout=5)
        try:
            if self.auto_events:await self.auto_events.start()
        except BaseException:
            server.close();await server.wait_closed();raise
        return server


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8880)
    p.add_argument('--certificate',required=True,type=Path);p.add_argument('--private-key',required=True,type=Path)
    p.add_argument('--feedback-directory',type=Path,help='Explicit private feature-request/input-audit store; never enables requested features')
    p.add_argument('--profile',choices=['legacy','machine-v1'],default='legacy',help='Explicit lean action/report/control profile; use fresh sessions')
    p.add_argument('--auto-events',action='store_true',help='Explicit native chat/observable-entity event collection; requires matching mod')
    p.add_argument('--allow-respawn',action='store_true',help='Explicitly permit fenced native respawn requests, never automatic replay')
    p.add_argument('--token-file',required=True,type=Path);p.add_argument('--state-directory',required=True,type=Path)
    a=p.parse_args()
    if a.token_file.is_symlink() or a.token_file.stat().st_mode&0o077:raise ValueError('Private token file required')
    token=a.token_file.read_text().strip();tls=server_tls(a.certificate,a.private_key)
    async def run():
        with Bridge.from_env() as native:
            gateway=BCLGateway(Player(native),token,a.state_directory,allow_respawn=a.allow_respawn,native_events=native if a.auto_events else None,feedback_directory=a.feedback_directory,profile=a.profile)
            server=await gateway.listen(a.host,a.port,tls)
            print(f'BCL/1 TLS gateway listening at wss://{a.host}:{server.sockets[0].getsockname()[1]}/v1',flush=True)
            try:await asyncio.Future()
            finally:server.close();await server.wait_closed();await gateway.aclose()
    asyncio.run(run())
if __name__=='__main__':main()
