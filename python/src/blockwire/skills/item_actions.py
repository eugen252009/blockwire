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
DRY_SUPPORTS=frozenset({'minecraft:grass_block','minecraft:dirt','minecraft:stone','minecraft:cobblestone',*PLANKS})
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
    clear_plants: bool = Field(default=True,description='Permit one native attack to clear an exact observed small dry flower at the intended destination, then require fresh exact support proof before use. Never break structural blocks.')
    # No arbitrary target query: use only a currently observed support's exact top hit.
    support: list[int] | None = Field(default=None, min_length=3, max_length=3,
        description='Optional observed support. Omit to select a nearby observed dry support mechanically.')

    @field_validator('support')
    @classmethod
    def bounds(cls, value): return Approach.bounded_position(value)


def place_block(context, goal, *, expected_session=None):
    ui = InventorySession(context)
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
    if support is None:
        return blocked('support_not_observed')
    # Only simple full-cube dry soil/stone supports; do not open a chest/door or guess a partial shape.
    if support['id'] not in DRY_SUPPORTS:
        return blocked('unsupported_placement_support')
    support_position=support['position']
    x, y, z = support_position
    offsets={'up':(0,1,0),'down':(0,-1,0),'north':(0,0,-1),'south':(0,0,1),'east':(1,0,0),'west':(-1,0,0)}
    offset=offsets[goal.face]
    destination=[v+d for v,d in zip(support_position,offset)]
    px,py,pz=scene['position'];tx,ty,tz=destination
    if not goal.auto_position and tx-.4<px<tx+1.4 and tz-.4<pz<tz+1.4 and py<ty+1.1 and py+1.9>ty:
        return blocked('placement_too_close_to_player')
    aim=[x+.5+offset[0]*.5,y+.5+offset[1]*.5,z+.5+offset[2]*.5]
    if goal.auto_position:
        from .walking import walk_to,WalkTo
        from .approaching import _reachable
        context.check();nav=context.player.navigation(terrain=True);context.check()
        if nav.get('actor_session')!=ui.session:raise SkillStop('blocked','actor_session_changed')
        if not nav.get('ready'):return blocked('placement_navigation_not_ready')
        cells=_reachable(nav,True)
        def usable_point(point,eye=None,*,margin=.4,reach=2.95):
            eye=eye or (point[0],point[1]+1.62,point[2])
            facing=sum((eye[i]-aim[i])*offset[i] for i in range(3))>.05
            overlap=tx-margin<point[0]<tx+1.+margin and tz-margin<point[2]<tz+1.+margin and point[1]<ty+1.1 and point[1]+1.9>ty
            return facing and not overlap and math.dist(eye,aim)<=reach
        def usable(cell):return usable_point((cell[0]+.5,cell[1],cell[2]+.5))
        current_cell=tuple(nav['current_cell']);current_center=(current_cell[0]+.5,current_cell[1],current_cell[2]+.5)
        current_valid=(current_cell in cells and nav.get('current_center_access') and
                       math.dist(scene['position'],current_center)<=.08 and
                       usable_point(scene['position'],scene['eye_position']))
        # The entire upright arrival interval must satisfy reach/body margins,
        # not just its mathematical centre. Samples remain inside one proven
        # full floor cell; this is positioning for ONE supplied target only.
        choices=[(cell[0]+.5+dx,float(cell[1]),cell[2]+.5+dz) for cell in cells
                 for dx in (-.12,0.,.12) for dz in (-.12,0.,.12)
                 if usable_point((cell[0]+.5+dx,cell[1],cell[2]+.5+dz),margin=.55,reach=2.8)]
        if not choices and not current_valid:
            disconnected=[tuple(c['position']) for c in nav['cells'] if not c['hazards'] and usable(c['position'])]
            disconnected.sort(key=lambda c:math.dist(scene['position'],(c[0]+.5,c[1],c[2]+.5)))
            return blocked('no_known_placement_pose',support=support_position,expected_face=goal.face,
                current_cell=nav.get('current_cell'),known_reachable_count=len(cells),
                known_placement_poses=[[c[0]+.5,c[1],c[2]+.5] for c in disconnected[:6]],
                constraint='These native standing poses satisfy face plane/reach/body clearance, but no safe current-graph route reaches them. Occlusion is not proven; the external agent chooses access, route or design changes.')
        if not current_valid:
            point=min(choices,key=lambda p:(abs(p[0]-(math.floor(p[0])+.5))+abs(p[2]-(math.floor(p[2])+.5)),
                                            math.dist(scene['position'],p)))
            result=walk_to(context,WalkTo(x=point[0],y=point[1],z=point[2],terrain=True,arrival_radius=.15),expected_session=ui.session)
            if result.status!='succeeded':return result
            scene=ui.guard()
    if math.dist(scene['eye_position'], aim) > 3.:
        return blocked('support_out_of_reach')
    initial = item_counts(ui.snapshot).get(goal.block, 0)
    while True:
        s = ui.guard()
        dx, dy, dz = [aim[i]-s['eye_position'][i] for i in range(3)]
        wanted = math.degrees(math.atan2(-dx, dz)), -math.degrees(math.atan2(dy, math.hypot(dx, dz)))
        turning = rotate_view_timed(context, (s['yaw'], s['pitch']), wanted, ui.session)
        context.pause(.08)
        if not turning: break
    s = ui.guard()
    hit, sight = s.get('target') or {}, s.get('sight_target') or {}
    direct = (hit.get('kind') == 'block' and hit.get('id') == support['id'] and hit.get('position') == support_position
              and hit.get('face') == goal.face and sight.get('position') == support_position)
    flower=(goal.face=='up' and hit.get('kind')=='block' and hit.get('id') in CLEARABLE_FLOWERS
            and hit.get('position')==destination and sight.get('position')==destination and sight.get('id')==hit.get('id'))
    if flower:
        if not goal.clear_plants:return blocked('plant_clearance_not_enabled')
        context.check();context.player.action('attack',actor_session=ui.session)  # One bounded native instant-plant attempt, never a structural mining loop.
        context.pause(.15);s=ui.guard();hit,sight=s.get('target') or {},s.get('sight_target') or {}
        direct=(hit.get('kind')=='block' and hit.get('id')==support['id'] and hit.get('position')==support_position
                and hit.get('face')==goal.face and sight.get('position')==support_position)
        if not direct:return blocked('plant_clearance_not_observed',actual_target=hit,support=support_position)
    # Native BlockItem placement can replace these ordinary noninteractive plants.
    # Keep known dry support, exact fresh destination hit and the SAME postcondition.
    vegetation = (goal.face=='up' and hit.get('kind') == 'block' and hit.get('id') in REPLACEABLE_PLANTS
                  and hit.get('position') == destination and sight.get('position') == destination and sight.get('id') == hit.get('id'))
    if not (direct or vegetation):
        return blocked('exact_support_top_not_acquired',expected_face=goal.face,actual_target=hit,
                       support=support_position,eye_position=s['eye_position'],
                       face_rule='To see a cube face your eye must be outside its plane: east x>support.x+1; west x<support.x; south z>support.z+1; north z<support.z; up y>support.y+1; down y<support.y. Occlusion can still block it.')
    px,py,pz=s['position']
    if tx-.4<px<tx+1.4 and tz-.4<pz<tz+1.4 and py<ty+1.1 and py+1.9>ty:
        return blocked('placement_too_close_to_player')
    if s.get('holding', {}).get('item') != goal.block:
        return blocked('held_item_changed')
    context.check()
    context.player.action('use', actor_session=ui.session)  # Submission only, never blindly repeat.
    for _ in range(15):
        context.pause(.1)
        s, inv = ui.guard(), ui.read()
        observed = any(r['position'] == destination and r['id'] == goal.block for r in _observed(context, s))
        if observed and initial-item_counts(inv).get(goal.block, 0) == 1:
            return SkillResult(status='succeeded', reason='block_placed', text='Observed placed block and consumed item.',
                               details={'block': goal.block, 'position': destination})
    return blocked('placement_not_observed')


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
