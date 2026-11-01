"""Bounded active visual search over the existing route/motion executor, not progression policy."""
import math
from pydantic import Field, field_validator
from .core import SkillParameters, SkillDefinition, SkillResult, SkillStop
from .woodcutting import LOGS, observed_blocks, _standing
from .approaching import _reachable
from .walking import WalkTo, walk_to
from .motion import rotate_view_timed
from ..mechanics import DROPS


class SearchBlocks(SkillParameters):
    block: str = Field(min_length=1,max_length=128,description='logs or a supported mining block registry ID')
    radius: float = Field(default=16.,ge=1.,le=24.)
    waypoints: int = Field(default=4,ge=1,le=8)
    terrain: bool = True
    require_reachable: bool = True

    @field_validator('block')
    @classmethod
    def supported(cls, v):
        if v not in {*LOGS,*DROPS,'logs'}: raise ValueError('Unsupported visual search block')
        return v


def search_blocks(context, goal):
    from .crafting import ensure_gameplay
    ensure_gameplay(context)
    context.check()
    first=context.player.observe();session=first.get('actor_session');origin=first['position'];health=first['health']
    visited=[]
    seen=[]
    def observe():
        context.check();s=context.player.observe()
        if s.get('actor_session')!=session:raise SkillStop('blocked','actor_session_changed')
        if not s.get('alive') or s['health']<health:raise SkillStop('blocked','damage_or_death_observed')
        if s.get('visibility',{}).get('profile')!='sampled_surfaces_v1':raise SkillStop('blocked','visibility_observation_required')
        if math.dist(s['position'],origin)>goal.radius+.5:raise SkillStop('blocked','search_radius_exceeded')
        return s
    allowed=LOGS if goal.block=='logs' else {goal.block}
    for waypoint in range(goal.waypoints):
        s=observe();visited.append(s['position']);scan_origin=s['yaw']
        for scan in range(17):
            found=observed_blocks({**s,'target':None},allowed)
            seen=sorted(set(seen).union(found),key=lambda t:math.dist(s['position'],[v+.5 for v in t[1]]))[:16]
            if found and goal.require_reachable:
                context.check()
                mesh=context.player.navigation(terrain=True) if goal.terrain else context.player.navigation()
                if mesh.get('actor_session')!=session:raise SkillStop('blocked','actor_session_changed')
                found=[t for t in found if mesh.get('ready') and _standing(mesh,t) is not None
                       and math.dist(s['position'],[v+.5 for v in t[1]])<=6.]
            if found:
                return SkillResult(status='succeeded',reason='blocks_observed',text='Currently observed surfaces, not mined or reachable proof.',
                    details={'targets':[{'id':i,'position':list(p)} for i,p in found][:16], 'visited':visited})
            context.publish({'phase':'visual_search','waypoint':waypoint,'scan':scan,'block':goal.block})
            if scan<16:
                target_yaw=(scan_origin+90.*(scan//4+1)+180)%360-180
                rotate_view_timed(context,(s['yaw'],s['pitch']),(target_yaw,15.),session)
                s=observe()
        context.check()
        mesh=context.player.navigation(terrain=True) if goal.terrain else context.player.navigation()
        if mesh.get('actor_session')!=session:raise SkillStop('blocked','actor_session_changed')
        if not mesh.get('ready') or mesh.get('on_fire') or mesh.get('nearby_hostiles'):
            raise SkillStop('blocked',mesh.get('reason','known_danger_nearby'))
        options=[]
        for cell,cost in _reachable(mesh,True).items():
            point=(cell[0]+.5,cell[1],cell[2]+.5)
            separation=min(math.dist(point,p) for p in visited)
            if separation>=2 and math.dist(point,origin)<=goal.radius:
                score = min(math.dist(point,[v+.5 for v in t[1]]) for t in seen)+cost*.02 if seen else -separation/(cost+1)
                options.append((score,cost,point))
        if not options:break
        _,_,point=min(options)
        result=walk_to(context,WalkTo(x=point[0],y=float(point[1]),z=point[2],terrain=goal.terrain),expected_session=session)
        if result.status!='succeeded':return result
    return SkillResult(status='blocked',reason='bounded_visual_search_exhausted',text='No matching exposed surface found; hidden space remains unknown.',
                       details={'block':goal.block,'visited':visited,'radius':goal.radius,
                                'observed_but_not_locally_collectable':[{'id':i,'position':list(p)} for i,p in seen]})


SEARCH_BLOCKS=SkillDefinition('search_blocks','Bounded stopped visual scans and known collision-route waypoints to find logs or supported exposed mining blocks. '
    'No hidden resources, arbitrary voxel queries, mining or automatic progression. Observed targets are NOT proof of reachability. '
    'One-block terrain steps opt-in; stops at danger, dead ends and bounded exhaustion.',SearchBlocks,search_blocks)
