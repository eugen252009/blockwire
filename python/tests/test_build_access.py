"""Observed-graph/dispatch contracts, NOT native physics or house acceptance.

Mesh rows are independent explicit fixtures. Integration reuses the tiny voxel
fixture with mocked walking, GUI and placement. Injected scaffold ownership in
bridge cases tests teardown policy, not feasibility of constructing that bridge.
"""
import copy
from dataclasses import replace
import json
import unittest
from unittest.mock import patch

from blockwire.grounded_build import SCAFFOLD
from blockwire.skills.build_access import AccessMap, upright_body
from blockwire.skills.core import SkillStop
import test_grounded_build as fixture
from test_schematic import source_for

ACTOR = 'actor-A'
HOME = (0, 64, 0)


def mesh(points, current=HOME, edges=None):
    points = list(points)
    if edges is None:
        edges = [(a, b, 'flat') for i, a in enumerate(points) for b in points[:i]
                 if a[1] == b[1] and abs(a[0]-b[0])+abs(a[2]-b[2]) == 1]
    return {'profile': 'stepped_full_blocks_v1', 'actor_session': ACTOR, 'ready': True,
            'on_ground': True, 'current_center_access': True, 'radius': 4,
            'position': [current[0]+.5, float(current[1]), current[2]+.5], 'current_cell': list(current),
            'cells': [{'position': list(p), 'hazards': []} for p in points],
            'edges': [[points.index(a), points.index(b)] for a, b, _ in edges],
            'transitions': [{'a': points.index(a), 'b': points.index(b), 'kind': kind} for a, b, kind in edges]}


def line(start, end):
    return [(x, 64, 0) for x in range(start, end+1)]


