"""One observed full-cube removal, shared mining motor; NOT resource collection."""
from typing import Literal
from pydantic import Field,field_validator
from .core import SkillDefinition,SkillParameters,SkillResult,SkillStop
from .crafting import ensure_gameplay,blocked
from .woodcutting import observed_blocks,_standing,mine_observed_target
from .walking import WalkTo,walk_to
from ..mechanics import MINING

class RemoveBlock(SkillParameters):
    block: Literal['minecraft:dirt','minecraft:grass_block','minecraft:stone','minecraft:cobblestone'] = 'minecraft:dirt'
    position: list[int] = Field(min_length=3,max_length=3)
    excavate: bool = Field(default=False,description='Permit an exposed cardinal neighbor one level below retained support; never own support.')
    @field_validator('position')
    @classmethod
    def bounds(cls,value):
        from .approaching import Approach
        return Approach.bounded_position(value)


def clear_full_cube(nav,position):
    """Only native collision-free standing body/head volume, not arbitrary air."""
    if not nav.get('ready') or nav.get('profile')!='stepped_full_blocks_v1':return False
    return any(not c['hazards'] and tuple(position) in (tuple(c['position']),
        (c['position'][0],c['position'][1]+1,c['position'][2])) for c in nav['cells'])


def remove_block(context,goal):
    ensure_gameplay(context);context.check();initial=context.player.observe()
    session=initial.get('actor_session');health=initial.get('health',20.)
    if not session or not initial.get('alive') or not initial.get('in_world'):raise SkillStop('blocked','live_player_required')
    def navigation():
        context.check();nav=context.player.navigation(terrain=True);context.check()
        if nav.get('actor_session')!=session:raise SkillStop('blocked','actor_session_changed')
        if not nav.get('ready') or nav.get('profile')!='stepped_full_blocks_v1':raise SkillStop('blocked','native_geometry_required')
        current=next((c for c in nav['cells'] if c['position']==nav['current_cell']),None)
        if current is None or current['hazards']:raise SkillStop('blocked','unsafe_current_support')
        if not nav.get('alive') or nav.get('health',0)<health or nav.get('on_fire') or nav.get('nearby_hostiles'):
            raise SkillStop('blocked','damage_or_danger_observed')
        return nav
    def observe():
        context.check();scene=context.player.observe();context.check()
        if scene.get('actor_session')!=session:raise SkillStop('blocked','actor_session_changed')
        if not scene.get('alive') or not scene.get('in_world'):raise SkillStop('blocked','live_player_required')
        return scene
    nav=navigation()
    if clear_full_cube(nav,goal.position):return SkillResult(status='succeeded',reason='full_cube_already_absent',text='Fresh native body clearance excludes the requested full cube.',details={'position':goal.position,'drop_collection_verified':False})
    selected=(goal.block,tuple(goal.position));scene=observe()
    if selected not in observed_blocks(scene,{goal.block}):return blocked('exact_exposed_block_required',position=goal.position)
    tools=MINING[goal.block]['accepted_held_items']
    if tools and scene.get('holding',{}).get('item') not in tools:return blocked('appropriate_equipped_tool_required')
    destination=_standing(nav,selected,excavate=goal.excavate)
    if destination is None:return blocked('no_known_safe_mining_pose',position=goal.position)
    result=walk_to(context,WalkTo(x=destination[0],y=float(destination[1]),z=destination[2],terrain=True,arrival_radius=.15,
        timeout_seconds=goal.timeout_seconds),expected_session=session)
    if result.status!='succeeded':return result
    mine_observed_target(context,selected,session,navigation,observe,tools=frozenset(tools) if tools else None,excavate=goal.excavate)
    # Target loss/ray receipt alone is NOT removal proof. Re-observe native
    # collision clearance; no drop, floor, destination or hidden block inference.
    for _ in range(10):
        if clear_full_cube(navigation(),goal.position):return SkillResult(status='succeeded',reason='full_cube_removed',text='Observed native body clearance at the former full-cube target.',details={'position':goal.position,'block':goal.block,'drop_collection_verified':False})
        context.pause(.1)
    return blocked('removal_clearance_not_observed',position=goal.position)

REMOVE_BLOCK=SkillDefinition('remove_block','Remove ONE exact currently exposed dirt/grass/stone/cobblestone full cube using the shared guarded mining motor. Requires fresh native body/head clearance afterward, NOT drops or attack receipts. No hidden coordinate lookup, automatic scaffolding or pickup claim. Optional one-level cardinal side cut, never own support.',RemoveBlock,remove_block)
