"""Generic single-voxel composition, not a building/physics simulator."""
import unittest
from unittest.mock import patch
from blockwire import Player,CallableBackend
from blockwire.skills import default_registry,run_skill,SkillResult
from test_placement import World

class PlaceAtContracts(unittest.TestCase):
    def player(self,n):return Player(CallableBackend(lambda q:n.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
    def test_PA10_target_derives_observed_support_face_and_keeps_actor(self):
        n=World(True,True)
        with patch('blockwire.skills.item_actions.place_block',return_value=SkillResult(status='succeeded',reason='block_placed',text='fixture',details={'position':[2,64,0]})) as delegate:
            result=run_skill(default_registry(),self.player(n),'place_at',{'position':[2,64,0]},sleeper=lambda _:None)
        self.assertEqual(result.status,'succeeded');goal=delegate.call_args.args[1]
        self.assertEqual(goal.support,[2,63,0]);self.assertEqual(goal.face,'up');self.assertTrue(goal.auto_position)
        self.assertEqual(delegate.call_args.kwargs['expected_session'],n.session)
    def test_PA11_unknown_neighbor_never_becomes_a_support(self):
        n=World(False,False)
        with patch('blockwire.skills.item_actions.place_block') as delegate:
            result=run_skill(default_registry(),self.player(n),'place_at',{'position':[8,64,0]},sleeper=lambda _:None)
        self.assertEqual(result.reason,'placement_support_unknown');delegate.assert_not_called();self.assertEqual(n.uses,0)
    def test_PA12_uncertain_use_never_retries_another_face(self):
        class TwoSupports(World):
            def call(self,op,**q):
                v=super().call(op,**q)
                if op=='observe':v['visible_blocks']['runs'].append([0,1,0,0,1])
                return v
        for reason,expected in [('placement_not_observed',1),('no_known_placement_pose',2)]:
            n=TwoSupports(True,True)
            with patch('blockwire.skills.item_actions.place_block',return_value=SkillResult(status='blocked',reason=reason,text='fixture')) as delegate:
                result=run_skill(default_registry(),self.player(n),'place_at',{'position':[2,64,0]},sleeper=lambda _:None)
            self.assertEqual(delegate.call_count,expected);self.assertNotEqual(result.status,'succeeded')
    def test_PA13_target_already_present_needs_no_inventory_or_delegation(self):
        n=World(True,True);n.used=True;n.items.clear()
        with patch('blockwire.skills.item_actions.place_block') as delegate:
            result=run_skill(default_registry(),self.player(n),'place_at',{'position':[2,64,0]},sleeper=lambda _:None)
        self.assertEqual(result.reason,'desired_block_already_observed');delegate.assert_not_called();self.assertEqual(n.uses,0)
    def test_PA14_bcl_position_uses_same_typed_array_contract(self):
        from blockwire.bcl import default_commands,compile_bcl
        from blockwire.bcl.compiler import arguments
        r=default_commands();p=compile_bcl('I4 Bminecraft:oak_planks P[1,64,0]',r)
        self.assertEqual(arguments(p.operations[0],r.resolve('core','I4'))['position'],[1,64,0])
    def test_PA15_delegated_actor_replacement_is_rejected_before_use(self):
        n=World(True,True)
        from blockwire.skills.core import SkillContext,SkillStop
        import threading,time
        from blockwire.skills.item_actions import place_block,PlaceBlock
        # Public run_skill exercises the handler's actor guard through a trusted
        # adapter to avoid inventing any native replacement/collision outcome.
        from blockwire.skills import SkillDefinition
        r=default_registry();r.register(SkillDefinition('fenced_place','fixture',PlaceBlock,lambda c,g:place_block(c,g,expected_session='foreign')))
        result=run_skill(r,self.player(n),'fenced_place',{'support':[2,63,0]},sleeper=lambda _:None)
        self.assertEqual(result.reason,'actor_session_changed');self.assertEqual(n.uses,0)

if __name__=='__main__':unittest.main()
