"""Bounded native camera adapter, not a block query or planner."""
import math
from .core import SkillDefinition,SkillParameters,SkillResult,SkillStop
from .walking import WalkTo
from .motion import rotate_view_timed

class AimAt(SkillParameters):
    x: float = WalkTo.model_fields['x']
    y: float = WalkTo.model_fields['y']
    z: float = WalkTo.model_fields['z']

def aim_at(context,goal):
    context.check();s=context.player.observe();session=s.get('actor_session')
    if not s.get('alive') or not s.get('in_world'):raise SkillStop('blocked','live_player_required')
    while True:
        context.check();s=context.player.observe();context.check()
        if s.get('actor_session')!=session:raise SkillStop('blocked','actor_session_changed')
        if not s.get('alive'):raise SkillStop('blocked','player_dead')
        dx,dy,dz=[v-p for v,p in zip((goal.x,goal.y,goal.z),s['eye_position'])]
        wanted=(math.degrees(math.atan2(-dx,dz)),-math.degrees(math.atan2(dy,math.hypot(dx,dz))))
        yaw_error=abs((wanted[0]-s['yaw']+180)%360-180)
        if yaw_error<1. and abs(wanted[1]-s['pitch'])<1.:
            return SkillResult(status='succeeded',reason='view_observed',text='Observed requested native camera orientation.',details={'yaw':s['yaw'],'pitch':s['pitch'],'sight_target':s.get('sight_target')})
        rotate_view_timed(context,(s['yaw'],s['pitch']),wanted,session);context.pause(.08)

AIM_AT=SkillDefinition('aim_at','Aim native camera at a supplied world point using actor-fenced native time-based rotation. No hidden coordinate/block lookup; success is observed camera orientation.',AimAt,aim_at)