class AccessGraphContracts(unittest.TestCase):
    def test_GA01_only_explicit_native_edges_no_blueprint_or_gap_invention(self):
        nav = mesh([HOME, (1,64,0), (2,64,0)], edges=[])
        graph = AccessMap(ACTOR).update(nav)
        self.assertIsNone(graph.route(HOME, (2,64,0)))
        nav['edges'] = [[0,2]]; nav['transitions'] = [{'a':0,'b':2,'kind':'gap_jump'}]
        graph.update(nav)
        self.assertEqual(graph.edges, {})
        self.assertIsNone(graph.route(HOME, (9,64,0)))

    def test_GA02_removing_bridge_cannot_cut_observed_return(self):
        graph = AccessMap(ACTOR).update(mesh(line(0,3)))
        self.assertEqual(len(graph.route((3,64,0), HOME)), 4)
        self.assertIsNone(graph.retreat((3,64,0), 'remove', [(1,63,0)]))
        self.assertIsNone(graph.retreat(HOME, 'remove', [(0,63,0)]))
        self.assertIsNotNone(graph.retreat(HOME, 'remove', [(1,63,0)]))

    def test_GA03_diagonal_needs_both_corner_floors_after_removal(self):
        far = (1,64,1)
        graph = AccessMap(ACTOR).update(mesh([HOME,far,(1,64,0),(0,64,1)], edges=[(HOME,far,'diagonal')]))
        self.assertIsNotNone(graph.route(far, HOME))
        self.assertIsNone(graph.retreat(far, 'remove', [(1,63,0)]))

    def test_GA04_headroom_and_both_door_cells_protect_return(self):
        graph = AccessMap(ACTOR).update(mesh(line(0,3)))
        self.assertIsNone(graph.retreat((3,64,0), 'place', [(1,65,0)]))
        self.assertIsNone(graph.retreat(HOME, 'place', [(0,65,0)]))
        self.assertIsNone(graph.retreat((3,64,0), 'place', [(1,63,0),(1,64,0)]))
        self.assertIsNotNone(graph.retreat((3,64,0), 'place', [(1,66,0)]))

    def test_GA05_step_jump_clearance_not_just_endpoint_bodies(self):
        high = (1,65,0)
        graph = AccessMap(ACTOR).update(mesh([HOME,high], edges=[(HOME,high,'step')]))
        self.assertIsNone(graph.retreat(high, 'place', [(0,67,0)]))
        self.assertIsNotNone(graph.retreat(high, 'place', [(0,68,0)]))

    def test_GA06_missing_cells_in_refreshed_window_become_unknown(self):
        graph = AccessMap(ACTOR).update(mesh(line(0,3)))
        graph.update(mesh([HOME,(2,64,0),(3,64,0)], current=(2,64,0)))
        self.assertNotIn((1,64,0), graph.nodes)
        self.assertIsNone(graph.route((3,64,0), HOME))

    def test_GA07_hazardous_diagonal_corner_cannot_be_used(self):
        far = (1,64,1)
        nav = mesh([HOME,far,(1,64,0),(0,64,1)], edges=[(HOME,far,'diagonal')])
        graph = AccessMap(ACTOR).update(nav)
        nav['cells'][2]['hazards'] = ['known_hazard']
        graph.update(nav)
        self.assertIsNone(graph.route(far, HOME))

    def test_GA08_overlap_keeps_border_edges_historical_not_fresh(self):
        graph = AccessMap(ACTOR).update(mesh(line(0,4)))
        graph.update(mesh(line(0,8), current=(4,64,0)))
        graph.update(mesh(line(4,12), current=(8,64,0)))
        plan = graph.retreat((8,64,0), 'remove', [(9,63,1)])
        self.assertIsNotNone(plan)
        self.assertEqual(plan.path[-1], HOME)
        self.assertFalse(plan.json()['all_in_latest_mesh'])
        self.assertFalse(plan.json()['traversed'])
        self.assertIsNone(graph.route((8,64,0), HOME, fresh=True))
        self.assertTrue(any(frame < graph.frame for frame in plan.edge_frames))

    def test_GA09_subtraction_never_predicts_new_air_floor_or_edges(self):
        high = (1,65,0)
        graph = AccessMap(ACTOR).update(mesh([HOME,high], edges=[(HOME,high,'step')]))
        before = set(graph.nodes)
        graph.invalidate('remove', [(1,64,0)])
        self.assertLess(set(graph.nodes), before)
        self.assertNotIn((1,64,0), graph.nodes)
        self.assertEqual(graph.edges, {})
        graph.update(mesh([HOME,(1,64,0)]))
        self.assertIsNotNone(graph.route(HOME, (1,64,0)))

    def test_GA10_schema_actor_geometry_and_indices_fail_without_partial_update(self):
        base = mesh(line(0,3)); graph = AccessMap(ACTOR).update(base)
        original = copy.deepcopy((graph.nodes, graph.edges, graph.frame))
        bad = []
        for key, value in [('actor_session','other'),('radius',8),('ready',1),('on_ground',False),('current_center_access',False)]:
            v = copy.deepcopy(base); v[key] = value; bad.append(v)
        v = copy.deepcopy(base); v['cells'][1]['position'][0] = True; bad.append(v)
        v = copy.deepcopy(base); v['cells'][1]['position'][0] = 10; bad.append(v)
        v = copy.deepcopy(base); v['cells'][1]['hazards'] = None; bad.append(v)
        v = copy.deepcopy(base); v['cells'].append(v['cells'][0]); bad.append(v)
        v = copy.deepcopy(base); v['edges'][0][0] = True; bad.append(v)
        v = copy.deepcopy(base); v['transitions'] = []; bad.append(v)
        v = mesh(line(0,3), edges=[(HOME,(2,64,0),'flat')]); bad.append(v)
        for nav in bad:
            with self.subTest(nav=nav), self.assertRaises(SkillStop): graph.update(nav)
            self.assertEqual((graph.nodes,graph.edges,graph.frame), original)

    def test_GA11_bounded_history_edges_and_route(self):
        nav = mesh(line(0,3))
        for name, value in [('MAX_NODES',3),('MAX_EDGES',2),('MAX_FRAME_EDGES',2)]:
            with patch('blockwire.skills.build_access.'+name,value), self.assertRaises(SkillStop): AccessMap(ACTOR).update(nav)
        graph = AccessMap(ACTOR).update(nav)
        with patch('blockwire.skills.build_access.MAX_ROUTE',2), self.assertRaises(SkillStop): graph.route(HOME,(3,64,0))
        for kind, changes in [('teleport',[HOME]),('remove',[]),('remove',line(0,2))]:
            with self.assertRaises(SkillStop): graph.projected(kind,changes)

    def test_GA12_native_body_envelope_is_required(self):
        native = fixture.NativeFixture(fixture.Clock())
        trace = native.call('motion_trace',limit=1)
        upright_body(trace,ACTOR,native.position)
        bad = []
        for key, value in [('actor_session','other'),('client_tick',True),('sneaking',True),('on_ground',False),
                           ('position',[99.,64.,2.5]),('bounding_box',[0.,64.,0.,2.,66.,2.])]:
            v = copy.deepcopy(trace); v['samples'][0][key] = value; bad.append(v)
        v = copy.deepcopy(trace); v['samples']=[]; bad.append(v)
        v = copy.deepcopy(trace); v['actor_session']='other'; bad.append(v)
        v = copy.deepcopy(trace); v['samples'][0]['bounding_box'][0]-=.1; v['samples'][0]['bounding_box'][3]+=.1; bad.append(v)
        for value in bad:
            with self.assertRaises(SkillStop): upright_body(value,ACTOR,native.position)

    def test_GA13_retreat_stance_must_be_from_latest_mesh(self):
        graph = AccessMap(ACTOR).update(mesh(line(0,4)))
        graph.update(mesh(line(0,8),current=(4,64,0)))
        graph.update(mesh(line(4,12),current=(8,64,0)))
        with self.assertRaises(SkillStop): graph.retreat(HOME,'place',[(9,64,1)])

    def test_GA14_cancellation_and_deadline_checks_inside_graph_work(self):
        graph = AccessMap(ACTOR).update(mesh(line(0,3)))
        count = [0]
        def check():
            count[0] += 1
            if count[0] == threshold: raise SkillStop('cancelled','cancel_requested')
        for threshold, operation in ((3,lambda: graph.update(mesh(line(0,3)))), (5,lambda: graph.route(HOME,(3,64,0))),
                                     (3,lambda: graph.projected('place',[(1,64,0)]))):
            count[0]=0; graph.check=check
            with self.assertRaises(SkillStop): operation()

    def test_GA30_reported_current_cell_must_match_actual_native_pose(self):
        graph=AccessMap(ACTOR).update(mesh(line(0,4)))
        nav=mesh(line(0,4)); nav['current_cell']=[4,64,0]
        with self.assertRaises(SkillStop) as caught: graph.update(nav)
        self.assertEqual(caught.exception.reason,'access_current_cell_position_mismatch')
        self.assertEqual(graph.current,HOME)


