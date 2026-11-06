"""Language-independent JSON/BCL-over-TLS-WebSocket reference SDK. No game controller."""
import asyncio,json
from websockets.asyncio.client import connect
from ..client import Bridge
from ..llm import strict_json

class BCLClient:
    def __init__(self,url,token,certificate,*,session_id,agent_id,world_id,player_uuid,actor_session,timeout=10.,role='controller',profile='legacy'):
        self.trust=Bridge(token,url,certificate=certificate)
        self.bind={'type':'bind','language':'BCL/1','session_id':session_id,'agent_id':agent_id,'world_id':world_id,
                   'player_uuid':player_uuid,'actor_session':actor_session}
        if profile not in {'legacy','machine-v1'}:raise ValueError('Unknown profile')
        self.profile=profile
        if profile!='legacy':self.bind['profile']=profile
        if role not in {'controller','observer'}:raise ValueError('Invalid role')
        if role!='controller':self.bind['role']=role
        if type(timeout) not in (int,float) or not .1<=timeout<=1800:raise ValueError('Bounded timeout required')
        self.timeout=timeout;self.ws=None;self.reader=None;self.next_id=1;self.modal={};self.coordinate_context={};self.responses={};self.tasks={}
        self.events=asyncio.Queue(maxsize=64);self.progress=asyncio.Queue(maxsize=64);self.lock=asyncio.Lock()
        self.wire_sequence=0;self.connection_id=None;self.control_state=None;self.control_generation=0
    def _future(self):
        future=asyncio.get_running_loop().create_future()
        future.add_done_callback(lambda f:None if f.cancelled() else f.exception())
        return future
    async def __aenter__(self):
        self.ws=await connect(self.trust.url,ssl=self.trust.tls_context(),server_hostname=Bridge.TLS_NAME,
            additional_headers={'Authorization':'Bearer '+self.trust._token},proxy=None,max_size=32768,max_queue=16,compression=None,open_timeout=self.timeout)
        future=self._future();self.responses[0]=(future,future)
        self.reader=asyncio.create_task(self._read());await self.ws.send(json.dumps(self.bind))
        try:
            response=await asyncio.wait_for(future,self.timeout)
            if response['status']!='bound':raise RuntimeError(str(response.get('diagnostics')))
            if response.get('profile','legacy')!=self.profile:raise RuntimeError('Gateway profile mismatch')
            self.next_id=response['last_request_id']+1;self.modal=response['modal'];self.coordinate_context=response.get('coordinate_context',{});return self
        except BaseException:await self.__aexit__(None,None,None);raise
    async def __aexit__(self,*_):
        if self.ws:await self.ws.close()
        if self.reader:
            self.reader.cancel();await asyncio.gather(self.reader,return_exceptions=True)
    async def _read(self):
        try:
            async for body in self.ws:
                message=strict_json(body)
                if self.profile=='machine-v1':
                    if (message.get('language')!='BCL/1' or message.get('type') not in {'response','event','progress','error'}
                        or message.get('session_id')!=self.bind['session_id'] or type(message.get('sequence'))is not int
                        or message['sequence']!=self.wire_sequence+1 or not isinstance(message.get('connection_id'),str)
                        or (self.connection_id is not None and message['connection_id']!=self.connection_id)):
                        raise RuntimeError('Machine event/response stream identity or sequence gap')
                    self.connection_id=message['connection_id'];self.wire_sequence=message['sequence']
                    generation=message.get('generation',message.get('data',{}).get('generation'))
                    if type(generation)is int:self.control_generation=max(self.control_generation,generation)
                    if message.get('control_state') in {'ready','requested','released','quarantined'}:self.control_state=message['control_state']
                    if message.get('event_type')=='control.released':self.control_state='released'
                    if message.get('event_type') in {'control.quarantined','player.dead','player.respawned','player.not_in_world','transport.disconnected'}:self.control_state='quarantined'
                if message.get('type')=='progress':
                    if self.progress.full():self.progress.get_nowait()  # Coalesce old display-only progress, never terminal responses/events.
                    self.progress.put_nowait(message);continue
                if message.get('type')=='event':
                    try:self.events.put_nowait(message)
                    except asyncio.QueueFull:raise RuntimeError('Client event queue overflow')
                    continue
                request=message.get('request_id');task=message.get('task_id')
                if message.get('modal'):self.modal=message['modal']
                if message.get('coordinate_context'):self.coordinate_context=message['coordinate_context']
                if task:
                    if task not in self.tasks:self.tasks[task]=self._future()
                    f=self.tasks[task]
                    if len(self.tasks)>128:
                        for old in list(self.tasks):
                            if old!=task and self.tasks[old].done():del self.tasks[old]
                            if len(self.tasks)<=64:break
                    if message.get('status') not in {'accepted','running'} and not f.done():f.set_result(message)
                pair=self.responses.get(request)
                if pair:
                    accepted,completed=pair
                    if not accepted.done():accepted.set_result(message)
                    if message.get('status') not in {'accepted','running'} and not completed.done():completed.set_result(message)
        finally:
            if self.ws:await self.ws.close()
            for pair in self.responses.values():
                for future in pair:
                    if not future.done():future.set_exception(ConnectionError('BCL connection lost; no automatic reconnect/replay'))
            for future in self.tasks.values():
                if not future.done():future.set_exception(ConnectionError('BCL task outcome uncertain after disconnect'))
    async def _request(self,message,request_id=None,*,wait_for_completion=True):
        if self.ws is None:raise RuntimeError('Connect explicitly first')
        async with self.lock:
            identifier=self.next_id if request_id is None else request_id
            if type(identifier) is not int or not 1<=identifier<=9007199254740991:raise ValueError('Safe positive request ID required')
            self.next_id=max(self.next_id,identifier+1)
            if identifier in self.responses:raise ValueError('Request ID already pending in this connection; reconnect to retrieve cached result')
            if len(self.responses)>128:
                for key in list(self.responses):
                    if all(f.done() for f in self.responses[key]):del self.responses[key]
                    if len(self.responses)<=64:break
            if len(self.responses)>128:raise ValueError('Client request bound exceeded')
            pair=(self._future(),self._future());self.responses[identifier]=pair
            await self.ws.send(json.dumps({**message,'request_id':identifier},allow_nan=False))
        accepted=await asyncio.wait_for(asyncio.shield(pair[0]),self.timeout)
        if wait_for_completion and accepted.get('status')=='accepted' and accepted.get('execution_mode',accepted.get('modal',self.modal).get('execution_mode','sync'))=='sync':
            return await asyncio.wait_for(asyncio.shield(pair[1]),self.timeout)
        return accepted
    async def send(self,source,*,request_id=None):return await self._request({'type':'bcl','source':source},request_id)
    async def submit(self,source,*,request_id=None):
        """Return the existing accepted receipt before sync completion, for owned cancel.

        Does not change wire mode, queue semantics, IDs or gameplay verification.
        Call wait(task_id) for the terminal outcome; never resubmit on uncertainty.
        """
        return await self._request({'type':'bcl','source':source},request_id,wait_for_completion=False)
    async def action(self,name,parameters,*,request_id=None):
        """Typed machine command; returns admission, not a gameplay outcome."""
        if self.profile!='machine-v1':raise ValueError('Machine profile required')
        return await self._request({'type':'action','name':name,'parameters':parameters},request_id,wait_for_completion=False)
    async def compose(self,actions,*,request_id=None):
        if self.profile!='machine-v1':raise ValueError('Machine profile required')
        from ..machine_composition import source
        return await self.submit(source(actions),request_id=request_id)
    async def search_page(self,parameters,*,request_id=None):
        """One additional bounded sight page, outside the action FIFO. No replay."""
        from ..skills.search import SearchPage
        from ..skills.core import SkillStop
        if self.profile!='machine-v1':raise ValueError('Machine profile required')
        params=SearchPage.model_validate(parameters).model_dump(exclude_none=True)
        reply=await self._request({'type':'search','parameters':params},request_id)
        if reply.get('status')!='completed':
            diagnostic=next(iter(reply.get('diagnostics',[])),{})
            raise SkillStop('cancelled' if reply.get('status')=='cancelled' else 'blocked',
                diagnostic.get('message',diagnostic.get('code','search_unavailable')))
        return reply['result']
    async def search(self,parameters,*,check=lambda:None):
        from ..skills.search import Search,search_async
        from ..skills.core import SkillStop
        goal=Search.model_validate(parameters);generation=self.control_generation
        def guard():
            check()
            if self.control_generation!=generation:raise SkillStop('cancelled','search_interrupted')
            if self.control_state in {'requested','quarantined'}:raise SkillStop('blocked','search_control_unavailable')
        return (await search_async(self.search_page,goal,self.bind['actor_session'],guard)).model_dump(mode='json')
    async def report(self,events,*,request_id=None):
        """Configure independent change reporting; snapshots arrive through events."""
        return await self._request({'type':'report','events':events},request_id)
    async def interrupt(self,*,request_id=None):
        return await self._request({'type':'interrupt'},request_id)
    async def resume(self,*,request_id=None):
        return await self._request({'type':'resume'},request_id)
    async def request_feature(self,feedback_id,feedback,*,request_id=None):
        """Record a bounded operator-review proposal, never code/action execution."""
        return await self._request({'type':'feedback','feedback_id':feedback_id,'feedback':feedback},request_id)
    async def feedback_status(self,feedback_id,*,request_id=None):
        return await self._request({'type':'feedback_status','feedback_id':feedback_id},request_id)
    async def cancel(self,task_id,*,request_id=None):return await self._request({'type':'cancel','task_id':task_id},request_id)
    async def respawn(self,*,request_id=None):return await self._request({'type':'respawn'},request_id)
    async def reset(self,*,request_id=None):return await self._request({'type':'reset'},request_id)
    async def wait(self,task_id):
        if task_id not in self.tasks:self.tasks[task_id]=self._future()
        future=self.tasks[task_id]
        return await asyncio.wait_for(asyncio.shield(future),self.timeout)
