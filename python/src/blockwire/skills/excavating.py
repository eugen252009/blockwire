"""A bounded excavation/clearance primitive, not an ore finder or progression planner."""
import math
from typing import Literal
from pydantic import Field
from .core import SkillDefinition,SkillParameters,SkillResult,SkillStop
from .woodcutting import mine_observed_target,LOGS
from .motion import FlatMotion,rotate_view_timed
from .walking import WalkTo,walk_to
from .approaching import _reachable
from ..mechanics import MINING

PLANTS=frozenset({'minecraft:leaf_litter','minecraft:short_grass','minecraft:tall_grass','minecraft:fern','minecraft:large_fern','minecraft:dead_bush'})
PLANTS |= frozenset('minecraft:'+s for s in ('dandelion','poppy','blue_orchid','allium','azure_bluet','red_tulip','orange_tulip','white_tulip','pink_tulip','oxeye_daisy','cornflower','lily_of_the_valley','sunflower','lilac','rose_bush','peony','wildflowers','pink_petals','bush','firefly_bush','dry_short_grass','dry_tall_grass'))
LEAVES=frozenset(i.replace('_log','_leaves') for i in LOGS)
CLEARABLE=frozenset({'minecraft:dirt','minecraft:grass_block','minecraft:stone','minecraft:cobblestone','minecraft:coal_ore'})|PLANTS|LEAVES


class DigStep(SkillParameters):
    direction: Literal['north','south','east','west'] = 'north'
    steps: int = Field(default=1,ge=1,le=3)


def dig_step(context, goal):
    from .crafting import ensure_gameplay
    ensure_gameplay(context)
    session=health=origin=None
    cleared=[]
    completed=0
    def blocked(reason,**details):
        return SkillResult(status='blocked',reason=reason,text=reason.replace('_',' '),
                           details={'completed_steps':completed,'clearance_observations':cleared,**details})
    def navigation():
        nonlocal session,health,origin
        context.check();s=context.player.navigation(terrain=True);context.check()
        if s.get('profile')!='stepped_full_blocks_v1' or not s.get('ready'):
            raise SkillStop('blocked',s.get('reason','stepped_navigation_required'))
        if session is None:session,health,origin=s['actor_session'],s['health'],s['position'][:]
        if s['actor_session']!=session:raise SkillStop('blocked','actor_session_changed')
        if s['health']<health or s.get('on_fire') or s.get('nearby_hostiles'):
            raise SkillStop('blocked','damage_or_known_danger_observed')
        if math.dist(s['position'],origin)>6.:raise SkillStop('blocked','local_activity_radius_exceeded')
        return s
    def observe():
        context.check();s=context.player.observe();context.check()
        if s.get('actor_session')!=session:raise SkillStop('blocked','actor_session_changed')
        if not s.get('alive') or s.get('visibility',{}).get('profile')!='sampled_surfaces_v1':
            raise SkillStop('blocked','fresh_visibility_required')
        return s
    delta={'north':(0,-1),'south':(0,1),'east':(1,0),'west':(-1,0)}[goal.direction]
    for _ in range(goal.steps):
        s=navigation();cx,cy,cz=s['current_cell'];center=(cx+.5,cy,cz+.5)
        motor=FlatMotion()
        while math.dist(s['position'],center)>.1:
            scene=observe()
            r=motor.pulse(context,s,center,'walk',view=(scene['yaw'],scene['pitch']),precision_sneak=False,max_ticks=1)
            if r is not None:return r
            s=navigation()
        motor.halt(context);context.pause(.15)
        x,z=cx+delta[0],cz+delta[1]
        # Top-down bounded clearance, including conservative reverse-jump headroom.
        # Looking is ordinary bounded perception, NOT an arbitrary coordinate block read.
        for y in range(cy+2,cy-2,-1):
            for attempt in range(3):
                s=navigation();scene=observe()
                if s['current_cell']!=[cx,cy,cz]:return blocked('excavation_source_changed')
                aim=(x+.5,y+.25,z+.5)
                dx,dy,dz=[aim[i]-scene['eye_position'][i] for i in range(3)]
                wanted=(math.degrees(math.atan2(-dx,dz)),-math.degrees(math.atan2(dy,math.hypot(dx,dz))))
                while True:
                    turning=rotate_view_timed(context,(scene['yaw'],scene['pitch']),wanted,session)
                    context.pause(.08);navigation();scene=observe()
                    if not turning:break
                hit=scene.get('sight_target') or {};p=hit.get('position')
                if not p or (p[0],p[2])!=(x,z) or not cy-1<=p[1]<=cy+2:
                    break  # No relevant obstruction observed. Only the later native mesh can prove clearance.
                if hit.get('id') not in CLEARABLE:return blocked('unsupported_clearance_block',target=hit)
                rule=MINING.get(hit['id']);accepted=rule['accepted_held_items'] if rule else []
                if accepted and scene.get('holding',{}).get('item') not in accepted:
                    return blocked('appropriate_equipped_tool_required',mining_contract=rule)
                target=(hit['id'],tuple(p))
                context.publish({'phase':'excavating_step','direction':goal.direction,'completed_steps':completed,'target':target})
                changed=mine_observed_target(context,target,session,navigation,observe,
                    tools=frozenset(accepted) if accepted else None,excavate=True)
                if not changed:return blocked('clearance_target_not_fresh',target=hit)
                cleared.append({'id':target[0],'position':list(target[1]),'evidence':'native_target_no_longer_hit; NOT collection proof'})
                context.check();context.player.stop();context.pause(.1)
            else:return blocked('clearance_attempt_bound_exhausted')
        s=navigation();destination=(x,cy-1,z)
        if destination not in _reachable(s,True):
            return blocked('no_verified_step_destination',destination=destination,
                           cause='Native supported floor/headroom/edge missing; no blind fall attempted')
        r=walk_to(context,WalkTo(x=x+.5,y=float(cy-1),z=z+.5,terrain=True),expected_session=session)
        if r.status!='succeeded':return r
        s=navigation()
        if math.dist(s['position'],(x+.5,cy-1,z+.5))>.3:return blocked('step_postcondition_not_observed')
        completed+=1
    return SkillResult(status='succeeded',reason='excavated_steps_observed',
        text='Observed requested one-block descents after bounded exposed clearance and native geometry validation.',
        details={'completed_steps':completed,'position':s['position'],'clearance_observations':cleared,
                 'collection_claimed':False,'damage_avoidance_is_best_effort':True})


DIG_STEP=SkillDefinition('dig_step','Excavate 1–3 descending one-block steps in a selected cardinal direction. '
    'Centers on retained support, clears only fresh exposed dry soil/stone/leaves/plants in the adjacent column, top-down, '
    'then enters ONLY if new native collision geometry proves supported floor/headroom and an edge. '
    'Appropriate equipped tool required for stone/coal. Never own support, sand/gravel, fluids or hidden voxel queries. '
    'Useful for bounded access/clearance; not an ore finder. Success verifies movement, NOT collected resource counts.',DigStep,dig_step)
