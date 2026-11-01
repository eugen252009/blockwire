"""Observed inventory evidence and mechanics consistency; no Minecraft acceptance claim."""
import tempfile
from pathlib import Path
import unittest
from blockwire import Player,CallableBackend
from blockwire.agent import AgentRuntime,SessionStore,decision_state_changed
from blockwire.mechanics import describe_mechanics


class EvidenceContracts(unittest.TestCase):
    def test_PE01_consumed_material_keeps_observed_peak_not_fabricated_goal(self):
        for starting in (15,16):
            with tempfile.TemporaryDirectory() as folder:
                stock={'minecraft:cobblestone':starting}
                def call(q):
                    if q['op']=='observe':return {'in_world':True,'alive':True,'actor_session':'a','player_uuid':'p','health':20.,'hunger':20,'position':[.5,64.,.5]}
                    if q['op']=='inventory':return {'items':[{'item':i,'count':n} for i,n in stock.items()],'carried':{'empty':True}}
                    if q['op']=='menu':return {}
                    if q['op']=='stop':return {}
                    raise AssertionError(q)
                class Model:
                    def decide(self, ctx):
                        stock.clear();stock.update({'minecraft:cobblestone':starting-3,'minecraft:stone_pickaxe':1})
                        return {'kind':'finish'}
                runtime=AgentRuntime(Player(CallableBackend(call)),Model(),SessionStore(Path(folder)/'state.sqlite',{'agent_id':'a','world_id':'w','player_id':'p'}),'fixture',allowed_skills=set(),max_failures=1,
                    completion_check=lambda o:o.get('inventory_high_water',{}).get('minecraft:cobblestone',0)>=16 and o['inventory'].get('minecraft:stone_pickaxe',0)>0)
                r=runtime.run();self.assertEqual(r['objective_verified'],starting==16,r)
                self.assertEqual(runtime.state['inventory_evidence']['high_water']['minecraft:cobblestone'],starting)
    def test_PE04_explicit_actor_rebind_cannot_inherit_old_collection_proof(self):
        from blockwire.goals import InventoryMilestone
        actor=['a'];stock={'minecraft:cobblestone':16}
        def call(q):
            if q['op']=='observe':return {'in_world':True,'alive':True,'actor_session':actor[0],'player_uuid':'p','health':20.,'hunger':20,'position':[.5,64.,.5]}
            if q['op']=='inventory':return {'items':[{'item':i,'count':n} for i,n in stock.items()],'carried':{'empty':True}}
            if q['op'] in {'menu','stop'}:return {}
            raise AssertionError(q)
        class Model:
            def decide(self,ctx):return {'kind':'finish'}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.sqlite';identity={'agent_id':'a','world_id':'w','player_id':'p'}
            first=AgentRuntime(Player(CallableBackend(call)),Model(),SessionStore(path,identity),'fixture',allowed_skills=set())
            first.run()
            actor[0]='b';stock.update({'minecraft:cobblestone':13,'minecraft:stone_pickaxe':1})
            second=AgentRuntime(Player(CallableBackend(call)),Model(),SessionStore(path,identity),'fixture',allowed_skills=set(),allow_rebind=True,max_failures=1,
                completion_check=InventoryMilestone(inventory={'minecraft:stone_pickaxe':1},inventory_high_water={'minecraft:cobblestone':16}))
            self.assertFalse(second.run()['objective_verified'])
            self.assertEqual(second.state['inventory_evidence']['actor_session'],'b')
            self.assertEqual(second.state['inventory_evidence']['high_water']['minecraft:cobblestone'],13)

    def test_PE03_small_native_pose_settling_does_not_discard_valid_intent(self):
        self.assertFalse(decision_state_changed({'position':[.5,64.,.501]},{'position':[.5,64.,.5]}))
        self.assertTrue(decision_state_changed({'position':[.5,64.,1.]},{'position':[.5,64.,.5]}))
        self.assertTrue(decision_state_changed({'inventory':{'minecraft:dirt':1}},{'inventory':{}}))

    def test_PE02_tool_and_mining_catalogues_agree(self):
        m=describe_mechanics()
        for rule in m['mining'].values():
            for tool in rule['accepted_held_items']:
                self.assertEqual(m['tools'][tool]['class'],rule['required_tool_class'])
        self.assertEqual(m['tools']['minecraft:wooden_hoe']['class'],'hoe')
        self.assertNotIn('minecraft:wooden_hoe',m['mining']['minecraft:stone']['accepted_held_items'])


if __name__=='__main__':unittest.main()
