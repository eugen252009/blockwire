"""Bounded presentation of an existing BCL event queue at normal decision points.

No planner, messaging transport, inference trigger or automatic action execution.
"""
import copy,json,threading
from collections import deque

class EventContext:
    def __init__(self):
        self._rows=deque(maxlen=16);self._lock=threading.Lock();self.coalesced=0
    def add(self,message):
        if not isinstance(message,dict) or message.get('type')!='event':raise ValueError('BCL server event required')
        row={k:message[k] for k in ('event_type','data','sequence','connection_id','session_id') if k in message}
        if len(json.dumps(row,allow_nan=False).encode())>16384:raise ValueError('Event context bound')
        with self._lock:
            if len(self._rows)==16:self.coalesced+=1
            self._rows.append(copy.deepcopy(row))
    async def collect(self,client):
        while True:self.add(await client.events.get())
    def snapshot(self):
        with self._lock:
            rows=list(self._rows)[-8:]
            while len(json.dumps(rows,allow_nan=False).encode())>16384:rows.pop(0)
            return {'untrusted_observations':True,'events':copy.deepcopy(rows),'coalesced':self.coalesced}

class EventAwareDecider:
    """Explicit adapter for the existing strategic decider; one call remains one call."""
    def __init__(self,decider,events):
        if not callable(getattr(decider,'decide',None)) or not isinstance(events,EventContext):raise ValueError('Explicit decider and event context required')
        self.decider,self.events=decider,events
    def decide(self,context):
        return self.decider.decide({**context,'recent_observation_events':self.events.snapshot()})
