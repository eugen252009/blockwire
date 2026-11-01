"""Deterministic project contracts; snapshots are simulated, NOT Minecraft acceptance."""
import copy,json,tempfile,unittest
from pathlib import Path
from blockwire.projects import ProjectJournal,ProjectPlan,enclosure_contract,material_report

IDENTITY={'agent_id':'a','world_id':'owned','player_id':'player'}
GOAL='Build an independently verified enclosure'

def plan_fixture():
    blocks=[]
    for x in (-1,0,1):
        for z in (-1,0,1):
            if (x,z)!=(0,0) and (x,z)!=(0,-1):
                for y in (64,65):blocks.append({'position':[x,y,z],'block':'minecraft:dirt','section':'walls'})
            blocks.append({'position':[x,66,z],'block':'minecraft:dirt','section':'roof'})
    return {'site':[0,64,0],'dimension':'minecraft:overworld','blocks':blocks,'sections':['walls','roof'],
            'enclosure':{'interior':[[0,64,0]],'entrance':[0,64,-1],'height':2}}

def scene_fixture(plan=None):
    plan=plan or plan_fixture();palette=list(dict.fromkeys(b['block'] for b in plan['blocks']))
    return {'actor_session':'actor','player_uuid':'player','dimension':'minecraft:overworld','alive':True,'in_world':True,'position':[0.5,64.,0.5],
            'visibility':{'profile':'sampled_surfaces_v1'},'visible_blocks':{'encoding':'palette_x_runs_v1','origin':[0,0,0],'palette':palette,
                'runs':[[palette.index(b['block']),*b['position'],1] for b in plan['blocks']]},
            'navigation':{'profile':'stepped_full_blocks_v1','ready':True,'actor_session':'actor','current_cell':[0,64,0],'current_center_access':True,
                'cells':[{'position':[0,64,0],'hazards':[]},{'position':[0,64,-1],'hazards':[]},{'position':[0,64,-2],'hazards':[]}],'edges':[[0,1],[1,2]]}}

