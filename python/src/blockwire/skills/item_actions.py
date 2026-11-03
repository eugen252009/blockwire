"""Small verified native item actions; no progression strategy or hidden lookups."""
import math
from typing import Literal
from pydantic import Field, field_validator
from .core import SkillDefinition, SkillParameters, SkillResult, SkillStop
from .crafting import InventorySession, blocked
from .approaching import Approach, approach
from .motion import rotate_view_timed
from .distance import _observed
from ..recipes import item_counts,PLANKS

PLACEABLE_BLOCKS=('minecraft:crafting_table','minecraft:cobblestone','minecraft:dirt',*PLANKS)
INTERACTIVE_SUPPORTS=frozenset({'minecraft:crafting_table'})  # Known full cube; use requires crouch, never open it.
DRY_SUPPORTS=frozenset({'minecraft:grass_block','minecraft:dirt','minecraft:stone','minecraft:cobblestone',*PLANKS}) | INTERACTIVE_SUPPORTS
# Ordinary replaceable dry vanilla plants. Native BlockItem placement and the
# SAME observed block + one-item consumption postcondition remain authoritative.
REPLACEABLE_PLANTS=frozenset('minecraft:'+name for name in ('leaf_litter','short_grass','fern','dead_bush'))
CLEARABLE_FLOWERS=frozenset('minecraft:'+name for name in (
    'dandelion','poppy','blue_orchid','allium','azure_bluet','red_tulip',
    'orange_tulip','white_tulip','pink_tulip','oxeye_daisy','cornflower',
    'lily_of_the_valley','torchflower'))


class EquipItem(SkillParameters):
    item: str = Field(min_length=1, max_length=128, pattern=r'^[a-z0-9_.-]+:[a-z0-9_./-]+$')


def equip_item(context, goal, *, expected_session=None):
    ui = InventorySession(context)
    if expected_session is not None and ui.session != expected_session:
        raise SkillStop('blocked', 'actor_session_changed')
    row = next((i for i in ui.snapshot['items'] if i.get('item') == goal.item and i['inventory_index'] < 36), None)
    if row is None:
        return blocked('item_not_in_inventory', item=goal.item)
    index = row['inventory_index']
    if index >= 9:
        used = {i['inventory_index'] for i in ui.snapshot['items']}
        index = next((i for i in range(9) if i not in used), None)
        if index is None:
            return blocked('empty_hotbar_slot_required')
        ui.ensure_open()
        if not ui.cursor_empty():
            return blocked('cursor_requires_recovery')
        source = next(s for s in ui.player_slots() if s['inventory_index'] == row['inventory_index'])
        dest = next(s for s in ui.player_slots() if s['inventory_index'] == index)
        ui.click(source['slot'])
        if ui.snapshot['carried'].get('item') != goal.item or not ui.slot(dest['slot']).get('empty'):
            return blocked('inventory_changed', recovery_required=True)
        ui.click(dest['slot'])
        if not ui.cursor_empty() or ui.slot(dest['slot']).get('item') != goal.item:
            return blocked('hotbar_transfer_not_observed', recovery_required=True)
    if ui.snapshot.get('container_open'):
        ui.close_clean()
    ui.guard()
    context.player.hotbar(index, actor_session=ui.session)
    context.pause(.1)
    scene = ui.guard()
    if scene.get('holding', {}).get('item') != goal.item:
        return blocked('equipped_item_not_observed')
    return SkillResult(status='succeeded', reason='item_equipped', text='Observed the requested held item.',
                       details={'item': goal.item, 'hotbar_slot': index})


class InteractBlock(SkillParameters):
    terrain: bool = False
    target: Literal['minecraft:crafting_table'] = 'minecraft:crafting_table'
    position: list[int] | None = Field(default=None, min_length=3, max_length=3)

    @field_validator('position')
    @classmethod
    def bounds(cls, value): return Approach.bounded_position(value)


def interact_block(context, goal):
    context.check()
    scene = context.player.observe()
    session = scene.get('actor_session')
    result = approach(context, Approach(target=goal.target, position=goal.position,
                                       timeout_seconds=goal.timeout_seconds, terrain=goal.terrain), expected_session=session)
    if result.status != 'succeeded': return result
    context.check()
    scene = context.player.observe()
    if scene.get('actor_session') != session:
        raise SkillStop('blocked', 'actor_session_changed')
    target = result.details['target']
    if scene.get('target', {}).get('position') != target['position'] or scene['target'].get('id') != goal.target:
        return blocked('target_changed_before_use')
    context.check()
    context.player.action('use', actor_session=session)
    for _ in range(10):
        context.pause(.1)
        inv = context.player.inventory()
        if inv.get('actor_session') != session:
            raise SkillStop('blocked', 'actor_session_changed')
        if inv.get('container_open') and inv.get('menu_type') == 'CraftingMenu':
            return SkillResult(status='succeeded', reason='workbench_opened', text='Observed the native workbench menu.',
                               details={'target': target, 'menu_id': inv['menu_id']})
    return blocked('workbench_open_not_observed')


