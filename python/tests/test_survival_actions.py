"""Partial survival skills on deterministic fixtures, not farm/survival acceptance."""
import unittest
from pydantic import ValidationError
from blockwire import CallableBackend, Player
from blockwire.skills import default_registry, run_skill
from test_crafting import CraftNative


class FoodNative(CraftNative):
    def __init__(self):
        super().__init__({0: ('minecraft:bread', 3)})
        self.hunger, self.pitch, self.uses = 12, -90., 0
        self.gain, self.reduce = True, True
    def call(self, op, **q):
        if op == 'look':
            assert q['actor_session'] == self.session
            self.pitch = q['pitch'];return {}
        if op == 'drive':
            assert q['actor_session'] == self.session and q['buttons'] == ['use'] and q['ticks'] <= 6
            self.uses += 1
            if self.uses % 3 == 0:
                if self.gain: self.hunger = min(20, self.hunger+4)
                if self.reduce and self.items.get(0):
                    n = self.items[0][1]-1
                    if n: self.items[0] = ('minecraft:bread', n)
                    else: self.items.pop(0)
            return {'text':'submitted'}
        value = super().call(op, **q)
        if op == 'observe': value.update(hunger=self.hunger, yaw=0., pitch=self.pitch)
        return value


class SurvivalActionContracts(unittest.TestCase):
    def perform(self, native, name, params):
        now = [0.]
        def sleep(n): now[0] += n
        player = Player(CallableBackend(lambda q: native.call(q['op'], **{k:v for k,v in q.items() if k!='op'})))
        return run_skill(default_registry(), player, name, params, clock=lambda:now[0], sleeper=sleep)

    def test_SA01_consume_requires_hunger_gain_and_food_loss(self):
        for gain, reduce in [(True,True), (True,False), (False,True)]:
            n = FoodNative();n.gain, n.reduce = gain, reduce
            r = self.perform(n,'consume_item', {'item':'minecraft:bread','timeout_seconds':2.})
            if gain and reduce:
                self.assertEqual(r.reason,'food_consumed',r)
                self.assertEqual(r.details['consumed'],1)
                self.assertEqual(r.details['hunger_after'],16)
            else: self.assertNotEqual(r.status,'succeeded')
            self.assertEqual(r.cleanup,'released')

    def test_SA02_already_full_and_unsupported_food_never_use(self):
        n = FoodNative();n.hunger = 20
        self.assertEqual(self.perform(n,'consume_item',{'item':'minecraft:bread'}).reason,'already_full')
        self.assertEqual(n.uses,0)
        with self.assertRaises(ValidationError): self.perform(n,'consume_item',{'item':'minecraft:brown_mushroom'})

    def test_SA03_equip_from_main_inventory_uses_empty_hotbar_and_verifies(self):
        n = CraftNative({10:('minecraft:wooden_pickaxe',1)})
        r = self.perform(n,'equip_item',{'item':'minecraft:wooden_pickaxe'})
        self.assertEqual(r.status,'succeeded',r)
        self.assertEqual(n.selected,0)
        self.assertEqual(n.items[0],('minecraft:wooden_pickaxe',1))
        self.assertFalse(n.open)

    def test_SA04_equip_does_not_overwrite_full_hotbar(self):
        n = CraftNative({**{i:('minecraft:stone',64) for i in range(9)},10:('minecraft:wooden_pickaxe',1)})
        r = self.perform(n,'equip_item',{'item':'minecraft:wooden_pickaxe'})
        self.assertEqual(r.reason,'empty_hotbar_slot_required')
        self.assertEqual(n.clicks,0)

    def test_SA05_mining_requires_equipped_pickaxe_before_effects(self):
        n = CraftNative()
        r = self.perform(n,'gather_block',{'block':'minecraft:stone'})
        self.assertEqual(r.reason,'appropriate_equipped_tool_required')
        self.assertEqual(n.clicks,0)
        self.assertEqual([x[0] for x in n.calls],['observe','stop'])


if __name__=='__main__':unittest.main()
