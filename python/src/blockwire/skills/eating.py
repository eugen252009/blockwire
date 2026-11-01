"""Exclusive stationary native eating; shares the async controller's outcome contract."""
from pydantic import Field, field_validator
from .core import SkillDefinition, SkillParameters, SkillResult, SkillStop
from .crafting import InventorySession, blocked
from .item_actions import EquipItem, equip_item
from .motion import rotate_view_timed
from ..food import FOOD, consumption_observed
from ..recipes import item_counts


class ConsumeItem(SkillParameters):
    item: str = Field(default='minecraft:bread', min_length=1, max_length=128,
                      json_schema_extra={'enum': sorted(FOOD)})
    @field_validator('item')
    @classmethod
    def supported_food(cls, value):
        if value not in FOOD: raise ValueError('Only explicitly supported ordinary foods')
        return value


def consume_item(context, goal):
    ui = InventorySession(context)
    scene = ui.guard()
    initial_hunger = scene.get('hunger')
    if type(initial_hunger) is not int or not 0 <= initial_hunger <= 20:
        return blocked('hunger_observation_required')
    if initial_hunger == 20:
        return SkillResult(status='succeeded', reason='already_full', text='Observed hunger 20; no food used.', details={'consumed': 0})
    before = item_counts(ui.snapshot).get(goal.item, 0)
    if before < 1: return blocked('supported_food_not_in_inventory', item=goal.item)
    if any(i.get('inventory_index') == 40 for i in ui.snapshot['items']):
        return blocked('empty_offhand_required')
    equipped = equip_item(context, EquipItem(item=goal.item), expected_session=ui.session)
    if equipped.status != 'succeeded': return equipped
    original = scene['yaw'], scene['pitch']
    while True:
        s = ui.guard()
        turning = rotate_view_timed(context, (s['yaw'], s['pitch']), (original[0], -90.), ui.session)
        context.pause(.08)
        if not turning: break
    while True:
        scene = ui.guard()
        inv = ui.read()
        current = item_counts(inv).get(goal.item, 0)
        if consumption_observed(initial_hunger, scene.get('hunger', 0), before, current):
            context.check()
            context.player.stop()  # Release use BEFORE restoring the camera.
            context.check()
            context.player.look(*original, actor_session=ui.session)
            return SkillResult(status='succeeded', reason='food_consumed', text='Observed hunger gain and fewer food items.',
                details={'item': goal.item, 'consumed': before-current, 'hunger_before': initial_hunger,
                         'hunger_after': scene['hunger']})
        if current < 1 or scene.get('holding', {}).get('item') != goal.item:
            return blocked('food_or_held_item_changed')
        if scene.get('target') or scene.get('sight_target') or scene.get('pitch', 0) > -89:
            return blocked('clear_upward_use_target_required')
        context.publish({'phase': 'eating', 'item': goal.item, 'hunger': scene.get('hunger')})
        context.check()
        context.player.drive(['use'], 6, wait=False, actor_session=ui.session)
        context.pause(.08)


CONSUME_ITEM = SkillDefinition('consume_item',
    'Eat an explicitly supported existing food while stationary, empty offhand and clear upward target. '
    'Fenced native hotbar/use; verify hunger gain AND item reduction. already_full means no food consumed. '
    'No food search, crafting or survival guarantee; leaves requested food selected.',
    ConsumeItem, consume_item)
