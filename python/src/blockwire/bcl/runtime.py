"""BCL is a bounded batch dispatcher INTO AgentRuntime, not a second controller."""
from collections import deque,OrderedDict
import hashlib
import json
import math
from pathlib import Path
import re
import threading
import time
from uuid import uuid4
from .compiler import BCLError,Diagnostic,arguments,compile_bcl,registry_digest
from .registry import DEFAULT_PERMISSIONS
from .modal import Modal,ModalSession
from ..agent import AgentRuntime,SessionStore


def reachable_height(observation,x,z):
    nav=observation.get('navigation') or {}
    if not nav.get('ready') or nav.get('profile')!='stepped_full_blocks_v1':
        raise ValueError('No current stepped navigation proof')
    positions=[tuple(c['position']) for c in nav['cells']]
    source=tuple(nav['current_cell']);allowed={i for i,c in enumerate(nav['cells']) if not c['hazards']}
    if source not in positions or positions.index(source) not in allowed or not nav.get('current_center_access'):
        raise ValueError('No safe source cell')
    start=positions.index(source);edges={i:[] for i in allowed}
    for a,b in nav['edges']:
        if a in allowed and b in allowed:edges[a].append(b);edges[b].append(a)
    distances={start:0};queue=deque([start])
    while queue:
        i=queue.popleft()
        for j in edges[i]:
            if j not in distances:distances[j]=distances[i]+1;queue.append(j)
    candidates=[i for i in distances if positions[i][0]==math.floor(x) and positions[i][2]==math.floor(z)]
    if not candidates:raise ValueError('Target height is unobserved or unreachable')
    end=min(candidates,key=lambda i:(abs(positions[i][1]-observation['position'][1]),distances[i],positions[i][1]))
    return float(positions[end][1])


class BatchDriver:
    """Only expands the supplied ordered operations; no goals, branches or gameplay planning."""
    def __init__(self,program,registry,contexts=None):
        self.program,self.registry=program,registry
        self.contexts=contexts or tuple(Modal() for _ in program.operations)
        self.runtime=None;self.index=0;self.issued=None;self.results=[];self.started=False;self.error=None
    def error_at(self,code,message,op):
        self.error=Diagnostic(code,message,phase='execute',line=op.line,column=op.column,opcode=op.opcode,command=op.namespace+':'+op.command)
        raise BCLError(self.error)
    def failed(self,entry):
        op=self.program.operations[self.index];mode=self.contexts[self.index].error_mode
        self.results.append({'index':self.index,'command':op.namespace+':'+op.command,'status':entry['status'],'reason':entry['reason'],
                             'evidence':{k:v for k,v in entry.get('details',{}).items() if k in {'expected_face','actual_target','support','eye_position','face_rule','missing','current_cell','known_reachable_count','known_placement_poses','constraint','attempts','position'}}})
        self.index+=1;self.issued=None
        self.runtime.state['bcl_progress']={'completed':self.index,'results':self.results[:]}
        self.runtime.store.save(self.runtime.state)
        return mode=='continue'
    def decide(self,context):
        op=self.program.operations[min(self.index,len(self.program.operations)-1)]
        if registry_digest(self.registry)!=self.program.registry_digest:self.error_at('UNSUPPORTED_VERSION','Registry changed since compilation.',op)
        if not self.started:
            if self.runtime.state.get('bcl_started'):
                self.error_at('INTERRUPTED_SESSION','Execution ID was already activated. Never replay; inspect saved state and use an explicitly new execution ID.',op)
            self.runtime.state['bcl_started']={'program_digest':self.program.digest}
            self.runtime.store.save(self.runtime.state)  # Durable before even the first decision/effect.
            self.started=True
        if self.issued:
            skill,baseline=self.issued
            if context['completed_actions'].get(skill,0)>baseline:
                h=context['history'][-1]
                self.results.append({'index':self.index,'command':op.namespace+':'+op.command,'status':h['status'],'reason':h['reason']})
                self.index+=1;self.issued=None
                if skill in {'inspect_inventory','observe_environment'}:
                    fields=('inventory','carried') if skill=='inspect_inventory' else ('position','eye_position','yaw','pitch','health','hunger','holding','dimension','actor_session','player_uuid','in_world','alive','target','sight_target','visible_blocks','visible_interactables','visibility','navigation')
                    self.results[-1]['output']={k:context['observation'].get(k) for k in fields}
                    self.results[-1]['observed_at']=time.time()  # Capture before later operations, not at frame receipt.
                else:
                    self.results[-1]['position']=context['observation'].get('position')
                    details=context['history'][-1].get('details',{})
                    self.results[-1]['evidence']={k:details[k] for k in ('block','position','item','target') if k in details}
                self.runtime.state['bcl_progress']={'completed':self.index,'results':[{k:v for k,v in r.items() if k!='output'} for r in self.results]}
                self.runtime.store.save(self.runtime.state)
        if self.index==len(self.program.operations):return {'kind':'finish'}
        op=self.program.operations[self.index];command=self.registry.resolve(op.namespace,op.opcode)
        modal=self.contexts[self.index]
        values=arguments(op,command)
        for p in command.parameters:
            if p.default_kind=='static' and not (op.namespace=='core' and op.opcode=='M0' and p.name=='mode'):values.setdefault(p.name,p.default)
        if op.namespace=='core' and op.opcode=='M0':
            observation=context['observation'];position=observation['position']
            if modal.coordinate_mode=='relative':
                for axis,i in [('x',0),('y',1),('z',2)]:
                    if axis in values:values[axis]+=position[i]
            values.setdefault('x',position[0]);values.setdefault('z',position[2])
            if 'y' not in values:
                try:values['y']=reachable_height(observation,values['x'],values['z'])
                except ValueError as e:self.error_at('UNREACHABLE_TARGET',str(e),op)
            mode=values.pop('mode',modal.movement_mode)
            values.update(terrain=True,movement={'normal':'walk','fast':'run','sneak':'sneak'}[mode])
        if command.skill in self.registry.skills._definitions:
            values['timeout_seconds']=modal.timeout_seconds
            try:self.registry.skills.prepare(command.skill,values)
            except (ValueError,TypeError):self.error_at('INVALID_ARGUMENT','Resolved defaults violate the skill contract.',op)
        self.issued=(command.skill,context['completed_actions'].get(command.skill,0))
        self.runtime._publish(bcl_index=self.index,bcl_total=len(self.program.operations))
        return {'kind':'act','skill':command.skill,'parameters':values}


