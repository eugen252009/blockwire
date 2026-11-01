"""No-X-ray distance contracts; simulated observations are not live fall acceptance."""
import asyncio
import copy
import json
import math
import threading
import unittest
from unittest.mock import patch
from pydantic import ValidationError
from blockwire import CallableBackend, Player
from blockwire.skills import default_registry, run_skill


def scene(block='minecraft:dirt', position=(0, 79, 0)):
    return {'in_world': True, 'alive': True, 'actor_session': 'actor-a',
            'position': [.5, 100., .5], 'eye_position': [.5, 101.62, .5], 'health': 20.,
            'visibility': {'profile': 'sampled_surfaces_v1'}, 'sampled_at_ms': 123,
            'visible_blocks': {'encoding': 'palette_x_runs_v1', 'origin': [0, 101, 0],
                               'palette': [block], 'runs': [[0, position[0], position[1]-101, position[2], 1]]},
            'visible_interactables': []}


class DistanceContracts(unittest.TestCase):
    def measure(self, observation, **parameters):
        self.calls = []
        def backend(request):
            self.calls.append(request)
            self.assertEqual(request, {'op': 'observe'})  # Any lookup/control/stop fails.
            return copy.deepcopy(observation)
        player = Player(CallableBackend(backend))
        return run_skill(default_registry(), player, 'estimate_distance', parameters)

    def test_ED01_one_read_no_controls_and_separate_geometry(self):
        result = self.measure(scene(), target='dirt')
        self.assertEqual(result.status, 'succeeded', result)
        self.assertEqual(result.cleanup, 'not_required')
        self.assertEqual(self.calls, [{'op': 'observe'}])
        d = result.details
        self.assertEqual(d['target']['position'], [0, 79, 0])
        self.assertEqual(d['horizontal_distance_blocks'], 0.)
        self.assertEqual(d['vertical_delta_from_feet_blocks'], -20.5)
        self.assertAlmostEqual(d['eye_distance_blocks'], 22.12)
        self.assertEqual(d['reference'], 'observed_block_center')
        self.assertEqual(d['landing_safety'], 'unknown')
        self.assertNotIn('fall_estimate', d)

    def test_ED02_hidden_and_cached_renderer_target_do_not_reveal_blocks(self):
        s = scene('minecraft:stone')
        s['target'] = {'kind': 'block', 'id': 'minecraft:dirt', 'position': [0, 79, 0]}
        result = self.measure(s, target='dirt', position=[0, 79, 0])
        self.assertEqual(result.reason, 'target_not_observed')
        self.assertEqual(result.details['visibility'], 'unknown')
        self.assertIsNone(result.details['distance'])
        self.assertNotIn('fall_estimate', result.details)
        self.assertEqual(self.calls, [{'op': 'observe'}])

    def test_ED03_nearest_match_filter_and_sparse_gaps(self):
        s = scene()
        s['visible_blocks']['runs'] = [[0, -2, -2, 0, 2], [0, 2, -2, 0, 1]]
        result = self.measure(s, target='minecraft:dirt')
        self.assertEqual(result.details['target']['position'], [-1, 99, 0])
        self.assertEqual(result.details['matching_observed_blocks'], 3)
        selected = self.measure(s, target='dirt', position=[2, 99, 0])
        self.assertEqual(selected.details['target']['position'], [2, 99, 0])
        for missing in [[0, 99, 0], [1, 99, 0], [2, 98, 0]]:
            self.assertEqual(self.measure(s, target='dirt', position=missing).reason, 'target_not_observed')

    def test_ED04_fresh_sight_and_interactable_sources_without_cache(self):
        for source in ['sight_target', 'visible_interactables']:
            s = scene('minecraft:stone')
            row = {'id': 'minecraft:dirt', 'position': [0, 78, 0]}
            s[source] = row if source == 'sight_target' else [row]
            result = self.measure(s, target='dirt')
            self.assertEqual(result.status, 'succeeded')
            self.assertIn(source, result.details['target']['sources'])
        # A following call must re-observe instead of retaining a previously seen position.
        self.assertEqual(self.measure(scene('minecraft:stone'), target='dirt').reason, 'target_not_observed')

    def test_ED05_horizontal_distance_is_not_fall_height_or_safe_landing(self):
        result = self.measure(scene(position=(20, 99, 0)))
        self.assertEqual(result.details['horizontal_distance_blocks'], 20.)
        self.assertEqual(result.details['vertical_delta_from_feet_blocks'], -.5)
        self.assertEqual(result.details['landing_safety'], 'unknown')
        self.assertEqual(result.details['clear_vertical_path'], 'unknown')
        self.assertEqual(result.details['target_top_observed'], 'unknown')

    def test_ED06_geometry_does_not_depend_on_health(self):
        baseline = self.measure(scene()).details
        for health in [1., 20., None]:
            s = scene()
            if health is None:
                del s['health']
            else:
                s['health'] = health
            self.assertEqual(self.measure(s).details, baseline)

    def test_ED07_no_damage_survival_or_shape_predictions_are_returned(self):
        for identifier in ['minecraft:dirt', 'minecraft:oak_slab', 'minecraft:water', 'mod:unknown_block']:
            result = self.measure(scene(identifier), target=identifier)
            self.assertEqual(result.status, 'succeeded')
            self.assertAlmostEqual(result.details['eye_distance_blocks'], 22.12)
            for field in ['fall_estimate', 'drop_height_blocks', 'baseline_damage_hp',
                          'baseline_remaining_health_hp', 'baseline_lethal', 'safe_to_fall']:
                self.assertNotIn(field, result.model_dump_json())
            self.assertEqual(result.details['landing_safety'], 'unknown')

    def test_ED08_strict_query_validation_precedes_observation(self):
        for parameters in [{'target': 'Dirt'}, {'target': 'minecraft:dirt;run'}, {'position': [True, 1, 0]},
                           {'position': [1., 2, 3]}, {'position': [30_000_000, 0, 0]},
                           {'position': [0, 2049, 0]}, {'extra': True}, {'timeout_seconds': math.nan}]:
            with self.subTest(parameters=parameters), self.assertRaises(ValidationError):
                self.measure(scene(), **parameters)
            self.assertEqual(self.calls, [])

    def test_ED09_unsupported_profile_invalid_observation_and_expansion_cap(self):
        s = scene(); s['visibility']['profile'] = 'unsupported'
        self.assertEqual(self.measure(s).reason, 'visibility_observation_required')
        s = scene(); s['visible_blocks']['runs'][0][-1] = 338
        self.assertEqual(self.measure(s).reason, 'visibility_budget_exceeded')
        s = scene(); s['visible_blocks']['encoding'] = 'unknown'
        self.assertEqual(self.measure(s).reason, 'unsupported_surface_encoding')
        s = scene(); s['sight_target'] = {'id': 'minecraft:stone', 'position': [0, 79, 0]}
        self.assertEqual(self.measure(s).reason, 'inconsistent_visibility_observation')
        s = scene(); s['position'][1] = float('nan')
        self.assertEqual(self.measure(s).reason, 'player_position_required')

    def test_ED10_cancel_and_deadline_never_mutate_or_stop_inputs(self):
        calls = []
        player = Player(CallableBackend(lambda q: calls.append(q) or scene()))
        event = threading.Event(); event.set()
        result = run_skill(default_registry(), player, 'estimate_distance', {}, cancel_event=event)
        self.assertEqual(result.status, 'cancelled')
        self.assertEqual(calls, [])
        ticks = iter([0., 100.])
        result = run_skill(default_registry(), player, 'estimate_distance', {}, clock=lambda: next(ticks, 100.))
        self.assertEqual(result.status, 'timed_out')
        self.assertEqual(calls, [])

    def test_ED11_python_helper_uses_only_existing_observe_rpc(self):
        calls = []
        player = Player(CallableBackend(lambda q: calls.append(q) or scene()))
        result = player.estimate_distance('dirt')
        self.assertEqual(result['reason'], 'distance_estimated')
        self.assertEqual(calls, [{'op': 'observe'}])
        descriptor = next(d for d in default_registry().describe() if d['name'] == 'estimate_distance')
        self.assertFalse(descriptor['controls_player'])

    def test_ED13_measurement_does_not_claim_or_release_an_existing_control_owner(self):
        from blockwire.ownership import claim_control, release_control, control_busy
        calls = []
        player = Player(CallableBackend(lambda q: calls.append(q) or scene()))
        lease = claim_control(player, lambda: None)
        try:
            self.assertEqual(player.estimate_distance()['status'], 'succeeded')
            self.assertTrue(control_busy(player))
            self.assertEqual(calls, [{'op': 'observe'}])
        finally:
            release_control(player, lease)

    def test_ED14_cli_forwards_only_a_visible_snapshot_filter(self):
        from blockwire.cli import main
        with patch('sys.argv', ['blockwire', 'estimate_distance', 'dirt', '--position', '1', '64', '2']), patch('blockwire.cli.Bridge.from_env'), patch('blockwire.cli.Player') as factory, patch('sys.stdout'):
            factory.return_value.estimate_distance.return_value = {'status': 'succeeded'}
            main()
            factory.return_value.estimate_distance.assert_called_once_with('dirt', position=[1, 64, 2], timeout_seconds=30)

    def test_ED12_mcp_convenience_is_read_only_and_strict(self):
        try:
            from blockwire.mcp_server import create_server
        except ImportError:
            self.skipTest('Optional MCP dependencies are not installed')
        from mcp.server.fastmcp.exceptions import ToolError
        calls = []
        player = Player(CallableBackend(lambda q: calls.append(q) or scene()))
        with patch('blockwire.mcp_server.Bridge.from_env'), patch('blockwire.mcp_server.Player', return_value=player):
            server = create_server()
        async def check():
            reply = await server.call_tool('estimate_distance', {'target': 'dirt'})
            result = reply[1] if isinstance(reply, tuple) else json.loads(reply[0].text)
            self.assertEqual(result['status'], 'succeeded')
            self.assertNotIn('fall_estimate', result['details'])
            self.assertNotIn('baseline_damage_hp', json.dumps(result))
            with self.assertRaises(ToolError):
                await server.call_tool('estimate_distance', {'target': 'dirt', 'position': [True, 79, 0]})
        asyncio.run(check())
        self.assertEqual(calls, [{'op': 'observe'}])


if __name__ == '__main__':
    unittest.main()
