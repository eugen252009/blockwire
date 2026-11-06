"""Native observation adapters into the EXISTING gateway Event stream, not a broker."""
import asyncio,math,time
from dataclasses import dataclass,field
from ..controller import Event
from .event_policy import ChatFilter

EVENTS={'player.chat':'E108','player.nearby.enter':'E109','player.nearby.leave':'E110',
        'entity.hostile.enter':'E111','entity.hostile.leave':'E112','reporting.metrics':'E113'}

def register_events(registry):
    for name,opcode in EVENTS.items():
        if name not in registry.events:registry.register_event(name,opcode,_core=True)

@dataclass(frozen=True)
class ReportingPolicy:
    radius:float=16.
    min_interval:float=.25
    players:frozenset[str]=frozenset()
    chat:ChatFilter=field(default_factory=lambda:ChatFilter('all'))
    def __post_init__(self):
        if type(self.radius) not in (int,float) or not math.isfinite(self.radius) or not 0<self.radius<=24:raise ValueError('Observation radius must be 0..24')
        if type(self.min_interval) not in (int,float) or not math.isfinite(self.min_interval) or not .25<=self.min_interval<=5:raise ValueError('Reporting interval must be .25..5 seconds')
        if not isinstance(self.players,frozenset) or len(self.players)>32 or any(not isinstance(p,str) or not 1<=len(p)<=128 for p in self.players):raise ValueError('Bounded immutable player UUID allowlist required')
        if not isinstance(self.chat,ChatFilter):raise ValueError('Validated ChatFilter required')

