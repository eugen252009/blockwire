"""External-model project orchestration over the existing BCL TLS client.

This layer supplies persistent context, budgets and verification, never a build
sequence, resource choice, Minecraft controller, or automatic reconnection.
"""
import asyncio
import hashlib
import json
import time
from pydantic import Field
from .projects import Strict,ProjectPlan
from .bcl import compile_bcl
from .bcl.compiler import arguments,BCLError
from .bcl.registry import DEFAULT_PERMISSIONS

class ProjectDecision(Strict):
    source: str = Field(default='',max_length=16384)
    note: str = Field(default='',max_length=1024)
    plan: ProjectPlan | None = None
    finish: bool = False
    begin_verification: bool = False

class ProjectAgent:
    def __init__(self,client,journal,decider,registry,*,max_calls=60,duration=1800.,max_stagnation=10,audit=None,permissions=DEFAULT_PERMISSIONS):
        if type(max_calls)is not int or not 1<=max_calls<=100 or type(max_stagnation)is not int or not 1<=max_stagnation<=20 or type(duration)not in (int,float) or not .1<=duration<=3600:raise ValueError('Bounded project activation required')
        self.permissions=frozenset(permissions)
        if not self.permissions<=DEFAULT_PERMISSIONS:raise ValueError('Unknown project permissions')
        self.client,self.journal,self.decider,self.registry=client,journal,decider,registry
        self.max_calls,self.duration,self.max_stagnation=max_calls,duration,max_stagnation
        self.audit=audit;self.cancelled=False;self.active=None;self.last_response=None;self.last_action_result=None;self._started=False;self.inspection_sweeps=0
    def cancel(self):
        self.cancelled=True
        if getattr(self,'task',None):self.loop.call_soon_threadsafe(self.task.cancel)
    def check(self):
        if self.cancelled:raise RuntimeError('project_cancelled')
        if time.monotonic()>=self.deadline:raise RuntimeError('project_deadline')
    async def exchange(self,source,*,intent=False):
        self.check()
        try:program=compile_bcl(source,self.registry,permissions=self.permissions)
        except BCLError as error:
            if self.audit:self.audit({'source':source,'response':{'status':'rejected','phase':'compile','effects_started':False,'diagnostics':[error.diagnostic.to_dict()]}})
            raise
        if self.journal.p['counters']['operations']+len(program.operations)>512:raise RuntimeError('project_operation_budget')
        mutates=any(self.registry.resolve(o.namespace,o.opcode).skill not in {'observe_environment','inspect_inventory','aim_at','walk_to',None} for o in program.operations)
        identifier=self.client.next_id
        if intent:
            costs={'placement_requests':0,'gather_requests':0,'craft_batches':0}
            for op in program.operations:
                command=self.registry.resolve(op.namespace,op.opcode);values=arguments(op,command)
                if command.skill in {'place_block','place_at'}:costs['placement_requests']+=1
                if command.skill in {'gather_block','gather_wood','remove_block'}:costs['gather_requests']+=values.get('count',1)
                if command.skill=='craft_item':costs['craft_batches']+=values.get('batches',1)
            if costs['placement_requests'] and self.journal.policy=='enclosure_v1' and not self.journal.p.get('observed_unfulfilled'):
                raise ValueError('Project baseline unknown: observe a currently unmet planned requirement before construction')
            caps={'placement_requests':256,'gather_requests':512,'craft_batches':128}
            if any(self.journal.p['counters'].get(k,0)+v>caps[k] for k,v in costs.items()):raise ValueError('Persistent project material/action request budget exhausted')
            for k,v in costs.items():self.journal.p['counters'][k]=self.journal.p['counters'].get(k,0)+v
            self.journal.intent(source,identifier,self.client.bind['session_id'],len(program.operations))
        else:
            if mutates:raise ValueError('Observation exchange cannot mutate the world')
            self.journal.p['counters']['operations']+=len(program.operations);self.journal.save()
        # The pending ID is durable before send. Lost acknowledgements are never
        # auto-replayed; caller must explicitly reconnect and freshly reconcile.
        async def execute():
            response=await self.client.send(source,request_id=identifier)
            if response.get('status')=='accepted':
                self.active=response['task_id']
                try:response=await self.client.wait(self.active)
                except asyncio.CancelledError:
                    await asyncio.wait_for(self.client.cancel(self.active),5.)
                    raise
                finally:self.active=None
            return response
        try:response=await asyncio.wait_for(execute(),max(.001,self.deadline-time.monotonic()))
        except (asyncio.CancelledError,TimeoutError):
            if getattr(self.client,'ws',None):await asyncio.wait_for(self.client.ws.close(),5.)
            raise
        self.last_response=response
        if self.audit:self.audit({'source':source,'response':response})
        if intent:
            self.journal.result(response)
            actual=response.get('result',{})
            self.last_action_result={'status':response.get('status'),'diagnostics':actual.get('diagnostics',response.get('diagnostics',[])),
                'operations':[{k:o.get(k) for k in ('command','status','reason','evidence')} for o in actual.get('operations',[])]}
        else:
            for op in response.get('result',{}).get('operations',[]):
                scene=op.get('output',{})
                if scene.get('visibility'):self.journal.observe(scene,observed_at=op.get('observed_at'))
                if 'inventory' in scene:self.journal.inventory(scene['inventory'])
            self.journal.save()
        codes={d.get('code') for d in response.get('result',{}).get('diagnostics',response.get('diagnostics',[]))}
        if codes & {'PLAYER_DEAD','PLAYER_NOT_IN_WORLD','ACTOR_MISMATCH','TRANSPORT_ERROR'}:
            self.journal.invalidate('explicit_lifecycle_rebind_required');raise RuntimeError('explicit_lifecycle_rebind_required')
        self.check()
        return response
    async def run(self):
        if self._started:raise RuntimeError('Project runtime activations cannot be reused')
        self._started=True
        self.task=asyncio.current_task();self.loop=asyncio.get_running_loop()
        self.deadline=time.monotonic()+self.duration;stagnant=0;previous=None
        result={'status':'OBJECTIVE_INCOMPLETE','reason':'model_call_budget'}
        try:
            # Bind is the operator's explicit fresh native identity proof. A read
            # occurs before any model decision; the journal never reuses old proof.
            await self.exchange('S0 sync\nS1 absolute\nS3 stop\nV0\nI0')
            catalog=[self.registry.describe(op) for op in ['M0','M2','C0','C1','C2','C3','I0','I1','I3','I4','V0','V1','V2','S0','S1','S2','S3','S4'] if self.registry.resolve('core',op).permissions<=self.permissions]
            for _ in range(self.max_calls):
                self.check();summary=self.journal.summary()
                if summary['status']=='OBJECTIVE_VERIFIED':result={'status':'OBJECTIVE_VERIFIED','reason':'trusted_project_postcondition'};break
                if self.journal.p['counters']['model_calls']>=160:result['reason']='persistent_model_budget';break
                # Re-seeing an expired old surface is not new project progress.
                progress=[self.journal.p['revision'],self.journal.p.get('activation_confirmed',[]),self.journal.p['counters']['placement_events']]
                fingerprint=hashlib.sha256(json.dumps([progress,self.journal.p['inventory']],sort_keys=True).encode()).hexdigest()
                stagnant=stagnant+1 if fingerprint==previous else 0;previous=fingerprint
                if stagnant>=self.max_stagnation:result['reason']='no_relevant_progress_budget';break
                self.journal.p['counters']['model_calls']+=1;self.journal.save()
                payload={'project':summary,'registry':catalog,'latest_result':self.last_response,'last_action_result':self.last_action_result,
                         'remaining_seconds':max(0.,self.deadline-time.monotonic()),'stagnant_decisions':stagnant,
                         'contract':'COMMAND_COMPLETED/BATCH_COMPLETED are not OBJECTIVE_VERIFIED. Model finish is a proposal only. Unknown blocks require observations. Choose all design, resources, access and repairs yourself.'}
                try:raw=await asyncio.wait_for(asyncio.to_thread(self.decider.decide,payload),min(180.,max(.1,self.deadline-time.monotonic())))
                except TimeoutError:raise RuntimeError('model_decision_timeout') from None
                self.check()
                try:
                    decision=ProjectDecision.model_validate(raw)
                    if decision.plan:
                        revision=self.journal.p['revision'];self.journal.revise(decision.plan.model_dump())
                        if self.journal.p['revision']!=revision:await self.exchange('V0\nI0')  # Fresh target baseline, never infer an empty site from the plan.
                    if decision.note:self.journal.event('model_note',note=decision.note)
                    if decision.begin_verification and not self.journal.p.get('final_sweep'):self.journal.begin_verification()
                    if decision.source:
                        if not self.journal.p['plan']:
                            await self.exchange(decision.source,intent=False)
                        else:await self.exchange(decision.source,intent=True)
                    self.journal.reconcile()
                    # Start a fresh sweep once every declared block has evidence.
                    # The model chooses camera/walking/inspection actions, not us.
                    if self.journal.p['progress'] and all(r['status']=='correct' for r in self.journal.p['progress'].values()) and not self.journal.p.get('final_sweep'):
                        self.journal.begin_verification()
                    if (decision.begin_verification or self.journal.p.get('final_sweep')) and self.journal.p['status']!='OBJECTIVE_VERIFIED' and self.inspection_sweeps<3:
                        remaining=512-self.journal.p['counters']['operations']
                        if remaining>0:
                            from .project_inspection import inspect_project
                            self.inspection_sweeps+=1
                            outcome=await inspect_project(self.journal,self.exchange,max_operations=min(64,remaining),check=self.check)
                            self.journal.event('independent_inspection',**outcome)
                    if decision.finish and self.journal.p['status']!='OBJECTIVE_VERIFIED':self.journal.event('OBJECTIVE_INCOMPLETE',reason='model_finish_not_independent_proof')
                except ValueError as error:
                    if self.journal.p['pending']:raise RuntimeError('uncertain_project_intent_requires_explicit_rebind') from error
                    self.last_response={'status':'rejected','reason':str(error)[:2048],'diagnostics':[error.diagnostic.to_dict()] if isinstance(error,BCLError) else []};self.last_action_result=self.last_response;self.journal.event('plan_or_program_rejected',reason=str(error)[:512])
                await self.exchange('V0\nI0')
                self.journal.save()
            if self.journal.summary()['status']=='OBJECTIVE_VERIFIED':result={'status':'OBJECTIVE_VERIFIED','reason':'trusted_project_postcondition'}
        except asyncio.CancelledError:
            self.cancelled=True
            if self.active:
                # Existing gateway cancellation/owned cleanup, never raw stop of
                # someone else's controls. Disconnect also cancels owned work.
                await self.client.cancel(self.active)
            raise
        except (ConnectionError,TimeoutError):
            self.journal.invalidate('uncertain_transport_pending_intent_not_replayed');raise
        finally:self.journal.save()
        summary=self.journal.summary();verified=summary['status']=='OBJECTIVE_VERIFIED'
        if result['status']=='OBJECTIVE_VERIFIED' and not verified:result['reason']='evidence_expired_before_return'
        return {**result,'status':summary['status'],'objective_verified':verified,'project':summary}