class BCLRunner:
    def __init__(self,source,registry,player,state_file,identity,actor_session,*,permissions=DEFAULT_PERMISSIONS,duration_seconds=120.,contexts=None):
        # All static checks BEFORE creating/opening session storage or reading Minecraft.
        self.program=compile_bcl(source,registry,permissions=permissions)
        if not isinstance(actor_session,str) or not 1<=len(actor_session)<=128:raise ValueError('Explicit actor_session required')
        self.program=type(self.program)(self.program.version,self.program.registry_digest,tuple(o for o in self.program.operations if registry.resolve(o.namespace,o.opcode).category=='skill'))
        if not self.program.operations:raise ValueError('Settings/events-only programs use ModalSession, not the game runner')
        if contexts is not None and (len(contexts)!=len(self.program.operations) or any(not isinstance(m,Modal) for m in contexts)):raise ValueError('Typed modal snapshot per operation required')
        driver=BatchDriver(self.program,registry,contexts);self.driver=driver
        store=SessionStore(state_file,identity)
        self.runtime=AgentRuntime(player,driver,store,'Execute supplied BCL/1 operations sequentially; no rollback.',
            registry=registry.skills,allowed_skills={registry.resolve(o.namespace,o.opcode).skill for o in self.program.operations if registry.resolve(o.namespace,o.opcode).skill in registry.skills._definitions},
            expected_actor_session=actor_session,completion_check=lambda _:driver.index==len(self.program.operations),
            max_decisions=len(self.program.operations)*2+4,max_failures=20,max_same_failure=5,
            failure_handler=driver.failed,
            duration_seconds=duration_seconds,action_timeout_seconds=min(120.,duration_seconds),decision_timeout_seconds=5.)
        driver.runtime=self.runtime
    def cancel(self):self.runtime.cancel()
    def status(self):return self.runtime.status()
    def run(self):
        result=self.runtime.run()
        completed=self.driver.results[:]
        # A failure prevents the next driver call; expose the verified outcome of that last operation.
        if self.driver.issued and result.get('history'):
            h=result['history'][-1]
            op=self.program.operations[min(self.driver.index,len(self.program.operations)-1)]
            completed.append({'index':self.driver.index,'command':op.namespace+':'+op.command,'status':h['status'],'reason':h['reason']})
        if result['status']=='succeeded' and any(r['status']!='succeeded' for r in completed):
            result.update(status='failed',reason='completed_with_errors',objective_verified=False)
        diagnostics=[]
        if self.driver.error:diagnostics=[self.driver.error.to_dict()]
        elif result['status']!='succeeded':
            failure=next((r for r in completed if r['status']!='succeeded'),None)
            reason=failure['reason'] if failure else result.get('history',[{}])[-1].get('reason',result['reason']) if result.get('history') else result['reason']
            code=('PLAYER_DEAD' if reason in {'player_dead','player_died_while_deciding'} else
                  'PLAYER_NOT_IN_WORLD' if reason=='not_in_world' else
                  'EXECUTION_CANCELLED' if result['status']=='cancelled' else
                  'EXECUTION_TIMEOUT' if reason in {'deadline_exceeded','mining_not_observed'} else
                  'ACTOR_MISMATCH' if reason in {'actor_session_changed','player_identity_mismatch','explicit_actor_rebind_required'} else
                  'UNREACHABLE_TARGET' if reason in {'no_known_safe_route','stuck','vertical_route_unsupported'} else 'POSTCONDITION_FAILED')
            op=self.program.operations[failure['index'] if failure else min(self.driver.index,len(self.program.operations)-1)]
            diagnostics=[Diagnostic(code,reason,phase='execute',line=op.line,column=op.column,opcode=op.opcode,command=op.namespace+':'+op.command).to_dict()]
        program_verified=bool(result.get('objective_verified')) and result['status']=='succeeded'
        result['objective_verified']=False  # BCL cannot attest an external free-text build/Survival goal.
        result['program_verified']=program_verified
        result['verification_scope']='BCL operation postconditions only; NOT the external agent objective'
        if result.get('reason')=='objective_postcondition_observed':result['reason']='bcl_program_completed'
        return {**result,'language':self.program.version,'program_digest':self.program.digest,'operations':completed,
                'diagnostics':diagnostics,'rollback_performed':False}