class AccessIntegrationContracts(unittest.TestCase):
    setUp = fixture.GroundedBuildContracts.setUp
    unit = fixture.GroundedBuildContracts.unit
    run_builder = fixture.GroundedBuildContracts.run_builder

    def allow_scaffolds(self):
        self.params = self.params.model_copy(update={'allow_scaffolds':True})

    def records(self):
        return [json.loads(s) for s in (self.root/'unit/journal.jsonl').read_text().splitlines()]

    def bridge(self):
        # Injected teardown-only fixture. Not an actual placement/admission trace.
        self.allow_scaffolds(); self.native.position=[.5,64.,.5]
        self.native.world = {(x,63,0):{'id':'minecraft:dirt','properties':{}} for x in range(4)}
        self.native.world[3,64,0]={'id':'minecraft:oak_planks','properties':{}}
        a,b = (1,64,0),(2,64,0)
        self.native.world[a]=copy.deepcopy(SCAFFOLD); self.native.world[b]=copy.deepcopy(SCAFFOLD)
        builder,guard,ledger = self.unit()
        for i,p in enumerate((a,b)):
            ticket = str(i+1)*64
            self.native.watches[ticket]=([p],True); builder.scaffolds[p]=ticket
        builder.scaffold_parents[b]={a}
        builder.nav(); builder.move((3.5,65.,.5))
        return builder,guard,a,b

    def test_GA15_bridge_cleanup_moves_to_return_side_before_removing(self):
        builder,_,a,b = self.bridge(); seen=[]
        def audit(op,q):
            if q.get('action')=='remove': seen.append((tuple(q['position']),self.native.position[:]))
        self.native.on_call=audit
        builder.cleanup_scaffolds(); builder.move(builder.guard.initial)
        self.assertEqual([p for p,_ in seen],[b,a])
        self.assertEqual(seen[0][1],[1.5,65.,.5])  # Adjacent higher stance, NOT own support.
        self.assertEqual(self.native.position,[.5,64.,.5])
        self.assertEqual(builder.removed,{a,b})
        self.assertEqual(self.native.state((3,64,0))['id'],'minecraft:oak_planks')
        plans=[r for r in self.records() if r['event']=='retreat_plan' and r['mutation']=='remove']
        self.assertEqual(len(plans),2)
        self.assertTrue(all(r['path'][-1]==[0,64,0] for r in plans))

    def test_GA16_real_mocked_side_attachment_records_child_before_parent(self):
        self.allow_scaffolds(); builder,_,_=self.unit()
        parent,child=(-1,64,1),(0,64,1)
        self.assertTrue(builder.install(parent,SCAFFOLD,temporary=True))
        option=(0.,(1.5,64.,1.5),(0.,64.5,1.5),parent,'east')
        with patch('blockwire.grounded_build.poses',return_value=[option]):
            self.assertTrue(builder.install(child,SCAFFOLD,temporary=True))
        self.assertEqual(builder.scaffold_parents[child],{parent})
        builder.cleanup_scaffolds()
        removed=[tuple(q['position']) for _,q in self.native.calls if q.get('action')=='remove']
        self.assertEqual(removed,[child,parent])  # Height/coordinate sorting alone would remove parent first.

    def test_GA17_changed_floor_stops_before_next_walking_edge(self):
        self.native.position=[.5,64.,.5]
        self.native.world={(x,63,0):{'id':'minecraft:dirt','properties':{}} for x in range(4)}
        builder,_,_=self.unit(); builder.nav()
        drives=[]
        def mutate(op,q):
            if op=='drive':
                drives.append(q); self.native.world.pop((2,63,0),None)
        self.native.on_call=mutate
        with self.assertRaises(SkillStop): builder.move((3.5,64.,.5))
        self.assertEqual(len(drives),1); self.assertEqual(self.native.position,[1.5,64.,.5])
        self.assertEqual(drives[0]['actor_session'],ACTOR)

    def test_GA18_placement_without_retreat_never_dispatches(self):
        builder,_,_=self.unit()
        with patch.object(builder,'retreat_plan',return_value=None) as plans:
            self.assertFalse(builder.install((1,64,1),{'id':'minecraft:oak_planks','properties':{}}))
        self.assertGreater(plans.call_count,0)
        self.assertFalse(any(q.get('action')=='place' for _,q in self.native.calls))

    def test_GA19_final_retreat_guard_is_required_even_after_successful_approach(self):
        self.allow_scaffolds(); builder,_,_=self.unit()
        self.assertTrue(builder.install((0,64,1),SCAFFOLD,temporary=True))
        with patch.object(builder,'sight',return_value={'hit_token':'a'*64}), patch.object(builder,'retreat_plan',return_value=None):
            with self.assertRaises(SkillStop): builder.cleanup_scaffolds()
        self.assertFalse(any(q.get('action')=='remove' for _,q in self.native.calls))

    def test_GA20_owner_is_rechecked_after_approach(self):
        self.allow_scaffolds(); builder,_,_=self.unit(); position=(0,64,1)
        self.assertTrue(builder.install(position,SCAFFOLD,temporary=True))
        original=builder.sight
        def change(*args,**kwargs):
            result=original(*args,**kwargs)
            self.native.world[position]={'id':'minecraft:oak_planks','properties':{}}
            return result
        builder.sight=change
        with self.assertRaises(SkillStop): builder.cleanup_scaffolds()
        self.assertFalse(any(q.get('action')=='remove' for _,q in self.native.calls))

    def test_GA21_new_body_reads_are_actor_fenced_and_not_reset(self):
        result=self.run_builder(); self.assertEqual(result.status,'succeeded',result)
        traces=[q for op,q in self.native.calls if op=='motion_trace']
        self.assertGreater(len(traces),3)
        self.assertTrue(all(q.get('actor_session')==ACTOR and q.get('limit')==1 and 'reset' not in q for q in traces))

    def test_GA22_home_must_be_centered_and_outside_target_clearance(self):
        self.params=self.params.model_copy(update={'origin':[1,64,2]})
        result=self.run_builder()
        self.assertEqual(result.reason,'build_home_inside_target_clearance')
        self.assertEqual(result.details['native_effects'],0)
        self.params=self.params.model_copy(update={'origin':[1,64,1]}); self.native.position[0]=1.9
        result=fixture.run_build(self.player,self.source,self.params,self.root/'uncentered',clock=self.clock,sleeper=self.clock.sleep)
        self.assertEqual(result.reason,'access_home_must_be_centered')
        self.assertEqual(result.details['native_effects'],0)

    def test_GA23_walking_legs_share_one_child_deadline(self):
        self.native.position=[.5,64.,.5]
        self.native.world={(x,63,0):{'id':'minecraft:dirt','properties':{}} for x in range(4)}
        builder,_,_=self.unit(); deadlines=[]
        def delayed(ctx,params,**kwargs):
            deadlines.append(ctx.deadline); self.clock.sleep(12); ctx.check()
            return fixture.simulated_walk(ctx,params,**kwargs)
        with patch('blockwire.grounded_build.walk_to',side_effect=delayed), self.assertRaises(SkillStop):
            builder.move((3.5,64.,.5))
        self.assertEqual(set(deadlines),{30.})
        self.assertEqual(sum(op=='drive' for op,_ in self.native.calls),2)

    def test_GA24_cancel_after_verified_placement_keeps_scaffold_accounted(self):
        self.allow_scaffolds(); builder,guard,_=self.unit(); original=builder.verify_effect
        def verified(*args,**kwargs):
            value=original(*args,**kwargs); self.cancel.set(); return value
        builder.verify_effect=verified
        with self.assertRaises(SkillStop): builder.install((0,64,1),SCAFFOLD,temporary=True)
        self.assertEqual(set(builder.scaffolds),{(0,64,1)})
        self.assertFalse(guard.pending_effect)
        self.assertFalse(any(q.get('action')=='remove' for _,q in self.native.calls))

    def test_GA25_cancel_after_verified_removal_keeps_air_accounted(self):
        self.allow_scaffolds(); builder,guard,_=self.unit(); position=(0,64,1)
        self.assertTrue(builder.install(position,SCAFFOLD,temporary=True)); original=builder.verify_effect
        def verified(*args,**kwargs):
            value=original(*args,**kwargs); self.cancel.set(); return value
        builder.verify_effect=verified
        with self.assertRaises(SkillStop): builder.cleanup_scaffolds()
        self.assertEqual(builder.removed,{position}); self.assertFalse(guard.pending_effect)

    def test_GA26_temporary_floor_cannot_be_permanent_door_support(self):
        props={'facing':'south','half':'lower','hinge':'left','open':'false','powered':'false'}
        self.source=source_for([('minecraft:spruce_door',props),('minecraft:spruce_door',dict(props,half='upper'))])
        self.allow_scaffolds(); builder,guard,_=self.unit()
        with self.assertRaises(SkillStop) as caught: builder.install((1,63,1),SCAFFOLD,temporary=True)
        self.assertEqual(caught.exception.reason,'scaffold_would_support_permanent_door')
        self.assertEqual(guard.effects,0)

    def test_GA27_lost_return_after_aim_prevents_removal(self):
        builder,_,a,b=self.bridge(); original=builder.sight
        def change(*args,**kwargs):
            probe=original(*args,**kwargs); self.native.world.pop((0,63,0),None); return probe
        builder.sight=change
        with self.assertRaises(SkillStop): builder.cleanup_scaffolds()
        self.assertFalse(any(q.get('action')=='remove' for _,q in self.native.calls))
        self.assertFalse(builder.removed)

    def test_GA28_retreat_plan_is_durable_before_native_world_dispatch(self):
        builder,_,ledger=self.unit()
        def check(op,q):
            if q.get('action')=='place':
                rows=self.records(); plans=[r for r in rows if r['event']=='retreat_plan']
                self.assertTrue(plans)
                self.assertIn(q['position'],plans[-1]['positions'])
                self.assertLess(plans[-1]['sequence'],rows[-1]['sequence'])
                self.assertEqual(rows[-1]['event'],'intent')
        self.native.on_call=check
        self.assertTrue(builder.install((1,64,1),{'id':'minecraft:oak_planks','properties':{}}))
        # The same established fsync-before-intent Ledger is used, not a new side channel.
        self.assertGreater(ledger.sequence,0)

    def test_GA29_stale_edge_fault_is_denied_before_motor_dispatch(self):
        builder,_,_=self.unit(); builder.nav(); original=builder.nav
        goal=(1,64,1)
        def stale():
            value=original(); key=tuple(sorted((builder.access.current,goal)))
            if key in builder.access.edges:
                builder.access.edges[key]=replace(builder.access.edges[key],frame=builder.access.frame-1)
            return value
        builder.nav=stale  # Deliberate internal-cache fault, not native geometry.
        with self.assertRaises(SkillStop) as caught: builder.move((1.5,64.,1.5))
        self.assertEqual(caught.exception.reason,'walk_edge_not_fresh')
        self.assertFalse(any(op=='drive' for op,_ in self.native.calls))

    def test_GA31_hard_interrupt_before_accounting_retains_uncertainty(self):
        original=fixture.Builder.verify_effect
        def interrupt(builder,*args,**kwargs):
            original(builder,*args,**kwargs)
            raise KeyboardInterrupt()
        with patch.object(fixture.Builder,'verify_effect',interrupt): result=self.run_builder()
        self.assertEqual(result.status,'cancelled')
        self.assertEqual(result.cleanup,'released')
        self.assertTrue(result.details['unknown_no_retry'])
        self.assertFalse(result.details['scaffold_inventory_complete'])
        self.assertEqual(sum(q.get('action')=='place' for _,q in self.native.calls),1)


if __name__=='__main__': unittest.main()
