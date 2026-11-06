"""Presentation contracts, not Minecraft harvesting acceptance."""
import copy
import unittest
from blockwire.machine_perception import describe_scene, describe_events
from blockwire.skills.core import SkillStop


def scene():
    return {'actor_session':'fixture','sampled_at_ms':123,'eye_position':[-38.5,65.62,-6.5],
            'yaw':-225.,'visibility':{'profile':'sampled_surfaces_v1','partial':True},
            'visible_blocks':{'encoding':'palette_x_runs_v1','origin':[-39,65,-7],
                'palette':['minecraft:birch_log','minecraft:stone'],
                'runs':[[0,1,0,3,2],[1,5,0,3,1]]}}


class PerceptionContracts(unittest.TestCase):
    def test_lossless_world_coordinates_centers_no_gap_fill_or_selection(self):
        source=scene();before=copy.deepcopy(source);out=describe_scene(source)
        self.assertEqual(source,before)
        blocks=out['observed_blocks']
        self.assertEqual([b['position']for b in blocks],[[-38,65,-4],[-37,65,-4],[-34,65,-4]])
        self.assertEqual(blocks[0]['center'],[-37.5,65.5,-3.5])
        self.assertAlmostEqual(blocks[0]['eye_distance_to_center'],3.165,places=3)
        self.assertEqual(blocks[2]['id'],'minecraft:stone')
        self.assertEqual(out['yaw_normalized_degrees'],135.)
        self.assertIsNone(out['interaction_target'])
        self.assertEqual(out['visible_blocks'],source['visible_blocks'])
        self.assertNotIn('in_reach',blocks[0]);self.assertNotIn('walkable',blocks[0])
        self.assertEqual(describe_scene(out),out)

    def test_no_freshness_change_and_native_hit_not_confused_with_sight(self):
        source=scene();source['sight_target']={'id':'minecraft:birch_log','position':[-38,65,-4]}
        source['target']={'kind':'block','id':'minecraft:stone','position':[-34,65,-4]}
        snapshot={'state':{'state.scene':{'sequence':17,'data':{'observed_monotonic_ns':42,'value':source}}},'events':[]}
        before=copy.deepcopy(snapshot);result=describe_events(snapshot)
        self.assertEqual(snapshot,before);event=result['state']['state.scene']
        self.assertEqual(event['sequence'],17);self.assertEqual(event['data']['observed_monotonic_ns'],42)
        self.assertEqual(event['data']['value']['interaction_target'],source['target'])
        self.assertEqual(event['data']['value']['observed_blocks'][0]['sources'],['sight_target','visible_blocks'])

    def test_malformed_unbounded_or_inconsistent_observations_rejected(self):
        variants=[]
        for run in [[True,1,0,3,1],[0,1,0,3,338],[0,1,0,3,0],[2,1,0,3,1],[0,100,0,3,1]]:
            s=scene();s['visible_blocks']['runs']=[run];variants.append(s)
        s=scene();s['eye_position'][0]=float('nan');variants.append(s)
        s=scene();s['visible_blocks']['palette'][0]='not an id';variants.append(s)
        s=scene();s['sight_target']={'id':'minecraft:dirt','position':[-38,65,-4]};variants.append(s)
        for s in variants:
            with self.subTest(scene=s),self.assertRaises((ValueError,SkillStop)):describe_scene(s)

    def test_unsupported_observation_does_not_invent_geometry(self):
        source={'actor_session':'fixture','alive':False}
        self.assertEqual(describe_scene(source),source)
        self.assertNotIn('observed_blocks',describe_scene(source))

if __name__=='__main__':unittest.main()
