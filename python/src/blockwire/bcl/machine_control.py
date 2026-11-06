"""Out-of-band owned cancellation barrier. No action executor or automatic resume."""
import asyncio
from ..machine_actions import confirm_release


async def fresh_release(player,actor):
    """Two ordered native ticks; the second must prove no actual/owned inputs."""
    return await asyncio.to_thread(confirm_release,player,actor)


class MachineControl:
    def __init__(self,jobs,session_id,actor,player):
        self.jobs,self.sid,self.actor,self.player=jobs,session_id,actor,player
        self.state='ready';self.generation=0;self.lock=asyncio.Lock()

    def interrupt(self):
        # Cancellation happens before disk work or an awaited native observation.
        self.generation+=1
        if self.state!='quarantined':self.state='requested'
        self.jobs.close_session(self.sid)
        return {'control_state':self.state,'cancellation_requested':True,'released':False,'generation':self.generation}

    def quarantine(self):
        self.state='quarantined';self.jobs.halted=True;self.jobs.cancel()

    def admit(self):
        if self.state!='ready' or self.jobs.halted:
            raise ValueError('Controller interrupted/quarantined; no action admission')

    async def advance(self):
        async with self.lock:
            if self.state!='requested':return None
            generation=self.generation
            with self.jobs.lock:
                rows=[j for j in self.jobs.jobs.values() if j['session_id']==self.sid]
                if any(j['result'] is None for j in rows):return None
                uncertain=self.jobs.halted or any(j['result'].get('cleanup')!='released'
                    and j['result'].get('reason')!='cancelled_before_execution' for j in rows)
            try:
                if uncertain:raise RuntimeError('Uncertain owned cleanup')
                tick=await fresh_release(self.player,self.actor)
            except Exception:
                self.quarantine()
                return ('control.quarantined',{'actor_session':self.actor,'reason':'UNKNOWN_NO_RETRY','generation':self.generation})
            if self.jobs.halted:
                self.quarantine()
                return ('control.quarantined',{'actor_session':self.actor,'reason':'UNKNOWN_NO_RETRY','generation':self.generation})
            if generation!=self.generation:return None
            self.state='released'
            return ('control.released',{'actor_session':self.actor,'tick':tick,'generation':generation,'requires_explicit_resume':True})

    async def resume(self):
        async with self.lock:
            if self.state!='released' or self.jobs.halted:raise ValueError('Fresh confirmed cleanup required')
            generation=self.generation
            try:tick=await fresh_release(self.player,self.actor)
            except Exception:
                self.quarantine();raise
            if self.jobs.halted:self.quarantine();raise RuntimeError('Dispatcher quarantined')
            if generation!=self.generation:raise ValueError('Interrupted during resume')
            self.state='ready'
            return {'control_state':'ready','release_tick':tick,'old_actions_replayed':False}
