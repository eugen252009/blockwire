"""Explicit supported drop contracts over the existing local harvesting motor."""
from typing import Literal
from pydantic import Field,field_validator,model_validator
from .core import SkillDefinition, SkillParameters, SkillStop, SkillResult
from ..mechanics import PICKS, DROPS, MINING
from .woodcutting import _gather

# Compatibility exports PICKS/DROPS derive from the shared mechanics catalogue.


class GatherBlock(SkillParameters):
    block: Literal['minecraft:stone', 'minecraft:cobblestone', 'minecraft:dirt', 'minecraft:grass_block', 'minecraft:crafting_table', 'minecraft:coal_ore', 'ground_soil']
    count: int = Field(default=1, ge=1, le=16)
    scan: bool = True
    terrain: bool = False
    position: list[int] | None = Field(default=None,min_length=3,max_length=3,description='Optional exact currently exposed block coordinate; no hidden lookup. With position set, count must be one.')

    @field_validator('position')
    @classmethod
    def bounded_position(cls,value):
        from .approaching import Approach
        return Approach.bounded_position(value)

    @model_validator(mode='after')
    def single_target(self):
        if self.position is not None and self.count!=1:raise ValueError('Exact-target gathering requires count=1')
        return self

    excavate: bool = Field(default=False, description='With terrain=True, permit observed adjacent one-block-lower excavation, NEVER own support column. Enter a hole only after native mesh proves its floor/headroom; soil group clears exposed dirt/grass without hidden lookup.')


def gather_block(context, goal):
    if goal.excavate and not goal.terrain:
        raise SkillStop('blocked','excavation_requires_terrain_profile')
    rule = MINING[goal.block]
    accepted = rule['accepted_held_items']
    tools = frozenset(accepted) if accepted else None
    context.check()
    initial = context.player.observe()
    if tools is not None and initial.get('holding', {}).get('item') not in tools:
        return SkillResult(status='blocked', reason='appropriate_equipped_tool_required',
            text='Held item does not satisfy the block mining contract.',
            details={'held_item':initial.get('holding', {}).get('item'), 'mining_contract':MINING[goal.block]})
    reasons = {'wood_collected': 'block_drops_collected', 'wood_not_collected': 'drops_not_collected',
               'no_reachable_exposed_logs': 'no_reachable_exposed_blocks',
               'hazardous_log_area': 'hazardous_block_area',
               'log_requires_higher_support': 'block_requires_higher_support',
               'log_route_too_long': 'block_route_too_long', 'log_not_reachable': 'block_not_reachable',
               'log_target_not_fresh_or_native': 'block_target_not_fresh_or_native'}
    try:
        result = _gather(context, goal, block_ids=set(rule['blocks']), drop_ids={rule['drop']}, tools=tools,
                         expected_session=initial.get('actor_session'))
    except SkillStop as stop:
        raise SkillStop(stop.status, reasons.get(stop.reason, stop.reason)) from None
    result.reason = reasons.get(result.reason, result.reason)
    result.text = result.reason.replace('_', ' ')
    result.details['mining_contract'] = MINING[goal.block]
    if 'observed_logs' in result.details: result.details['observed_blocks'] = result.details.pop('observed_logs')
    for old,new in [('baseline_logs','baseline_items'),('inventory_logs','inventory_items')]:
        if old in result.details:result.details[new]=result.details.pop(old)
    result.details['drop'] = rule['drop']
    if goal.position is not None:result.details['position']=goal.position
    return result


GATHER_BLOCK = SkillDefinition('gather_block',
    'Mine currently exposed stone/cobblestone/dirt/coal ore within radius 6 using the shared harvesting motor. terrain=True enables bounded one-block routes. '
    'Pickaxe required per mechanics contract except soil. No Silk Touch or hidden lookup. Optional position selects ONE exact currently exposed target (count=1), not a hidden coordinate query. excavate=True with terrain=True permits observed one-block-lower SIDE cuts and entry only with newly observed supported geometry, NEVER own support. ground_soil matches exposed dirt/grass. '
    'Success requires additional expected drops in inventory, not attack receipts. Unsupported terrain stops.',
    GatherBlock, gather_block)