class ProjectContracts(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'project.sqlite';self.now=1000.
    def journal(self,**kwargs):return ProjectJournal(self.path,IDENTITY,'p',GOAL,clock=lambda:self.now,**kwargs)
    def setup_plan(self,p):
        p.bind(scene_fixture());p.revise(plan_fixture())
        p.p['observed_unfulfilled']={'-1,64,-1':'minecraft:dirt'}  # Simulated earlier native missing-cube witness, not an action receipt.
    def test_PJ24_removal_invalidates_surfaces_without_a_pickup_claim(self):
        with self.journal() as p:
            self.setup_plan(p);p.observe(scene_fixture());self.assertTrue(p.p['evidence'])
            p.intent('C3 Bminecraft:dirt P[-1,64,-1]',1,'session',1)
            p.result({'session_id':'session','request_id':1,'status':'completed','result':{'operations':[
                {'command':'core:crafting.remove_block','status':'succeeded','reason':'full_cube_removed','evidence':{'position':[-1,64,-1]}}]}})
            self.assertFalse(p.p['evidence']);self.assertEqual(p.p['status'],'OBJECTIVE_INCOMPLETE')
            self.assertEqual(p.p['counters']['placement_events'],0)

    def test_PJ01_persistence_restore_stales_proof_and_never_replays_intent(self):
        with self.journal() as p:
            self.setup_plan(p);p.observe(scene_fixture(),{'minecraft:dirt':18});p.intent('I3 Bminecraft:dirt P"[0,63,0]"',1,'session',1)
        with self.journal() as p:
            self.assertTrue(p.p['plan']);self.assertTrue(p.p['pending']);self.assertFalse(p.p['progress']);p.bind(scene_fixture());self.assertIsNone(p.p['pending'])
            p.observe(scene_fixture());self.assertEqual(sum(r['status']=='correct' for r in p.p['progress'].values()),23)
            with self.assertRaises(ValueError):p.intent('I3 Bminecraft:dirt',1,'session',1)
            self.assertTrue(any(e['kind']=='interrupted_intent_not_replayed' for e in p.p['history']))
    def test_PJ02_unknown_wrong_and_native_clearance_missing_are_distinct(self):
        with self.journal() as p:
            self.setup_plan(p);s=scene_fixture();s['visible_blocks']['runs']=[];p.observe(s)
            self.assertTrue(all(r['status']=='unknown' for r in p.p['progress'].values()))
            p.observe(scene_fixture());s=scene_fixture();s['visible_blocks']['palette']=['minecraft:stone'];p.observe(s)
            self.assertTrue(all(r['status']=='wrong' for r in p.p['progress'].values()))
            self.assertTrue(any(e['kind']=='world_change_observed' for e in p.p['history']))
            s['visible_blocks']['runs']=[];s['navigation']['cells'].append({'position':[-1,64,0],'hazards':[]});p.observe(s)
            self.assertEqual(p.p['progress']['-1,64,0']['status'],'missing')
    def test_PJ03_no_false_objective_and_fresh_native_entrance_required(self):
        with self.journal() as p:
            self.setup_plan(p);p.p['observed_unfulfilled']={};p.observe(scene_fixture());self.assertEqual(p.summary()['status'],'OBJECTIVE_INCOMPLETE')
            p.begin_verification();p.observe(scene_fixture());self.assertEqual(p.summary()['status'],'OBJECTIVE_INCOMPLETE') # Existing unchanged enclosure, no observed transition.
            p.p['observed_unfulfilled']={'-1,64,-1':'minecraft:dirt'};p.observe(scene_fixture());self.assertEqual(p.summary()['status'],'OBJECTIVE_VERIFIED')
            s=scene_fixture();s['navigation']['edges']=[];p.observe(s);self.assertEqual(p.summary()['status'],'OBJECTIVE_INCOMPLETE')
    def test_PJ04_stale_evidence_never_confirms_completion(self):
        with self.journal() as p:
            self.setup_plan(p);p.p['counters']['placement_events']=1;p.begin_verification();p.observe(scene_fixture());self.now+=121
            self.assertEqual(p.summary()['status'],'OBJECTIVE_INCOMPLETE');self.assertTrue(all(r['status']=='unknown' for r in p.p['progress'].values()))
    def test_PJ05_plan_validation_rejects_holes_headroom_and_dimension(self):
        with self.journal() as p:
            p.bind(scene_fixture());plan=plan_fixture();plan['blocks']=plan['blocks'][1:]
            with self.assertRaises(ValueError):p.revise(plan)
            plan=plan_fixture();plan['blocks'].append({'position':[0,64,0],'block':'minecraft:dirt','section':'walls'})
            self.assertFalse(enclosure_contract(ProjectPlan.model_validate(plan))['valid'])
            plan=plan_fixture();plan['dimension']='other'
            with self.assertRaises(ValueError):p.revise(plan)
    def test_PJ06_material_inventory_and_recipe_arithmetic_not_a_strategy(self):
        plan=plan_fixture();plan['blocks']=[{'position':[i%8,64,i//8],'block':'minecraft:oak_planks','section':'roof'} for i in range(24)];plan['enclosure']=None
        report=material_report(ProjectPlan.model_validate(plan),{}, {'minecraft:oak_planks':8,'minecraft:oak_log':2})['minecraft:oak_planks']
        self.assertEqual(report['shortfall'],16);self.assertEqual(report['craft_options'][0]['possible_output'],8);self.assertEqual(report['craft_options'][0]['shortfall_after_this_option'],8)
    def test_PJ07_partial_batch_invalidates_old_surface_and_correlates(self):
        with self.journal() as p:
            self.setup_plan(p);p.observe(scene_fixture());p.intent('M2 north',1,'s',1)
            with self.assertRaises(ValueError):p.result({'session_id':'wrong','request_id':1,'status':'completed'})
            p.result({'session_id':'s','request_id':1,'status':'blocked','result':{'operations':[{'command':'core:movement.dig_step','status':'blocked','reason':'no_known_safe_route'}]}})
            self.assertFalse(p.p['evidence']);self.assertFalse(p.p['pending']);self.assertTrue(p.summary()['blockers']);self.assertEqual(p.summary()['status'],'OBJECTIVE_INCOMPLETE')
    def test_PJ08_death_rebind_is_explicit_and_retains_plan_not_proof(self):
        with self.journal() as p:
            self.setup_plan(p);s=scene_fixture();s.update(alive=False);p.observe(s);self.assertFalse(p.p['evidence'])
            s=scene_fixture();s['actor_session']='respawned'
            with self.assertRaises(ValueError):p.bind(s)
            with self.assertRaises(ValueError):p.bind(s,allow_rebind='false')
            p.bind(s,allow_rebind=True);self.assertTrue(p.p['plan']);self.assertFalse(p.p['inventory'])
            with self.assertRaises(ValueError):p.observe(scene_fixture())
    def test_PJ09_identity_isolation(self):
        with self.journal() as p:self.setup_plan(p)
        with self.assertRaises(ValueError):
            with ProjectJournal(self.path,{**IDENTITY,'world_id':'foreign'},'p',GOAL):pass
    def test_PJ10_durable_bounds_and_deduplicated_receipt(self):
        with self.journal() as p:
            self.setup_plan(p);p.intent('I3 Bminecraft:dirt',1,'s',1)
            r={'session_id':'s','request_id':1,'status':'completed','result':{'operations':[{'command':'core:inventory.place','status':'succeeded','reason':'block_placed','evidence':{'position':[1,64,0]}}]}}
            p.result(r);p.result(r);self.assertEqual(p.p['counters']['placement_events'],1)
            with self.assertRaises(ValueError):p.intent('I3 Bminecraft:dirt',1,'s',1)
            p.p['counters']['operations']=512
            with self.assertRaises(ValueError):p.intent('I0',2,'s',1)
    def test_PJ11_revision_stales_progress_and_rejects_duplicate_positions(self):
        with self.journal() as p:
            self.setup_plan(p);p.observe(scene_fixture());v=plan_fixture();v['reserves']={'minecraft:dirt':2};p.revise(v)
            self.assertEqual(p.p['revision'],2);self.assertFalse(p.p['progress'])
            v['blocks'].append(v['blocks'][0])
            with self.assertRaises(ValueError):p.revise(v)
    def test_PJ12_actor_bracket_and_navigation_expiry(self):
        with self.journal() as p:
            self.setup_plan(p);s=scene_fixture();s['navigation']['actor_session']='foreign'
            with self.assertRaises(ValueError):p.observe(s)
    def test_PJ23_compatible_revision_preserves_observed_change_not_current_proof(self):
        with self.journal() as p:
            self.setup_plan(p);v=plan_fixture();v['reserves']={'minecraft:dirt':1};p.revise(v)
            self.assertEqual(p.p['observed_unfulfilled'],{'-1,64,-1':'minecraft:dirt'});self.assertFalse(p.p['progress'])
            v['blocks'][0]['block']='minecraft:stone';p.revise(v)
            self.assertNotIn('-1,64,-1',p.p['observed_unfulfilled'])

    def test_PJ22_first_batch_lost_receipt_does_not_force_repeating_completed_work(self):
        with self.journal() as p:
            self.setup_plan(p);p.p['observed_unfulfilled']={};s=scene_fixture()
            s['visible_blocks']['runs']=[r for r in s['visible_blocks']['runs'] if r[1:4]!=[-1,64,-1]]
            s['navigation']['cells'].append({'position':[-1,64,-1],'hazards':[]});p.observe(s)
            p.intent('I3 Bminecraft:dirt P"[-1,63,-1]"',1,'lost',1)
        with self.journal() as p:
            p.bind(scene_fixture());p.begin_verification();p.observe(scene_fixture())
            self.assertEqual(p.p['counters']['placement_events'],0)
            self.assertEqual(p.summary()['status'],'OBJECTIVE_VERIFIED')
            with self.assertRaises(ValueError):p.intent('I3 Bminecraft:dirt P"[-1,63,-1]"',1,'lost',1)

    def test_PJ21_unrelated_old_construction_cannot_certify_new_enclosure(self):
        with self.journal() as p:
            self.setup_plan(p);p.p['observed_unfulfilled']={};p.p['counters']['placement_events']=10;p.p['constructed_targets']={'9,64,9':'minecraft:dirt'}
            p.begin_verification();p.observe(scene_fixture());self.assertEqual(p.summary()['status'],'OBJECTIVE_INCOMPLETE')

    def test_PJ20_idempotent_read_only_placement_does_not_invalidate_sweep(self):
        with self.journal() as p:
            self.setup_plan(p);p.p['counters']['placement_events']=1;p.begin_verification();p.observe(scene_fixture())
            p.intent('I3 Bminecraft:dirt',1,'s',1)
            p.result({'session_id':'s','request_id':1,'status':'completed','result':{'operations':[{'command':'core:inventory.place','status':'succeeded','reason':'desired_block_already_observed','evidence':{'position':[1,64,0]}}]}})
            self.assertTrue(p.p['final_sweep']);self.assertEqual(p.summary()['status'],'OBJECTIVE_VERIFIED');self.assertEqual(p.p['counters']['placement_events'],1)

    def test_PJ19_new_unready_geometry_revokes_previous_native_access_proof(self):
        with self.journal() as p:
            self.setup_plan(p);p.p['counters']['placement_events']=1;p.begin_verification();p.observe(scene_fixture())
            self.assertEqual(p.summary()['status'],'OBJECTIVE_VERIFIED')
            s=scene_fixture();s['navigation']={'ready':False,'reason':'unsupported'};p.observe(s)
            self.assertEqual(p.summary()['status'],'OBJECTIVE_INCOMPLETE')

    def test_PJ18_local_route_failure_preserves_existing_bounded_block_proof(self):
        with self.journal() as p:
            self.setup_plan(p);p.observe(scene_fixture());p.intent('M0 X1 Z1',1,'s',1)
            p.result({'session_id':'s','request_id':1,'status':'blocked','result':{'operations':[{'command':'core:movement.walk','status':'blocked','reason':'no_known_safe_route'}]}})
            self.assertEqual(len(p.p['evidence']),23);self.assertFalse(p.p['navigation']);self.assertEqual(p.summary()['status'],'OBJECTIVE_INCOMPLETE')

    def test_PJ17_generic_non_cube_requirements_do_not_infer_air_from_body_clearance(self):
        with self.journal(policy='blocks_v1') as p:
            p.bind(scene_fixture());plan={'site':[0,64,0],'dimension':'minecraft:overworld','sections':['plants'],
                'blocks':[{'position':[0,64,0],'block':'minecraft:short_grass','section':'plants'}]}
            p.revise(plan);s=scene_fixture(plan);p.observe(s)
            self.assertEqual(p.p['progress']['0,64,0']['status'],'correct')
            p.invalidate('fresh');s['visible_blocks']['runs']=[];p.observe(s)
            self.assertEqual(p.p['progress']['0,64,0']['status'],'unknown')

    def test_PJ16_old_batch_samples_do_not_become_fresh_at_receipt(self):
        with self.journal() as p:
            self.setup_plan(p);p.p['counters']['placement_events']=1;p.begin_verification()
            p.observe(scene_fixture(),observed_at=self.now-121)
            self.assertEqual(p.summary()['status'],'OBJECTIVE_INCOMPLETE');self.assertTrue(all(r['status']=='unknown' for r in p.p['progress'].values()))

    def test_PJ14_constructed_blocks_without_final_sweep_cannot_finish(self):
        with self.journal() as p:
            self.setup_plan(p);p.p['counters']['placement_events']=1;p.observe(scene_fixture())
            self.assertEqual(p.summary()['status'],'OBJECTIVE_INCOMPLETE');self.assertFalse(p.summary()['acceptance']['verified'])
            p.begin_verification();p.observe(scene_fixture());self.assertEqual(p.summary()['status'],'OBJECTIVE_VERIFIED')
    def test_PJ15_local_edge_without_reachable_interior_is_not_access(self):
        with self.journal() as p:
            self.setup_plan(p);p.p['counters']['placement_events']=1;p.begin_verification();s=scene_fixture()
            s['navigation'].update(current_cell=[0,64,-2],edges=[[0,1]])
            p.observe(s);self.assertEqual(p.summary()['status'],'OBJECTIVE_INCOMPLETE')

    def test_PJ13_observation_order_after_mutation_no_stale_before_snapshot(self):
        with self.journal() as p:
            self.setup_plan(p);p.intent('V0\nM2 north',1,'s',2)
            p.result({'session_id':'s','request_id':1,'status':'completed','result':{'operations':[{'command':'core:view.observe','status':'succeeded','output':scene_fixture()},{'command':'core:movement.dig_step','status':'succeeded'}]}})
            self.assertFalse(p.p['evidence'])

if __name__=='__main__':unittest.main()
