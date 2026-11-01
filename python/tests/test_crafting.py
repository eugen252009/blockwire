"""Deterministic native-menu simulation, NOT Minecraft crafting acceptance."""
import copy
import threading
import unittest
from pydantic import ValidationError
from blockwire import Player, CallableBackend
from blockwire.skills import default_registry, run_skill


class CraftNative:
    def __init__(self, items=None, width=2):
        self.items = dict(items or {0: ('minecraft:oak_log', 2)})
        self.width, self.open = width, width == 3
        self.grid, self.carried = {}, None
        self.session, self.state = 'actor-a', 0
        self.calls, self.clicks = [], 0
        self.guard_support, self.receipts_only = True, False
        self.after_click = lambda: None
        self.selected = 0
        self.drop_result = self.return_ingredients = False

    def stack(self, item):
        return {'empty': item is None, **({'item': item[0], 'count': item[1]} if item else {})}

    def mapping(self):
        return {((36+i) if self.width == 2 else (37+i)) if i < 9 else i+(1 if self.width == 3 else 0): i for i in range(36)}

    def result(self):
        g = self.grid
        if len(g) == 1 and 1 in g and g[1][0].endswith('_log'):
            return (g[1][0].replace('_log', '_planks'), 4)
        if self.width == 2 and set(g) == {1,2,3,4} and all(i[0].endswith('_planks') for i in g.values()):
            return ('minecraft:crafting_table', 1)
        if set(g) == {1, 1+self.width} and all(i[0].endswith('_planks') for i in g.values()):
            return ('minecraft:stick', 4)
        if self.width == 3 and set(g) == {1,2,3,5,8} and all(g[i][0] == 'minecraft:stick' for i in (5,8)):
            if all(g[i][0].endswith('_planks') for i in (1,2,3)): return ('minecraft:wooden_pickaxe', 1)
            if all(g[i][0] == 'minecraft:cobblestone' for i in (1,2,3)): return ('minecraft:stone_pickaxe', 1)
        return None

    def call(self, op, **q):
        self.calls.append((op, copy.deepcopy(q)))
        if op == 'observe':
            return {'in_world': True, 'alive': True, 'actor_session': self.session, 'player_uuid': 'player-a',
                    'health': 20., 'hunger': 20, 'holding': self.stack(self.items.get(self.selected))}
        if op == 'stop': return {'text': 'released'}
        if op == 'inventory':
            out = {'items': [{**self.stack(v), 'inventory_index': i} for i, v in self.items.items()],
                   'actor_session': self.session, 'guarded_inventory': self.guard_support,
                   'container_open': self.open, 'carried': self.stack(self.carried), 'selected_hotbar': self.selected}
            if self.open:
                slots = [{**self.stack(self.result()), 'slot': 0, 'active': True}]
                slots += [{**self.stack(self.grid.get(i)), 'slot': i, 'active': True} for i in range(1, self.width**2+1)]
                slots += [{**self.stack(self.items.get(i)), 'slot': slot, 'inventory_index': i, 'active': True} for slot,i in self.mapping().items()]
                out.update(menu_type='CraftingMenu' if self.width == 3 else 'InventoryMenu', menu_id=0 if self.width == 2 else 3, state_id=self.state, slots=slots)
            return out
        assert q.get('actor_session') == self.session, 'Every inventory effect needs native fencing'
        if op == 'hotbar': self.selected = q['slot'];return {}
        if op == 'open_inventory': self.open = True; return {}
        if op == 'close_screen':
            assert not self.carried and not self.grid
            self.open = False; return {}
        if op == 'click_slot':
            assert q['state_id'] == self.state
            self.clicks += 1
            if not self.receipts_only:
                n = q['slot']
                if n == 0:
                    assert q['mode'] == 'quick_move'
                    value = self.result(); assert value
                    index = next(i for i in range(36) if i not in self.items)
                    if not self.drop_result: self.items[index] = value
                    if self.return_ingredients:
                        for ingredient in self.grid.values():
                            free = next(i for i in range(36) if i not in self.items)
                            self.items[free] = ingredient
                    self.grid.clear()
                else:
                    mapping = self.mapping()
                    store, key = (self.items, mapping[n]) if n in mapping else (self.grid, n)
                    if q['button'] == 1:
                        assert self.carried
                        item, count = self.carried
                        prior = store.get(key)
                        assert prior is None
                        store[key] = (item, 1)
                        self.carried = (item, count-1) if count > 1 else None
                    else:
                        prior = store.pop(key, None)
                        if self.carried: store[key] = self.carried
                        self.carried = prior
                self.state += 1
            self.after_click()
            return {'text': 'submitted'}
        raise AssertionError(op)