class PlaceBlock(SkillParameters):
    block: Literal[PLACEABLE_BLOCKS] = 'minecraft:crafting_table'
    face: Literal['up','down','north','south','east','west'] = 'up'
    auto_position: bool = Field(default=False,description='Mechanically approach a known reachable standing cell facing the requested support face; no placement strategy.')
    recorded_pose: list[int | float] | None = Field(default=None,min_length=3,max_length=3,description='Optional exact recorded grounded player pose for this placement. Runtime still validates native support, reach and actor fencing.')
    recorded_aim: list[int | float] | None = Field(default=None,min_length=3,max_length=3,description='Recorded ray intersection on the supplied support face, reconstructed from local pose/view evidence.')
    recorded_sneak: bool = Field(default=False,description='Preserve an observed local-human crouched placement stance with an actor-fenced native sneak lease.')
    jump_place: bool = Field(default=False,description='Permit one bounded native vertical jump placement against an exact recorded up-face support. Requires auto_position and never retries use.')
    clear_plants: bool = Field(default=True,description='Permit one native attack to clear an exact observed small dry flower at the intended destination, then require fresh exact support proof before use. Never break structural blocks.')
    # No arbitrary target query: use only a currently observed support's exact top hit.
    support: list[int] | None = Field(default=None, min_length=3, max_length=3,
        description='Optional observed support. Omit to select a nearby observed dry support mechanically.')

    @field_validator('support')
    @classmethod
    def bounds(cls, value): return Approach.bounded_position(value)

    @field_validator('recorded_pose','recorded_aim')
    @classmethod
    def pose_bounds(cls, value):
        if value is None:return value
        if not (-29_999_984 <= value[0] <= 29_999_984 and -2048 <= value[1] <= 2048 and
                -29_999_984 <= value[2] <= 29_999_984):raise ValueError('recorded pose outside world bounds')
        return value


def _safe_partial_recorded_pose(nav, scene, point):
    if (not nav.get('ready') or abs(float(scene['position'][1])-float(point[1]))>.1
            or math.dist(scene['position'],point)>.5):
        return False
    cell=tuple(nav.get('current_cell',()))
    row=next((entry for entry in nav.get('cells',()) if tuple(entry.get('position',()))==cell),None)
    if row is None or row.get('hazards'):
        return False
    half=.3
    overlap_x=max(0.,min(float(point[0])+half,cell[0]+1.)-max(float(point[0])-half,cell[0]))
    overlap_z=max(0.,min(float(point[2])+half,cell[2]+1.)-max(float(point[2])-half,cell[2]))
    return min(overlap_x,overlap_z)>=.08 and max(overlap_x,overlap_z)>=.25


