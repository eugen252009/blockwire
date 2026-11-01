"""Acceptance data is not an action-order planner."""
import unittest
from blockwire.goals import InventoryMilestone


class GoalContracts(unittest.TestCase):
    def test_GO01_peak_and_current_possession_are_independent_and_both_required(self):
        g=InventoryMilestone(inventory={'minecraft:stone_pickaxe':1},inventory_high_water={'minecraft:cobblestone':16})
        self.assertTrue(g({'inventory':{'minecraft:stone_pickaxe':1,'minecraft:cobblestone':13},'inventory_high_water':{'minecraft:cobblestone':16}}))
        self.assertFalse(g({'inventory':{'minecraft:stone_pickaxe':1},'inventory_high_water':{'minecraft:cobblestone':15}}))
        self.assertFalse(g({'inventory':{'minecraft:cobblestone':16},'inventory_high_water':{'minecraft:cobblestone':16}}))
        self.assertEqual(len(g.describe()['all_of']),2)
        self.assertNotIn('actions',g.describe())
    def test_GO02_invalid_or_empty_operator_predicates_rejected(self):
        for rules in [{},{'minecraft:stone_pickaxe':True},{'stone_pickaxe':1},{'minecraft:stone_pickaxe':0},{'minecraft:stone_pickaxe':2305}]:
            with self.assertRaises(ValueError):InventoryMilestone(inventory=rules)


if __name__=='__main__':unittest.main()
