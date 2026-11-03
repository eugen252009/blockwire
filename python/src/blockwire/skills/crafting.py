"""Verified bounded native slot crafting; no recipe-order or progression planner."""
from collections import Counter
from pydantic import Field
from .core import SkillDefinition, SkillParameters, SkillResult, SkillStop
from ..recipes import RECIPES, ingredients, item_counts


def blocked(reason, **details):
    return SkillResult(status='blocked', reason=reason, text=reason.replace('_', ' '), details=details)


class CraftItem(SkillParameters):
    item: str = Field(min_length=1, max_length=128, pattern=r'^[a-z0-9_.-]+:[a-z0-9_./-]+$')
    batches: int = Field(default=1, ge=1, le=16)


class InventorySession:
    """One existing actor, native menu identity and bounded fresh clicks.

    Failure/cancel leaves partial grid/cursor visible for explicit recovery; never
    blindly replays clicks or closes a nonempty cursor (which could drop items).
    """
    def __init__(self, context):
        self.context, self.player = context, context.player
        context.check()
        scene = self.player.observe()
        if not scene.get('in_world') or not scene.get('alive'):
            raise SkillStop('blocked', 'live_player_required')
        self.session, self.health = scene['actor_session'], scene['health']
        self.snapshot = self.read()
        if not self.snapshot.get('guarded_inventory'):
            raise SkillStop('blocked', 'guarded_inventory_required_update_mod')

    def guard(self):
        self.context.check()
        s = self.player.observe()
        self.context.check()
        if s.get('actor_session') != self.session:
            raise SkillStop('blocked', 'actor_session_changed')
        if not s.get('alive') or s.get('health', 0) < self.health:
            raise SkillStop('blocked', 'damage_or_death_observed')
        self.context.renew_retained_sneak(s)
        return s

    def read(self):
        self.guard()
        self.context.check()
        value = self.player.inventory()
        self.context.check()
        if value.get('actor_session') != self.session:
            raise SkillStop('blocked', 'actor_session_changed')
        self.snapshot = value
        return value

    def ensure_open(self):
        if not self.snapshot.get('container_open'):
            self.guard()
            self.player.open_inventory(actor_session=self.session)
            self.context.pause(.08)
            self.read()
        if self.snapshot.get('menu_type') not in {'InventoryMenu', 'CraftingMenu'}:
            raise SkillStop('blocked', 'unsupported_inventory_menu')
        self.menu_id = self.snapshot['menu_id']

    def click(self, slot, button=0, mode='pickup'):
        value = self.read()
        if value.get('menu_id') != self.menu_id:
            raise SkillStop('blocked', 'inventory_menu_changed')
        self.context.publish({'phase': 'inventory_click', 'slot': slot,
                              'partial_inventory_state_possible': True})
        self.context.check()
        self.player.click_slot(slot, button, mode, menu_id=self.menu_id,
                               state_id=value['state_id'], actor_session=self.session)
        self.context.pause(.08)
        return self.read()

    def cursor_empty(self): return self.snapshot.get('carried', {}).get('empty', False)
    def slot(self, number): return next(s for s in self.snapshot['slots'] if s['slot'] == number)
    def player_slots(self): return [s for s in self.snapshot['slots'] if s.get('active') and 0 <= s.get('inventory_index', -1) < 36]

    def close_clean(self):
        if not self.cursor_empty():
            raise SkillStop('blocked', 'cursor_requires_recovery')
        grid = range(1, 10 if self.snapshot.get('menu_type') == 'CraftingMenu' else 5)
        if any(not self.slot(n).get('empty', False) for n in grid):
            raise SkillStop('blocked', 'crafting_grid_requires_recovery')
        self.guard()
        self.player.close_screen(actor_session=self.session)
        self.context.pause(.08)
        self.read()


def ensure_gameplay(context):
    """Close only a clean, supported inventory UI before an explicitly requested movement action.

    Never dismiss pause/chat/unknown menus or recover a partial cursor/grid.
    """
    context.check();scene=context.player.observe();context.check()
    if not scene.get('screen'):return
    context.check();menu=context.player.menu();context.check()
    if menu.get('type') not in {'InventoryScreen','CraftingScreen'}:return
    ui=InventorySession(context)
    if ui.session!=scene.get('actor_session'):
        raise SkillStop('blocked','actor_session_changed')
    if ui.snapshot.get('menu_type') not in {'InventoryMenu','CraftingMenu'}:
        raise SkillStop('blocked','unsupported_inventory_menu')
    ui.close_clean()