def _jump_place(context, goal, ui, scene, support, destination, aim):
    if goal.face != 'up' or not goal.auto_position:
        return blocked('jump_place_requires_up_face_and_auto_position')
    tx, ty, tz = destination
    if goal.recorded_pose is not None:
        qx,qy,qz=goal.recorded_pose
        if math.floor(qx)!=tx or math.floor(qz)!=tz or qy < ty+1.1:
            return blocked('invalid_recorded_jump_pose', recorded_pose=goal.recorded_pose, position=destination)
    from .walking import walk_to,WalkTo
    point = (tx + .5, float(ty), tz + .5)
    if (not scene.get('on_ground') or abs(float(scene['position'][1]) - ty) > .08
            or math.hypot(float(scene['position'][0]) - point[0], float(scene['position'][2]) - point[2]) > .15):
        result = walk_to(context, WalkTo(x=point[0], y=point[1], z=point[2], terrain=True, arrival_radius=.15),
                         expected_session=ui.session)
        if result.status != 'succeeded':
            return result
        scene = ui.guard()
    px, py, pz = scene['position']
    if (scene.get('on_ground') is not True or abs(float(py) - ty) > .08
            or not tx + .15 <= px <= tx + .85 or not tz + .15 <= pz <= tz + .85):
        return blocked('jump_place_start_not_reached', position=scene.get('position'))
    while True:
        s = ui.guard();dx, dy, dz = [aim[i] - s['eye_position'][i] for i in range(3)]
        wanted = math.degrees(math.atan2(-dx, dz)), -math.degrees(math.atan2(dy, math.hypot(dx, dz)))
        turning = rotate_view_timed(context, (s['yaw'], s['pitch']), wanted, ui.session)
        context.pause(.08)
        if not turning: break
    s = ui.guard();hit, sight = s.get('target') or {}, s.get('sight_target') or {}
    direct = (hit.get('kind') == 'block' and hit.get('id') == support['id'] and hit.get('position') == support['position']
              and hit.get('face') == 'up' and sight.get('position') == support['position'])
    if not direct:
        return blocked('exact_support_top_not_acquired', expected_face='up', actual_target=hit,
                       support=support['position'], eye_position=s.get('eye_position'))
    initial = item_counts(ui.snapshot).get(goal.block, 0)
    context.check()
    context.player.drive(['jump'] + (['sneak'] if goal.recorded_sneak else []), 4, wait=False, actor_session=ui.session)
    try:
        airborne = False
        for _ in range(20):
            context.pause(.05);s = ui.guard();px, py, pz = s['position']
            airborne = airborne or s.get('on_ground') is False
            jump_height = max(ty + 1.1, float(goal.recorded_pose[1]) - .08) if goal.recorded_pose is not None else ty + 1.1
            if not airborne or py < jump_height:
                continue
            if not tx + .05 <= px <= tx + .95 or not tz + .05 <= pz <= tz + .95:
                return blocked('jump_place_drifted', position=s.get('position'))
            context.player.stop()
            if goal.recorded_sneak:
                context.player.drive(['sneak'],8,wait=False,actor_session=ui.session);context.pause(.05)
            s = ui.guard();hit, sight = s.get('target') or {}, s.get('sight_target') or {}
            direct = (hit.get('kind') == 'block' and hit.get('id') == support['id']
                      and hit.get('position') == support['position'] and hit.get('face') == 'up'
                      and sight.get('position') == support['position'])
            if not direct:
                return blocked('jump_support_lost_before_use', actual_target=hit, support=support['position'])
            context.check();context.player.action('use', actor_session=ui.session)
            for _ in range(15):
                context.pause(.1);s, inv = ui.guard(), ui.read()
                observed = any(r['position'] == destination and r['id'] == goal.block for r in _observed(context, s))
                if observed and initial - item_counts(inv).get(goal.block, 0) == 1:
                    for _ in range(30):
                        s = ui.guard();px, py, pz = s['position']
                        if (s.get('on_ground') is True and abs(float(py) - (ty + 1)) <= .08
                                and tx <= px <= tx + 1 and tz <= pz <= tz + 1):
                            return SkillResult(status='succeeded', reason='block_placed',
                                text='Observed one jump placement, item consumption and safe landing on the placed block.',
                                details={'block': goal.block, 'position': destination, 'jump_place': True})
                        context.pause(.05)
                    return blocked('jump_place_landing_not_observed', position=destination, placement_observed=True)
            return blocked('placement_not_observed')
        return blocked('jump_height_not_observed', position=s.get('position') if 's' in locals() else scene.get('position'))
    finally:
        context.player.stop()


def _placement_inventory(context):
    """Reuse an adapter only inside one authorized context; inventory stays fresh."""
    cached=context.placement_session if context.execution_options.placement_reuse else None
    if cached is not None:
        if cached.context is not context or cached.player is not context.player:
            raise SkillStop('blocked','placement_context_changed')
        cached.read()  # Includes live actor/health guard; never reuse a stale stack.
        if not cached.snapshot.get('guarded_inventory'):
            raise SkillStop('blocked','guarded_inventory_required_update_mod')
        return cached
    ui=InventorySession(context)
    if context.execution_options.placement_reuse:context.placement_session=ui
    return ui