class BCLJobs:
    """One FIFO actor queue; per-session modal journals. All gameplay still uses AgentRuntime."""
    def __init__(self,registry,player,state_directory,permissions=DEFAULT_PERMISSIONS):
        self.registry,self.player,self.directory,self.permissions=registry,player,Path(state_directory),permissions
        self.jobs=OrderedDict();self.sessions={};self.queue=deque();self.active=None;self.worker=False
        self.lock=threading.RLock()
    def ensure_idle(self):
        with self.lock:
            if self.active or self.queue:raise RuntimeError('A BCL batch owns player control')
    def session(self,session_id,identity,actor_session):
        if not isinstance(session_id,str) or not re.fullmatch(r'[a-zA-Z0-9_.:-]{1,128}',session_id):raise ValueError('Bounded session ID required')
        with self.lock:
            if session_id in self.sessions:
                s=self.sessions[session_id]
                if s.store.identity!=identity or s.actor_session!=actor_session:raise ValueError('BCL session identity mismatch')
                return s
            if len(self.sessions)>=32:raise ValueError('Session bound exceeded')
            key=hashlib.sha256(session_id.encode()).hexdigest()
            s=ModalSession(self.registry,self.directory/(key+'.modal.sqlite'),identity,actor_session,self.permissions)
            self.sessions[session_id]=s;return s
    def submit(self,session_id,source,request_id,identity,actor_session,*,duration_seconds=120.,reset=False):
        compiled=None if reset else compile_bcl(source,self.registry,permissions=self.permissions)
        if type(duration_seconds) not in (float,int) or not .1<=duration_seconds<=1800:raise ValueError('Bounded duration required')
        with self.lock:
            if len(self.queue)>=16 and compiled and any(self.registry.resolve(o.namespace,o.opcode).category=='skill' for o in compiled.operations):raise ValueError('Task queue full')
            s=self.session(session_id,identity,actor_session)
            if reset and any(j['session_id']==session_id and j['result'] is None for j in self.jobs.values()):raise ValueError('Cancel/wait for own tasks before reset')
            prepared,response=s.prepare(source,request_id,reset=reset)
            if prepared is None:return dict(response)
            identifier='bcl:'+str(uuid4())
            s.update(request_id,task_id=identifier)
            response={**response,'task_id':identifier,'id':identifier}
            key=hashlib.sha256(json.dumps([session_id,request_id]).encode()).hexdigest()
            self.jobs[identifier]={'runner':None,'result':None,'session_id':session_id,'prepared':prepared,
                                   'cancelled':False,'duration':duration_seconds,'path':self.directory/(key+'.action.sqlite')}
            self.queue.append(identifier)
            while len(self.jobs)>64:
                old=next(iter(self.jobs))
                if self.jobs[old]['result'] is None:break
                self.jobs.pop(old)
            if not self.worker:
                self.worker=True
                try:threading.Thread(target=self._work,daemon=True,name='blockwire-bcl').start()
                except BaseException:self.worker=False;self.queue.remove(identifier);self.jobs[identifier]['cancelled']=True;raise
            return response
    def start(self,source,agent_id,world_id,player_uuid,actor_session,execution_id,duration_seconds=120.):
        # Backwards-compatible MCP signature: execution_id is a monotonic request integer.
        identity={'agent_id':agent_id,'world_id':world_id,'player_id':player_uuid}
        session_id=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
        if isinstance(execution_id,str) and execution_id.isdecimal():execution_id=int(execution_id)
        return self.submit(session_id,source,execution_id,identity,actor_session,duration_seconds=duration_seconds)
    def _work(self):
        while True:
            with self.lock:
                if not self.queue:self.active=None;self.worker=False;return
                identifier=self.queue.popleft();self.active=identifier;j=self.jobs[identifier]
                s=self.sessions[j['session_id']];p=j['prepared']
            try:
                with self.lock:s.update(p.request_id,status='running')
                if j['cancelled']:result={'status':'cancelled','reason':'cancelled_before_execution','rollback_performed':False}
                else:
                    runner=BCLRunner(p.source,self.registry,self.player,j['path'],s.store.identity,s.actor_session,
                                     permissions=self.permissions,duration_seconds=j['duration'],contexts=p.contexts)
                    with self.lock:
                        j['runner']=runner
                        if j['cancelled']:runner.cancel()
                    result=runner.run()
            except BaseException as e:result={'status':'failed','reason':'worker_terminated','error_type':type(e).__name__,'rollback_performed':False}
            with self.lock:
                j['result']=result
                try:s.update(p.request_id,status='completed' if result['status']=='succeeded' else result['status'],
                             reason=result.get('reason'),diagnostics=result.get('diagnostics',[]),task_id=identifier)
                except Exception:
                    j['result']={'status':'failed','reason':'state_store_error'}
                    for queued in self.queue:self.jobs[queued]['cancelled']=True
                self.active=None
    def status(self,identifier):
        with self.lock:
            j=self.jobs[identifier]
            if j['result'] is not None:return {'id':identifier,**j['result']}
            return {'id':identifier,**(j['runner'].status() if j['runner'] else {'status':'queued'})}
    def cancel(self,identifier=None):
        with self.lock:
            if identifier is None:
                pending=[key for key,j in self.jobs.items() if j['result'] is None]
                for key in pending:self.cancel(key)
                return {'cancellation_requested':bool(pending)}
            j=self.jobs[identifier];j['cancelled']=True
            if j['runner']:j['runner'].cancel()
            return {'id':identifier,'cancellation_requested':j['result'] is None}
    def close_session(self,session_id):
        with self.lock:
            for identifier,j in self.jobs.items():
                if j['session_id']==session_id and j['result'] is None:self.cancel(identifier)
    def release_session(self,session_id):
        with self.lock:
            if any(j['session_id']==session_id and j['result'] is None for j in self.jobs.values()):raise RuntimeError('Session cleanup pending')
            s=self.sessions.pop(session_id,None)
            if s:s.close()
    def close(self):
        with self.lock:
            for identifier,j in self.jobs.items():
                if j['result'] is None:self.cancel(identifier)
            for sid in list(self.sessions):
                if not any(j['session_id']==sid and j['result'] is None for j in self.jobs.values()):self.release_session(sid)
