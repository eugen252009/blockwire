"""Read-only search pages outside the action FIFO; one native page in flight per gateway."""
import asyncio
from ..errors import classify, FaultKind
from ..skills.search import SearchPage


class SearchPages:
    def __init__(self, gateway, session, machine, emit, ws):
        self.gateway, self.session, self.machine = gateway, session, machine
        self.emit, self.ws = emit, ws
        self.task = None; self.closing = False

    async def start(self, identifier, parameters):
        g = self.gateway
        params = SearchPage.model_validate(parameters).model_dump(exclude_none=True)
        if 'observe' not in g.jobs.permissions:raise ValueError('Search requires observe permission')
        if g.failed or g.jobs.halted or self.machine.state in {'requested', 'quarantined'}:
            raise ValueError('Search unavailable during interruption/quarantine')
        if g.search_busy:raise ValueError('One native search page at a time; no automatic retry')
        with g.jobs.lock:
            _, response = self.session.prepare('', identifier, control={'type':'search','parameters':params}, accepted_control=True)
        if response.get('deduplicated'):
            await self.emit({'type':'response', **response, 'cached':True});return
        g.search_busy = True
        try:await self.emit({'type':'response', **response, 'execution_mode':'sync'})
        except BaseException:g.search_busy = False;raise
        self.task = asyncio.create_task(self._run(identifier, params, self.machine.generation))

    async def _run(self, identifier, parameters, generation):
        g = self.gateway
        try:
            result = await asyncio.to_thread(g.player.search_page, actor_session=self.session.actor_session, **parameters)
            if self.closing or generation != self.machine.generation:
                response = {'status':'cancelled', 'diagnostics':[{'code':'SEARCH_INTERRUPTED'}]}
            else:response = {'status':'completed', 'result':result}
        except Exception as error:
            fault = classify(error)
            response = {'status':'failed', 'diagnostics':[{'code':fault.value, 'message':str(error)[:256]}]}
            if fault in {FaultKind.ACTOR, FaultKind.TRANSPORT, FaultKind.INVARIANT}:
                g.jobs.close_session(self.machine.sid)
                await self.ws.close(1011, 'Search actor/transport failure')
        finally:
            g.search_busy = False
        try:
            with g.jobs.lock:self.session.update(identifier, **response)
            if not self.closing:await self.emit({'type':'response', 'request_id':identifier, **response})
        except Exception:
            await self.ws.close(1011, 'Search result persistence/delivery failed')

    async def close(self):
        self.closing = True
        # Do not abandon/replay a running native RPC. It owns no controls, and its
        # actor fence is still checked by Minecraft. Action cancellation is separate.
        if self.task is not None:await asyncio.gather(self.task, return_exceptions=True)