def place_block(context, goal, *, expected_session=None, preserve_recorded_sneak=False):
    if preserve_recorded_sneak and not goal.recorded_sneak:
        raise ValueError('preserved stance requires recorded sneak evidence')
    if not goal.recorded_sneak:context.release_retained_sneak()
    ui = _placement_inventory(context)
    if expected_session is not None and ui.session!=expected_session:raise SkillStop('blocked','actor_session_changed')
    if ui.snapshot.get('container_open'):
        ui.close_clean()
    scene = ui.guard()
    if goal.support is not None:
        offsets={'up':(0,1,0),'down':(0,-1,0),'north':(0,0,-1),'south':(0,0,1),'east':(1,0,0),'west':(-1,0,0)}
        destination=[v+d for v,d in zip(goal.support,offsets[goal.face])]
        if any(r['position']==destination and r['id']==goal.block for r in _observed(context,scene)):
            return SkillResult(status='succeeded',reason='desired_block_already_observed',
                text='Fresh native observation already satisfies the requested placement; no use or consumption.',
                details={'block':goal.block,'position':destination,'consumed':0})
    if scene.get('holding', {}).get('item') != goal.block:
        return blocked('equip_requested_block_first')
    if scene.get('visibility', {}).get('profile') != 'sampled_surfaces_v1':
        return blocked('visibility_observation_required')
    if goal.support is None:
        # Active bounded inspection only, never a coordinate lookup or placement strategy.
        while scene['pitch'] < 55:
            rotate_view_timed(context,(scene['yaw'],scene['pitch']),(scene['yaw'],55.),ui.session)
            context.pause(.08);scene=ui.guard()
        candidates=[r for r in _observed(context,scene)
                    if r['id'] in DRY_SUPPORTS
                    and math.hypot(r['position'][0]+.5-scene['position'][0],r['position'][2]+.5-scene['position'][2])>=1.2
                    and math.dist(scene['eye_position'],[r['position'][0]+.5,r['position'][1]+1.,r['position'][2]+.5])<=3.]
        support=min(candidates,key=lambda r:(abs(r['position'][1]+1-scene['position'][1]),
            math.dist(scene['eye_position'],[r['position'][0]+.5,r['position'][1]+1.,r['position'][2]+.5]))) if candidates else None
    else:
        support = next((r for r in _observed(context, scene) if r['position'] == goal.support), None)
    if (support is None and goal.support is not None and goal.recorded_pose is not None
            and goal.auto_position and not goal.jump_place):
        from .walking import walk_to,WalkTo
        context.check();nav=context.player.navigation(terrain=True);context.check()
        if nav.get('actor_session')!=ui.session:raise SkillStop('blocked','actor_session_changed')
        if _safe_partial_recorded_pose(nav,scene,goal.recorded_pose):
            qx,qy,qz=goal.recorded_pose
            result=walk_to(context,WalkTo(x=qx,y=qy,z=qz,terrain=True,arrival_radius=.08,
                                          sneak=True,movement='sneak'),expected_session=ui.session)
            if result.status!='succeeded':return result
            if goal.recorded_sneak:
                context.check();context.player.drive(['sneak'],8,wait=False,actor_session=ui.session);context.pause(.05)
            support_offset={'up':(0,1,0),'down':(0,-1,0),'north':(0,0,-1),'south':(0,0,1),'east':(1,0,0),'west':(-1,0,0)}[goal.face]
            support_aim=(list(goal.recorded_aim) if goal.recorded_aim is not None else
                         [goal.support[i]+.5+support_offset[i]*.5 for i in range(3)])
            while True:
                scene=ui.guard();dx,dy,dz=[support_aim[i]-scene['eye_position'][i] for i in range(3)]
                wanted=math.degrees(math.atan2(-dx,dz)),-math.degrees(math.atan2(dy,math.hypot(dx,dz)))
                if not rotate_view_timed(context,(scene['yaw'],scene['pitch']),wanted,ui.session):break
                if goal.recorded_sneak:context.player.drive(['sneak'],8,wait=False,actor_session=ui.session)
                context.pause(.08)
            scene=ui.guard()
            support=next((r for r in _observed(context,scene) if r['position']==goal.support),None)
            if goal.recorded_sneak:context.player.stop()
    if support is None:
        return blocked('support_not_observed')
    # Only known full cubes; a crafting table requires crouch and is never opened.
    # Chests, doors and unknown collision shapes remain unsupported.
    if support['id'] not in DRY_SUPPORTS:
        return blocked('unsupported_placement_support')
    if support['id'] in INTERACTIVE_SUPPORTS and goal.jump_place:
        return blocked('interactive_support_jump_not_supported')
    support_position=support['position']
    x, y, z = support_position
    offsets={'up':(0,1,0),'down':(0,-1,0),'north':(0,0,-1),'south':(0,0,1),'east':(1,0,0),'west':(-1,0,0)}
    offset=offsets[goal.face]
    destination=[v+d for v,d in zip(support_position,offset)]
    px,py,pz=scene['position'];tx,ty,tz=destination
    if not goal.auto_position and tx-.4<px<tx+1.4 and tz-.4<pz<tz+1.4 and py<ty+1.1 and py+1.9>ty:
        return blocked('placement_too_close_to_player')
    aim=[x+.5+offset[0]*.5,y+.5+offset[1]*.5,z+.5+offset[2]*.5]
    if goal.recorded_aim is not None:
        axis={'east':0,'west':0,'up':1,'down':1,'south':2,'north':2}[goal.face]
        side=1 if goal.face in {'east','up','south'} else 0
        plane=support_position[axis]+side
        if abs(float(goal.recorded_aim[axis])-plane)>.001 or any(
                not support_position[index]-1e-6<=goal.recorded_aim[index]<=support_position[index]+1+1e-6
                for index in range(3) if index!=axis):
            return blocked('invalid_recorded_support_aim',recorded_aim=goal.recorded_aim,support=support_position)
        aim=list(goal.recorded_aim)
    if goal.jump_place:
        return _jump_place(context, goal, ui, scene, support, destination, aim)
    if goal.recorded_pose is not None and not goal.auto_position:
        return blocked('recorded_pose_requires_auto_position')
    if goal.auto_position:
        from .walking import walk_to,WalkTo
        from .approaching import _reachable
        context.check();nav=context.player.navigation(terrain=True);context.check()
        if nav.get('actor_session')!=ui.session:raise SkillStop('blocked','actor_session_changed')
        if not nav.get('ready'):return blocked('placement_navigation_not_ready')
        cells=_reachable(nav,True)
        def usable_point(point,eye=None,*,margin=.4,reach=None):
            eye=eye or (point[0],point[1]+(1.27 if goal.recorded_sneak else 1.62),point[2])
            reach=reach if reach is not None else (4.5 if goal.recorded_sneak else 2.95)
            facing=sum((eye[i]-aim[i])*offset[i] for i in range(3))>.05
            top_margin = -.001 if goal.recorded_pose is not None else .1
            overlap=tx-margin<point[0]<tx+1.+margin and tz-margin<point[2]<tz+1.+margin and point[1]<ty+1.+top_margin and point[1]+1.9>ty
            return facing and not overlap and math.dist(eye,aim)<=reach
        def usable(cell):return usable_point((cell[0]+.5,cell[1],cell[2]+.5))
        current_cell=tuple(nav['current_cell']);current_center=(current_cell[0]+.5,current_cell[1],current_cell[2]+.5)
        recorded_proxy=True;recorded_target_valid=False;recorded_point=None;recorded_cell=None
        if goal.recorded_pose is not None:
            recorded_point=tuple(float(v) for v in goal.recorded_pose)
            recorded_cell=(math.floor(recorded_point[0]),round(recorded_point[1]),math.floor(recorded_point[2]))
            recorded_target_valid=((recorded_cell in cells or _safe_partial_recorded_pose(nav,scene,recorded_point))
                                   and usable_point(recorded_point))
            recorded_proxy=(abs(scene['position'][1]-recorded_point[1])<=.1
                            and math.dist(scene['position'],recorded_point)<=.35
                            and (recorded_cell==current_cell or recorded_cell not in cells)
                            and usable_point(scene['position'],None if goal.recorded_sneak else scene['eye_position']))
        position_cell=(math.floor(scene['position'][0]),round(scene['position'][1]),math.floor(scene['position'][2]))
        position_authorized=(math.dist(scene['position'],current_center)<=.08
                             or nav.get('source_recovered_from_partial_support') is True
                             or (recorded_point is not None and recorded_proxy
                                 and (position_cell==current_cell or nav.get('source_recovered_from_partial_support') is True)))
        current_valid=(current_cell in cells and nav.get('current_center_access') and position_authorized
                       and recorded_proxy and usable_point(scene['position'],None if goal.recorded_sneak else scene['eye_position']))
        # The entire upright arrival interval must satisfy reach/body margins,
        # not just its mathematical centre. Samples remain inside one proven
        # full floor cell; this is positioning for ONE supplied target only.
        choices=[(cell[0]+.5+dx,float(cell[1]),cell[2]+.5+dz) for cell in cells
                 for dx in (-.12,0.,.12) for dz in (-.12,0.,.12)
                 if usable_point((cell[0]+.5+dx,cell[1],cell[2]+.5+dz),margin=.55,
                                 reach=4.35 if goal.recorded_sneak else 2.8)]
        if not choices and not current_valid and not recorded_target_valid:
            if recorded_point is not None and recorded_cell not in cells:
                return blocked('recorded_partial_pose_not_safely_reached',recorded_pose=goal.recorded_pose,
                               position=scene.get('position'),current_cell=nav.get('current_cell'))
            disconnected=[tuple(c['position']) for c in nav['cells'] if not c['hazards'] and usable(c['position'])]
            disconnected.sort(key=lambda c:math.dist(scene['position'],(c[0]+.5,c[1],c[2]+.5)))
            return blocked('no_known_placement_pose',support=support_position,expected_face=goal.face,
                current_cell=nav.get('current_cell'),known_reachable_count=len(cells),
                known_placement_poses=[[c[0]+.5,c[1],c[2]+.5] for c in disconnected[:6]],
                constraint='These native standing poses satisfy face plane/reach/body clearance, but no safe current-graph route reaches them. Occlusion is not proven; the external agent chooses access, route or design changes.')
        if not current_valid:
            if recorded_point is not None:
                if not recorded_target_valid:
                    return blocked('recorded_partial_pose_not_safely_reached',recorded_pose=goal.recorded_pose,
                                   position=scene.get('position'),current_cell=nav.get('current_cell'))
                point=recorded_point;arrival_radius=.08;movement={'sneak':True,'movement':'sneak'}
            else:
                point=min(choices,key=lambda p:(abs(p[0]-(math.floor(p[0])+.5))+abs(p[2]-(math.floor(p[2])+.5)),
                                                math.dist(scene['position'],p)))
                arrival_radius=.15;movement={}
            baseline_health=scene.get('health')
            result=walk_to(context,WalkTo(x=point[0],y=point[1],z=point[2],terrain=True,
                                          arrival_radius=arrival_radius,**movement),expected_session=ui.session)
            if result.status!='succeeded':
                if recorded_point is None or result.reason!='not_grounded':return result
                settled=False
                for _ in range(10):
                    context.check();context.pause(.05);fresh=context.player.navigation(terrain=True);context.check()
                    if fresh.get('actor_session')!=ui.session:return blocked('actor_session_changed')
                    if (baseline_health is not None and fresh.get('health',baseline_health)<baseline_health) or fresh.get('on_fire'):
                        return blocked('damage_observed')
                    if fresh.get('ready') and math.dist(fresh.get('position',[math.inf]*3),recorded_point)<=.1:
                        scene=ui.guard();settled=True;break
                    if abs(float(fresh.get('position',[0.,math.inf,0.])[1])-recorded_point[1])>.25:break
                if not settled:return result
            else:scene=ui.guard()
            if recorded_point is not None and math.dist(scene['position'],recorded_point)>.1:
                return blocked('recorded_placement_pose_not_reached',recorded_pose=goal.recorded_pose,position=scene.get('position'))
    modeled_eye=[scene['position'][0],scene['position'][1]+(1.27 if goal.recorded_sneak else 1.62),scene['position'][2]]
    if math.dist(modeled_eye, aim) > (4.5 if goal.recorded_sneak else 3.):
        return blocked('support_out_of_reach')
    stance_required=goal.recorded_sneak or support['id'] in INTERACTIVE_SUPPORTS
    keep_verification_stance=preserve_recorded_sneak or (context.execution_options.sneak_reuse and stance_required)
    stance_owned=False
    def release_stance():
        nonlocal stance_owned
        if stance_owned and not preserve_recorded_sneak:
            context.player.stop();stance_owned=False
            context.retained_sneak_session=None
    if stance_required:
        context.check();context.player.drive(['sneak'],8,wait=False,actor_session=ui.session);stance_owned=True
        context.retain_sneak(ui.session)
        context.pause(.05);scene=ui.guard()
    initial = item_counts(ui.snapshot).get(goal.block, 0)
    while True:
        s = ui.guard()
        if stance_required:
            context.check();context.player.drive(['sneak'],8,wait=False,actor_session=ui.session);stance_owned=True
        dx, dy, dz = [aim[i]-s['eye_position'][i] for i in range(3)]
        wanted = math.degrees(math.atan2(-dx, dz)), -math.degrees(math.atan2(dy, math.hypot(dx, dz)))
        turning = rotate_view_timed(context, (s['yaw'], s['pitch']), wanted, ui.session)
        if turning or not context.execution_options.camera_reuse:context.pause(.08)
        if not turning: break
    s = ui.guard()
    hit, sight = s.get('target') or {}, s.get('sight_target') or {}
    direct = (hit.get('kind') == 'block' and hit.get('id') == support['id'] and hit.get('position') == support_position
              and hit.get('face') == goal.face and sight.get('position') == support_position)
    if not direct and goal.recorded_pose is not None and math.dist(s['position'],goal.recorded_pose)>.08:
        release_stance();context.check();nav=context.player.navigation(terrain=True);context.check()
        if nav.get('actor_session')!=ui.session:raise SkillStop('blocked','actor_session_changed')
        from .approaching import _reachable
        pose_cell=(math.floor(goal.recorded_pose[0]),round(goal.recorded_pose[1]),math.floor(goal.recorded_pose[2]))
        if nav.get('ready') and (pose_cell in _reachable(nav,True) or _safe_partial_recorded_pose(nav,s,goal.recorded_pose)):
            from .walking import walk_to,WalkTo
            qx,qy,qz=goal.recorded_pose
            result=walk_to(context,WalkTo(x=qx,y=qy,z=qz,terrain=True,arrival_radius=.08,
                                          sneak=True,movement='sneak'),expected_session=ui.session)
            if result.status!='succeeded':return result
            if goal.recorded_sneak:
                context.player.drive(['sneak'],8,wait=False,actor_session=ui.session);stance_owned=True;context.pause(.05)
            while True:
                s=ui.guard();dx,dy,dz=[aim[i]-s['eye_position'][i] for i in range(3)]
                wanted=math.degrees(math.atan2(-dx,dz)),-math.degrees(math.atan2(dy,math.hypot(dx,dz)))
                if not rotate_view_timed(context,(s['yaw'],s['pitch']),wanted,ui.session):break
                if goal.recorded_sneak:context.player.drive(['sneak'],8,wait=False,actor_session=ui.session)
                context.pause(.08)
            s=ui.guard();hit,sight=s.get('target') or {},s.get('sight_target') or {}
            direct=(hit.get('kind')=='block' and hit.get('id')==support['id'] and hit.get('position')==support_position
                    and hit.get('face')==goal.face and sight.get('position')==support_position)
    flower=(goal.face=='up' and hit.get('kind')=='block' and hit.get('id') in CLEARABLE_FLOWERS
            and hit.get('position')==destination and sight.get('position')==destination and sight.get('id')==hit.get('id'))
    if flower:
        if not goal.clear_plants:
            release_stance();return blocked('plant_clearance_not_enabled')
        context.check();context.player.action('attack',actor_session=ui.session)  # One bounded native instant-plant attempt, never a structural mining loop.
        context.pause(.15);s=ui.guard();hit,sight=s.get('target') or {},s.get('sight_target') or {}
        direct=(hit.get('kind')=='block' and hit.get('id')==support['id'] and hit.get('position')==support_position
                and hit.get('face')==goal.face and sight.get('position')==support_position)
        if not direct:
            release_stance();return blocked('plant_clearance_not_observed',actual_target=hit,support=support_position)
    # Native BlockItem placement can replace these ordinary noninteractive plants.
    # Keep known dry support, exact fresh destination hit and the SAME postcondition.
    vegetation = (goal.face=='up' and hit.get('kind') == 'block' and hit.get('id') in REPLACEABLE_PLANTS
                  and hit.get('position') == destination and sight.get('position') == destination and sight.get('id') == hit.get('id'))
    if not (direct or vegetation):
        release_stance()
        return blocked('exact_support_top_not_acquired',expected_face=goal.face,actual_target=hit,
                       support=support_position,eye_position=s['eye_position'],
                       face_rule='To see a cube face your eye must be outside its plane: east x>support.x+1; west x<support.x; south z>support.z+1; north z<support.z; up y>support.y+1; down y<support.y. Occlusion can still block it.')
    px,py,pz=s['position']
    top_margin = -.001 if goal.recorded_pose is not None else .1
    if tx-.4<px<tx+1.4 and tz-.4<pz<tz+1.4 and py<ty+1.+top_margin and py+1.9>ty:
        release_stance();return blocked('placement_too_close_to_player')
    if s.get('holding', {}).get('item') != goal.block:
        release_stance();return blocked('held_item_changed')
    context.check()
    if stance_required:
        context.player.drive(['sneak'],8,wait=False,actor_session=ui.session);stance_owned=True
    context.player.action('use', actor_session=ui.session)  # Submission only, never blindly repeat.
    if not keep_verification_stance:release_stance()
    try:
        for _ in range(15):
            if keep_verification_stance:
                context.check();context.player.drive(['sneak'],8,wait=False,actor_session=ui.session)
            context.pause(.1)
            if keep_verification_stance:
                context.check();context.player.drive(['sneak'],8,wait=False,actor_session=ui.session)
            s = ui.guard()
            if keep_verification_stance:
                context.check();context.player.drive(['sneak'],8,wait=False,actor_session=ui.session)
            inv = ui.read()
            observed = any(r['position'] == destination and r['id'] == goal.block for r in _observed(context, s))
            if observed and initial-item_counts(inv).get(goal.block, 0) == 1:
                return SkillResult(status='succeeded', reason='block_placed', text='Observed placed block and consumed item.',
                                   details={'block': goal.block, 'position': destination})
        return blocked('placement_not_observed')
    finally:
        release_stance()