class CraftContracts(unittest.TestCase):
    def execute(self, native, item='minecraft:oak_planks', **extra):
        return run_skill(default_registry(), Player(CallableBackend(lambda q: native.call(q['op'], **{k:v for k,v in q.items() if k != 'op'}))),
                         'craft_item', {'item': item, **extra}, sleeper=lambda _: None)

    def test_CF01_planks_consume_one_log_and_verify_inventory(self):
        n = CraftNative()
        r = self.execute(n)
        self.assertEqual(r.status, 'succeeded', r)
        self.assertEqual(r.details['crafted'], 4)
        self.assertEqual(r.details['consumed'], {'minecraft:oak_log': 1})
        self.assertFalse(n.open)
        self.assertIsNone(n.carried)
        self.assertFalse(n.grid)
        self.assertEqual(n.calls[-1][0], 'stop')

    def test_CF02_missing_materials_and_workbench_are_explicit(self):
        n = CraftNative()
        self.assertEqual(self.execute(n, 'minecraft:wooden_pickaxe').reason, 'workbench_required')
        self.assertEqual(n.clicks, 0)
        self.assertEqual(self.execute(n, 'minecraft:stick').reason, 'missing_materials')
        self.assertEqual(n.clicks, 0)

    def test_CF03_table_and_sticks_use_native_two_by_two(self):
        for item, count, consumed in [('minecraft:crafting_table', 1, 4), ('minecraft:stick', 4, 2)]:
            n = CraftNative({0: ('minecraft:oak_planks', 8)})
            r = self.execute(n, item)
            self.assertEqual(r.status, 'succeeded', r)
            self.assertEqual(r.details['crafted'], count)
            self.assertEqual(r.details['consumed']['minecraft:oak_planks'], consumed)

    def test_CF04_pickaxe_in_an_already_open_native_workbench(self):
        n = CraftNative({0: ('minecraft:oak_planks', 3), 1: ('minecraft:stick', 2)}, width=3)
        r = self.execute(n, 'minecraft:wooden_pickaxe')
        self.assertEqual(r.status, 'succeeded', r)
        self.assertTrue(n.open)
        self.assertEqual(r.details['inventory_counts'], {'minecraft:wooden_pickaxe': 1})

    def test_CF05_receipts_cannot_claim_crafting(self):
        n = CraftNative();n.receipts_only = True
        r = self.execute(n)
        self.assertNotEqual(r.status, 'succeeded')
        self.assertEqual(r.reason, 'cursor_not_confirmed')
        self.assertEqual(n.clicks, 1)

    def test_CF06_actor_change_after_click_prevents_more_effects(self):
        n = CraftNative();n.after_click = lambda: setattr(n, 'session', 'replacement')
        r = self.execute(n)
        self.assertEqual(r.reason, 'actor_session_changed')
        self.assertEqual(n.clicks, 1)

    def test_CF08_cancel_leaves_partial_cursor_for_explicit_recovery(self):
        n, event = CraftNative(), threading.Event()
        n.after_click = event.set
        p = Player(CallableBackend(lambda q: n.call(q['op'], **{k:v for k,v in q.items() if k != 'op'})))
        r = run_skill(default_registry(), p, 'craft_item', {'item': 'minecraft:oak_planks'}, cancel_event=event, sleeper=lambda _: None)
        self.assertEqual(r.status, 'cancelled')
        self.assertEqual(n.clicks, 1)
        self.assertTrue(n.open)
        self.assertIsNotNone(n.carried)
        self.assertEqual(r.cleanup, 'released')

    def test_CF09_consumed_inputs_without_output_are_not_success(self):
        n = CraftNative();n.drop_result = True
        r = self.execute(n)
        self.assertEqual(r.reason, 'crafted_output_not_observed')
        self.assertNotEqual(r.status, 'succeeded')

    def test_CF10_output_without_consuming_inputs_is_not_success(self):
        n = CraftNative();n.return_ingredients = True
        r = self.execute(n)
        self.assertEqual(r.reason, 'ingredient_consumption_not_observed')
        self.assertNotEqual(r.status, 'succeeded')

    def test_CF11_stone_pickaxe_recipe_is_simulated_not_live_acceptance(self):
        n=CraftNative({0:('minecraft:cobblestone',3),1:('minecraft:stick',2)},width=3)
        r=self.execute(n,item='minecraft:stone_pickaxe')
        self.assertEqual(r.status,'succeeded',r)
        self.assertEqual(n.items,{0:('minecraft:stone_pickaxe',1)})

    def test_CF07_capability_cursor_grid_and_parameter_guards(self):
        n = CraftNative();n.guard_support = False
        self.assertEqual(self.execute(n).reason, 'guarded_inventory_required_update_mod')
        self.assertEqual(n.clicks, 0)
        n = CraftNative(width=3);n.carried = ('minecraft:stone', 1)
        self.assertEqual(self.execute(n).reason, 'clear_cursor_and_crafting_grid_first')
        self.assertEqual(n.clicks, 0)
        for batches in [True, 0, 17]:
            n = CraftNative()
            with self.assertRaises(ValidationError): self.execute(n, batches=batches)
            self.assertFalse(n.calls)


if __name__ == '__main__': unittest.main()
