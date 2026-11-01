"""Supported-drop fixtures over the shared harvesting motor, not native stone acceptance."""
import unittest
from blockwire.skills import default_registry, run_skill
from test_woodcutting import WoodPlayer


class StonePlayer(WoodPlayer):
    def __init__(self):
        super().__init__();self.blocks={(2,64,0):'minecraft:stone'}
    def observe(self):
        s=super().observe();s['holding']={'item':'minecraft:wooden_pickaxe','enchantments':[]}
        return s
    def inventory(self):
        return {'items':[{'item':'minecraft:cobblestone','count':self.logs}] if self.logs else [],
                'carried':{'empty':True},'container_open':False}
    def drive(self, buttons, ticks, *, wait, actor_session):
        if buttons==['attack']:
            assert actor_session==self.session and ticks<=6
            self.attacks+=1;self.calls.append(('drive',buttons,ticks))
            if self.attacks>=3:
                self.blocks.clear()
                if self.pickup:self.logs+=1
        else:super().drive(buttons,ticks,wait=wait,actor_session=actor_session)


class TablePlayer(StonePlayer):
    def __init__(self):super().__init__();self.blocks={(2,64,0):'minecraft:crafting_table'}
    def observe(self):s=super().observe();s['holding']={'empty':True};return s
    def inventory(self):
        return {'items':[{'item':'minecraft:crafting_table','count':self.logs}] if self.logs else [],
                'carried':{'empty':True},'container_open':False}


class MiningContracts(unittest.TestCase):
    def test_MI02_portable_workbench_recovery_requires_actual_item_not_pickaxe(self):
        for pickup in (True,False):
            p=TablePlayer();p.pickup=pickup
            r=run_skill(default_registry(),p,'gather_block',{'block':'minecraft:crafting_table','scan':False},clock=p.clock,sleeper=p.sleep)
            self.assertEqual(r.reason,'block_drops_collected' if pickup else 'drops_not_collected',r)
            self.assertEqual(r.cleanup,'released')

    def test_MI07_exact_target_is_only_a_filter_on_fresh_exposed_blocks(self):
        for position,expected in [([2,64,0],'block_drops_collected'),([3,64,0],'no_reachable_exposed_blocks')]:
            with self.subTest(position=position):
                p=StonePlayer();r=run_skill(default_registry(),p,'gather_block',{'block':'minecraft:stone','position':position,'scan':False},clock=p.clock,sleeper=p.sleep)
                self.assertEqual(r.reason,expected,r)
                self.assertEqual(r.details['position'],position)
                if position==[3,64,0]:self.assertEqual(p.attacks,0);self.assertTrue(p.blocks)
    def test_MI08_exact_target_count_is_bounded_before_effects(self):
        from blockwire.skills.mining import GatherBlock
        with self.assertRaises(ValueError):GatherBlock(block='minecraft:dirt',position=[0,64,0],count=2)
        with self.assertRaises(ValueError):GatherBlock(block='minecraft:dirt',position=[0,64])

    def test_MI01_equipped_pick_and_observed_cobblestone_are_required(self):
        for pickup in [True,False]:
            p=StonePlayer();p.pickup=pickup
            r=run_skill(default_registry(),p,'gather_block',{'block':'minecraft:stone','scan':False},clock=p.clock,sleeper=p.sleep)
            if pickup:
                self.assertEqual(r.reason,'block_drops_collected',r)
                self.assertEqual(r.details['drop'],'minecraft:cobblestone')
                self.assertEqual(r.details['inventory_items'],1)
            else:self.assertEqual(r.reason,'drops_not_collected')
            self.assertEqual(r.cleanup,'released')


class PickupPlayer(StonePlayer):
    def __init__(self, clear=True):
        super().__init__();self.pickup=False;self.clear=clear
    def navigation(self, *, terrain=False):
        nav=super().navigation()
        if terrain:nav['profile']='stepped_full_blocks_v1'
        return nav
    def drive(self, buttons, ticks, *, wait, actor_session):
        super().drive(buttons,ticks,wait=wait,actor_session=actor_session)
        if not self.blocks and self.clear:self.cells.add((2,64,0))

class PickupContracts(unittest.TestCase):
    def exercise(self, *, clear=True, collected=True, replaced=False):
        from unittest.mock import patch
        from blockwire.skills.core import SkillResult
        p=PickupPlayer(clear);calls=[]
        def walk(context,goal,*,expected_session=None):
            calls.append(goal)
            self.assertEqual(expected_session,p.session)
            self.assertEqual((goal.x,goal.y,goal.z),(2.5,64.,.5))
            if collected:p.logs+=1
            if replaced:return SkillResult(status='blocked',reason='actor_session_changed',text='Simulated replacement')
            return SkillResult(status='succeeded',reason='arrived',text='Simulated arrival, not pickup')
        with patch('blockwire.skills.walking.walk_to',side_effect=walk):
            result=run_skill(default_registry(),p,'gather_block',{'block':'minecraft:stone','terrain':True,'scan':False},clock=p.clock,sleeper=p.sleep)
        self.assertEqual(result.cleanup,'released')
        return result,calls
    def test_MI03_fresh_same_height_pickup_cell_and_actor_fence(self):
        r,calls=self.exercise();self.assertEqual(r.reason,'block_drops_collected');self.assertEqual(len(calls),1)
    def test_MI04_unknown_pickup_floor_never_approached(self):
        r,calls=self.exercise(clear=False);self.assertEqual(r.reason,'drops_not_collected');self.assertFalse(calls)
    def test_MI05_pickup_motion_receipt_never_collection(self):
        r,calls=self.exercise(collected=False);self.assertEqual(r.reason,'drops_not_collected');self.assertEqual(len(calls),1)
    def test_MI06_pickup_actor_replacement_blocks(self):
        r,calls=self.exercise(replaced=True);self.assertEqual(r.reason,'actor_session_changed');self.assertEqual(len(calls),1)

if __name__=='__main__':unittest.main()