class PlaceAt(SkillParameters):
    block: PlaceBlock.model_fields['block'].annotation = PlaceBlock.model_fields['block']
    position: list[int] = Field(min_length=3,max_length=3,description='Desired block coordinate, NOT a support. Only currently observed neighboring supports are considered.')
    clear_plants: bool = True

    @field_validator('position')
    @classmethod
    def bounds(cls,value):return Approach.bounded_position(value)


def place_at(context,goal):
    """Mechanical support/face selection for ONE model-selected voxel, never a design."""
    ui=InventorySession(context)
    if ui.snapshot.get('container_open'):ui.close_clean()
    scene=ui.guard();rows=list(_observed(context,scene))
    if any(r['position']==goal.position and r['id']==goal.block for r in rows):
        return SkillResult(status='succeeded',reason='desired_block_already_observed',text='Fresh target already matches; no use or consumption.',details={'block':goal.block,'position':goal.position,'consumed':0})
    if scene.get('holding',{}).get('item')!=goal.block:return blocked('equip_requested_block_first')
    offsets={'up':(0,1,0),'down':(0,-1,0),'north':(0,0,-1),'south':(0,0,1),'east':(1,0,0),'west':(-1,0,0)}
    options=[]
    for face,offset in offsets.items():
        position=[p-d for p,d in zip(goal.position,offset)]
        if not any(r['position']==position and r['id'] in DRY_SUPPORTS for r in rows):continue
        aim=[position[i]+.5+offset[i]*.5 for i in range(3)]
        facing=sum((scene['eye_position'][i]-aim[i])*offset[i] for i in range(3))>.05
        options.append((not facing,math.dist(scene['eye_position'],aim),position,face,aim))
    options.sort(key=lambda r:(r[0],r[1]));failures=[]
    for _,_,support,face,aim in options[:3]:
        # A previously observed local support is an aiming landmark, never a
        # hidden block query. The delegated adapter rechecks exact native hits.
        while True:
            s=ui.guard();dx,dy,dz=[aim[i]-s['eye_position'][i] for i in range(3)]
            wanted=math.degrees(math.atan2(-dx,dz)),-math.degrees(math.atan2(dy,math.hypot(dx,dz)))
            turning=rotate_view_timed(context,(s['yaw'],s['pitch']),wanted,ui.session)
            context.pause(.08)
            if not turning:break
        result=place_block(context,PlaceBlock(block=goal.block,support=support,face=face,auto_position=True,clear_plants=goal.clear_plants,timeout_seconds=goal.timeout_seconds),expected_session=ui.session)
        if result.status=='succeeded':return result
        failures.append({'support':support,'face':face,'reason':result.reason,'details':{k:v for k,v in result.details.items() if k in {'actual_target','known_placement_poses','current_cell','constraint','expected_face'}}})
        # NEVER retry after use/uncertain outcome, actor loss, inventory or motion
        # failure. Only a short explicit whitelist of pre-use target failures.
        if result.reason not in {'support_not_observed','exact_support_top_not_acquired','no_known_placement_pose','support_out_of_reach','placement_too_close_to_player'}:return result
    return blocked('observed_placement_supports_blocked' if options else 'placement_support_unknown',position=goal.position,attempts=failures)


PLACE_AT=SkillDefinition('place_at','Place ONE agent-selected block coordinate. Select support/face among currently observed dry full-cube neighbors, bounded to three pre-use candidates; delegate native positioning and verified placement. Never retry uncertain use. No structure, resource or scaffold strategy.',PlaceAt,place_at)


EQUIP_ITEM = SkillDefinition('equip_item', 'Equip an inventory item, using a free hotbar slot if needed. Verify held item; fenced native inventory only.', EquipItem, equip_item)
INTERACT_BLOCK = SkillDefinition('interact_with_block', 'Approach a currently visible crafting table and open its native 3x3 menu. Other blocks unsupported.', InteractBlock, interact_block)
PLACE_BLOCK = SkillDefinition('place_block', 'Place an equipped supported block against a selected currently observed full-cube support face within 3 blocks. Verify block and inventory consumption. No hidden coordinate lookup.', PlaceBlock, place_block)
