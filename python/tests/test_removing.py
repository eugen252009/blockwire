"""Simulated removal postconditions; resource collection remains a separate goal."""
import unittest
from unittest.mock import patch
from blockwire.skills import default_registry,run_skill,SkillResult
from test_mining import PickupPlayer

class RemovingContracts(unittest.TestCase):
    def exercise(self,mode='clear'):
        p=PickupPlayer(False);position=[2,64,0]
        if mode=='absent':p.blocks.clear();p.cells.add((2,64,0))
        if mode=='unknown':position=[2,70,0]
        if mode=='own_support':p.blocks={(0,63,0):'minecraft:stone'};position=[0,63,0]
        if mode=='wrong':p.blocks={(2,64,0):'minecraft:cobblestone'}
        def mine(context,selected,session,navigation,observe,**kwargs):
            self.assertEqual(selected,('minecraft:stone',(2,64,0)))
            self.assertEqual(session,p.session)
            if mode=='clear':p.blocks.clear();p.cells.add((2,64,0))
            if mode=='replacement':p.session='replacement'
            return True  # A mining receipt alone must never prove removal.
        def walk(context,goal,*,expected_session=None):
            self.assertEqual(expected_session,p.session)
            return SkillResult(status='succeeded',reason='arrived',text='simulated')
        with patch('blockwire.skills.removing.mine_observed_target',side_effect=mine) as mining,patch('blockwire.skills.removing.walk_to',side_effect=walk):
            r=run_skill(default_registry(),p,'remove_block',{'block':'minecraft:stone','position':position},clock=p.clock,sleeper=p.sleep)
        self.assertEqual(r.cleanup,'released')
        return r,mining.call_count,p
    def test_RM01_removal_is_fresh_clearance_not_drop_collection(self):
        r,c,p=self.exercise();self.assertEqual(r.reason,'full_cube_removed');self.assertEqual(c,1)
        self.assertEqual(p.logs,0);self.assertFalse(r.details['drop_collection_verified'])
    def test_RM02_mining_receipt_without_clearance_is_not_success(self):
        r,c,_=self.exercise('receipt');self.assertEqual(r.reason,'removal_clearance_not_observed');self.assertEqual(c,1)
    def test_RM03_absent_full_cube_is_idempotent_without_attack(self):
        r,c,_=self.exercise('absent');self.assertEqual(r.reason,'full_cube_already_absent');self.assertEqual(c,0)
    def test_RM04_unknown_or_wrong_material_never_mined(self):
        for mode in ('unknown','wrong'):
            r,c,_=self.exercise(mode);self.assertEqual(r.reason,'exact_exposed_block_required');self.assertEqual(c,0)
    def test_RM05_replacement_invalidates_clearance(self):
        r,c,_=self.exercise('replacement');self.assertEqual(r.reason,'actor_session_changed');self.assertEqual(c,1)
    def test_RM06_own_support_retained(self):
        r,c,_=self.exercise('own_support');self.assertEqual(r.reason,'no_known_safe_mining_pose');self.assertEqual(c,0)

if __name__=='__main__':unittest.main()