def craft_item(context, goal):
    recipe = RECIPES.get(goal.item)
    if recipe is None:
        return blocked('unsupported_recipe', item=goal.item)
    ui = InventorySession(context)
    original_open = ui.snapshot.get('container_open', False)
    if (recipe.width > 2 or recipe.height > 2) and ui.snapshot.get('menu_type') != 'CraftingMenu':
        return blocked('workbench_required', recipe=recipe.describe())
    initial = item_counts(ui.snapshot)
    # Missing materials are reported before opening or changing inventory.
    plan, missing = ingredients(recipe, initial)
    if missing:
        return blocked('missing_materials', missing=missing, recipe=recipe.describe())
    ui.ensure_open()
    width = 3 if ui.snapshot['menu_type'] == 'CraftingMenu' else 2
    grid = range(1, width*width+1)
    if not ui.cursor_empty() or any(not ui.slot(n).get('empty') for n in grid):
        return blocked('clear_cursor_and_crafting_grid_first')
    if not any(s.get('empty') for s in ui.player_slots()):
        return blocked('inventory_space_required')
    consumed = Counter()
    for batch in range(goal.batches):
        available = item_counts(ui.read())
        plan, missing = ingredients(recipe, available)
        if missing:
            return blocked('missing_materials', missing=missing, completed_batches=batch)
        for x, y, item in plan:
            ui.read()
            source = next((s for s in ui.player_slots() if s.get('item') == item), None)
            if source is None:
                return blocked('ingredient_changed', item=item)
            source_id, source_count = source['slot'], source['count']
            ui.click(source_id)
            if ui.snapshot['carried'].get('item') != item or ui.snapshot['carried'].get('count') != source_count:
                return blocked('cursor_not_confirmed', recovery_required=True)
            ui.click(1+y*width+x, 1)
            dest = ui.slot(1+y*width+x)
            if dest.get('item') != item or dest.get('count') != 1:
                return blocked('ingredient_placement_not_observed', recovery_required=True)
            if not ui.cursor_empty():
                if not ui.slot(source_id).get('empty'):
                    return blocked('source_slot_changed', recovery_required=True)
                ui.click(source_id)
            if not ui.cursor_empty():
                return blocked('cursor_not_cleared', recovery_required=True)
            consumed[item] += 1
        result = ui.slot(0)
        if result.get('item') != recipe.output or result.get('count') != recipe.count:
            return blocked('native_recipe_result_mismatch', recovery_required=True)
        ui.click(0, mode='quick_move')  # Inputs contain exactly one recipe, never a bulk stack.
        after = item_counts(ui.snapshot)
        expected = recipe.count*(batch+1)
        if after.get(recipe.output, 0)-initial.get(recipe.output, 0) != expected:
            return blocked('crafted_output_not_observed', completed_batches=batch)
        if any(initial.get(item, 0)-after.get(item, 0) != n for item, n in consumed.items()):
            return blocked('ingredient_consumption_not_observed')
        if not ui.cursor_empty() or any(not ui.slot(n).get('empty') for n in grid):
            return blocked('crafting_grid_not_cleared', recovery_required=True)
    if not original_open:
        ui.close_clean()
    return SkillResult(status='succeeded', reason='item_crafted',
        text='Observed native crafted output and ingredient consumption.',
        details={'item': recipe.output, 'crafted': recipe.count*goal.batches,
                 'batches': goal.batches, 'consumed': dict(consumed), 'inventory_counts': item_counts(ui.snapshot)})


CRAFT_ITEM = SkillDefinition('craft_item',
    'Craft one supported vanilla recipe in an empty native 2x2 inventory or already-open 3x3 workbench grid. '
    'Reports recipe/material dependencies, never selects progression. Requires free inventory space, '
    'guarded inventory mod support and exact observed output/consumption. Leaves partial UI state on failure; no blind retries.',
    CraftItem, craft_item)