class AutoReporter:
    """One native source per gateway. Queues/timing independent of any LLM/BCL task."""
    def __init__(self,gateway,bridge,policy=None):
        self.gateway,self.bridge=gateway,bridge;self.policy=policy or (lambda identity:ReportingPolicy())
        if not callable(self.policy):raise ValueError('Trusted per-session reporting policy factory required')
        self.task=None;self.actor=None;self.seen={};self.last={};self.limits={};self.sequence=0;self.metric_at=0.
        self.metrics={'received':0,'native_dropped':0,'transport_dropped':0,'bridge_dropped':0,'rate_limited':0,'gateway_dropped':0,'snapshot_coalesced':0,'tracking_evicted':0}
    async def start(self):
        loop=asyncio.get_running_loop();self.wake=asyncio.Event()
        scene=await asyncio.to_thread(self.gateway.player.observe)
        if not scene.get('auto_events_supported') or not scene.get('alive'):raise ValueError('Native auto-event provider unavailable; upgrade and bind a live actor')
        self.actor=scene['actor_session']
        def wake():
            if not loop.is_closed():loop.call_soon_threadsafe(self.wake.set)
        await asyncio.to_thread(self.bridge.start_native_events,self.actor,wake)
        self.task=asyncio.create_task(self.run())
        self.task.add_done_callback(lambda t:None if t.cancelled() else t.exception())
    async def run(self):
        try:
            while True:
                await self.wake.wait();self.wake.clear()
                for frame in self.bridge.drain_native_events():await self.accept(frame)
        except asyncio.CancelledError:raise
        except Exception:
            self.gateway.failed=True
            for ws in list(self.gateway.connections):await ws.close(1011,'Native event source failed; no reconnect/replay')
            raise
    async def close(self):
        if self.task:self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
        # A failed native connection is terminal. Never reconnect just to disable it.
        if not self.gateway.failed and self.actor:
            try:await asyncio.to_thread(self.bridge.call,'events_configure',enabled=False,actor_session=self.actor)
            except Exception:self.gateway.failed=True  # Keep cleanup progressing, never retry/rebind.
    async def emit(self,sid,name,data):
        now=time.monotonic();epoch,count=self.limits.get(sid,(now,0))
        if now-epoch>=1:epoch,count=now,0
        if count>=20:self.metrics['rate_limited']+=1;return
        self.limits[sid]=(epoch,count+1)
        await self.gateway.publish(Event(name,{**data,'actor_session':self.actor,'untrusted_observation':True}),session_id=sid)
    async def accept(self,frame):
        if frame.get('actor_session')!=self.actor:raise ValueError('Native event actor changed')
        seq=frame.get('sequence')
        if type(seq) is not int or seq<1:raise ValueError('Invalid event sequence')
        if seq<=self.sequence:return
        self.sequence=seq;self.metrics['received']+=1
        for key in ('dropped_total','transport_dropped_total'):
            if type(frame.get(key,0)) is not int or frame.get(key,0)<0:raise ValueError('Invalid native loss counter')
        self.metrics['native_dropped']=frame.get('dropped_total',0);self.metrics['transport_dropped']=frame.get('transport_dropped_total',0);self.metrics['bridge_dropped']=self.bridge.event_dropped
        name,data=frame['name'],frame['data']
        if name=='entities.snapshot':
            rows=data.get('entities')
            if not isinstance(rows,list) or len(rows)>16 or type(data.get('truncated')) is not bool:raise ValueError('Bounded entity snapshot required')
            for row in rows:
                if (not isinstance(row,dict) or row.get('category') not in {'player','hostile'}
                    or not isinstance(row.get('uuid'),str) or not 1<=len(row['uuid'])<=128
                    or type(row.get('entity_id')) is not int or row['entity_id']<0
                    or not isinstance(row.get('entity_type'),str) or len(row['entity_type'])>128
                    or type(row.get('distance')) not in (float,int) or not math.isfinite(row['distance']) or not 0<=row['distance']<=24
                    or not isinstance(row.get('position'),list) or len(row['position'])!=3
                    or any(type(v) not in (int,float) or not math.isfinite(v) for v in row['position'])):
                    raise ValueError('Invalid native entity observation')
        active=set(self.gateway.sinks)
        for sid in set(self.seen)|set(self.last)|set(self.limits):
            if sid not in active:self.seen.pop(sid,None);self.last.pop(sid,None);self.limits.pop(sid,None)
        for sid in active:
            session=self.gateway.jobs.sessions.get(sid)
            if session is None or session.actor_session!=self.actor:continue
            policy=self.policy(session.store.identity)
            if not isinstance(policy,ReportingPolicy):raise ValueError('Invalid reporting policy')
            if name=='player.chat':
                if (not isinstance(data.get('message'),str) or len(data['message'])>2048
                    or data.get('channel')!='player_chat'):raise ValueError('Invalid native chat payload')
                if 'player.chat' in session.subscriptions and policy.chat(name,data,session.store.identity):
                    await self.emit(sid,name,data)
            elif name=='entities.snapshot':
                now=time.monotonic()
                if now-self.last.get(sid,-math.inf)<policy.min_interval:self.metrics['snapshot_coalesced']+=1;continue
                self.last[sid]=now;rows=data.get('entities')
                if not isinstance(rows,list) or len(rows)>16:raise ValueError('Bounded entity snapshot required')
                current={};previous=self.seen.get(sid,{})
                wanted={'player' if e.startswith('player.nearby.') else 'hostile' for e in session.subscriptions if e.startswith(('player.nearby.','entity.hostile.'))}
                for row in rows:
                    category=row.get('category');uid=row.get('uuid');distance=row.get('distance');position=row.get('position')
                    if category not in wanted or distance>policy.radius or (category=='player' and policy.players and uid not in policy.players):continue
                    current[uid]=row
                unknown=set()
                if data.get('truncated'):
                    # Omission is unknown, not leave. Keep memory bounded even across
                    # an arbitrarily long series of crowded/truncated observations.
                    present={r['uuid'] for r in rows}
                    for uid,row in previous.items():
                        if uid not in present and row['category'] in wanted:
                            unknown.add(uid)
                            if len(current)<32:current.setdefault(uid,row)
                            else:self.metrics['tracking_evicted']+=1
                for uid,row in current.items():
                    event=('player.nearby.' if row['category']=='player' else 'entity.hostile.')+'enter'
                    if uid not in previous and event in session.subscriptions:await self.emit(sid,event,{**row,'observed_at_ms':data.get('observed_at_ms')})
                for uid,row in previous.items():
                    event=('player.nearby.' if row['category']=='player' else 'entity.hostile.')+'leave'
                    if uid not in current and uid not in unknown and event in session.subscriptions:await self.emit(sid,event,{'uuid':uid,'entity_id':row['entity_id'],'entity_type':row['entity_type'],'reason':'no_longer_observed','last_observation':row,'observed_at_ms':data.get('observed_at_ms')})
                self.seen[sid]=current
            else:raise ValueError('Unsupported native event source')
        if time.monotonic()-self.metric_at>=1:
            self.metric_at=time.monotonic()
            await self.gateway.publish(Event('reporting.metrics',{'actor_session':self.actor,**self.metrics}))
