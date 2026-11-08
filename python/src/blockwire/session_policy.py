"""Opt-in two-hour host scheduling, not a Minecraft planner or safety waiver.

Only the trusted host selects this profile. Known terminal gameplay blocks allow
bounded waiting and a NEW model decision, never automatic action retry. Transport
uncertainty, actor replacement, F8 and resource failures remain terminal.
"""
import dataclasses
import hashlib
import json
import math
from .feedback import InputPolicy
from .model_limits import TwoHourPolicy,integer
from .soak import UnknownNoRetry

@dataclasses.dataclass(frozen=True)
class TwoHourSessionProfile:
    gameplay_seconds:int=7200
    preparation_seconds:int=900
    finalization_seconds:int=900
    minimum_decision_interval:int=10
    blocked_backoff_seconds:int=30
    idle_backoff_seconds:int=30
    rejected_backoff_seconds:int=120
    identical_failure_limit:int=2
    max_frame_operations:int=12
    max_feedback:int=100
    def __post_init__(self):
        for name in ('gameplay_seconds','preparation_seconds','finalization_seconds','minimum_decision_interval','blocked_backoff_seconds','idle_backoff_seconds','rejected_backoff_seconds','identical_failure_limit','max_frame_operations','max_feedback'):
            # This is one explicit profile, not model-editable limit configuration.
            expected=type(self).__dataclass_fields__[name].default
            integer(getattr(self,name),expected,expected,name)
    def model_policy(self,campaign,agents):return TwoHourPolicy(campaign,agents)
    def input_policy(self,allowed_opcodes):
        return InputPolicy(max_frame_operations=self.max_frame_operations,max_session_operations=9000,
            max_actor_operations=9000,max_feedback_per_session=self.max_feedback,allowed_opcodes=allowed_opcodes)
    def play_deadline_ms(self,outer_deadline_ms,now_ms):
        integer(outer_deadline_ms,1,2**63-1,'outer deadline');integer(now_ms,0,2**63-1,'current time')
        needed=(self.gameplay_seconds+self.finalization_seconds)*1000
        if outer_deadline_ms-now_ms<needed:raise RuntimeError('Insufficient remaining envelope for two-hour play and cleanup')
        return now_ms+self.gameplay_seconds*1000
    def describe(self):
        return {**dataclasses.asdict(self),'outer_seconds':9000,'requests_per_agent':720,'total_requests':1440,
            'operations_per_agent':9000,'total_operations':18000,'model_concurrency':2,'model_timeout_seconds':90,
            'known_failure_behavior':'wait then ask model again; no automatic action retry',
            'unknown_actor_resource_F8_behavior':'terminal; no reconnect/rebind/respawn',
            'two_hour_native_acceptance':'NOT_RUN','duration_is_ceiling_not_guaranteed_progress':True}


def observed_state_key(scene,inventory,navigation):
    """Only supplied client observations; ignore clocks/labels and sub-voxel jitter.

    A state change permits reconsideration, NOT proof of progress or safe travel.
    A different look may provide genuinely new visible geometry. No hidden map.
    """
    actor=scene.get('actor_session')
    if not isinstance(actor,str) or not actor or inventory.get('actor_session')!=actor or navigation.get('actor_session')!=actor:
        raise ValueError('Same fresh actor required')
    position=scene.get('position')
    if not isinstance(position,list) or len(position)!=3 or any(type(v)not in (int,float)or not math.isfinite(v)for v in position):raise ValueError('Finite native position required')
    payload={'actor':actor,'position_quarters':[math.floor(v*4)for v in position],
        'inventory':inventory.get('items',[]),'carried':inventory.get('carried'),
        'visible_blocks':scene.get('visible_blocks'),'sight_target':scene.get('sight_target'),
        'navigation':{k:navigation.get(k)for k in ('profile','ready','reason','current_cell','current_center_access','cells','edges')}}
    encoded=json.dumps(payload,allow_nan=False,sort_keys=True,separators=(',',':')).encode()
    if len(encoded)>128*1024:raise ValueError('Bounded observation fingerprint required')
    return hashlib.sha256(encoded).hexdigest()


def action_key(prepared,state_key):
    if not isinstance(state_key,str)or len(state_key)!=64 or any(c not in '0123456789abcdef'for c in state_key):raise ValueError('Observed state SHA-256 required')
    # Compiler locations/comments/spacing are not different gameplay intent.
    operations=[]
    if prepared.program:
        for operation in prepared.program.operations:
            row=operation.to_dict();row.pop('line');row.pop('column');operations.append(row)
    return hashlib.sha256(json.dumps([state_key,operations],allow_nan=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


class SessionPacing:
    """Per-agent, bounded known-failure memory. Never selects/replays an action.

    Use only within a fresh SessionLifecycle. Existing journals must not be
    resumed implicitly. Durable request/operation budgets stay in ModelLimits.
    """
    def __init__(self,deadline,*,profile=None):
        if type(deadline)not in (int,float)or not math.isfinite(deadline):raise ValueError('Finite monotonic gameplay deadline')
        self.profile=profile or TwoHourSessionProfile()
        if not isinstance(self.profile,TwoHourSessionProfile):raise ValueError('Typed operator profile required')
        self.deadline=deadline;self.next_due=0.;self.last_time=None;self.terminal=False;self.failures={};self.known_failures=0;self.idle_decisions=0
    def check(self,now):
        if type(now)not in (int,float)or not math.isfinite(now):raise ValueError('Finite monotonic time required')
        if self.terminal:raise UnknownNoRetry('Terminal session; no new actions')
        if self.last_time is not None and now<self.last_time:self.terminal=True;raise UnknownNoRetry('Monotonic clock regressed')
        self.last_time=now
        if now>=self.deadline:raise TimeoutError('gameplay_deadline')
    def delay(self,now):
        self.check(now);return max(0.,min(self.next_due,self.deadline)-now)
    def permit(self,prepared,state_key,now):
        self.check(now)
        if now<self.next_due:raise RuntimeError('Decision pacing still active')
        return not prepared.program or self.failures.get(action_key(prepared,state_key),0)<self.profile.identical_failure_limit
    def record(self,prepared,state_key,now,*,known_terminal,successful):
        self.check(now)
        if type(known_terminal)is not bool or type(successful)is not bool:raise ValueError('Explicit typed terminal outcome required')
        if not known_terminal:self.terminal=True;raise UnknownNoRetry('UNKNOWN_NO_RETRY: outcome not known')
        delay=self.profile.minimum_decision_interval
        if prepared.program and not successful:
            key=action_key(prepared,state_key)
            if key not in self.failures and len(self.failures)>=720:raise RuntimeError('Known failure memory capacity')
            self.failures[key]=self.failures.get(key,0)+1;self.known_failures+=1;delay=self.profile.blocked_backoff_seconds
        elif not prepared.program:
            self.idle_decisions+=1;delay=self.profile.idle_backoff_seconds
        self.next_due=now+delay
    def rejected(self,now):
        self.check(now);self.next_due=now+self.profile.rejected_backoff_seconds
    def describe(self):
        return {'known_failed_frames':self.known_failures,'idle_decisions':self.idle_decisions,
            'identical_failed_frame_limit_per_observed_state':self.profile.identical_failure_limit,
            'unchanged_failed_frames_are_not_automatically_retried':True,'unknown_is_terminal':True}

if __name__=='__main__':
    print(json.dumps(TwoHourSessionProfile().describe(),indent=2))
