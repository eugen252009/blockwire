"""Read-only reticle geometry contracts; not live Minecraft acceptance."""
import asyncio
import copy
import json
import threading
import unittest
from unittest.mock import patch
from pydantic import ValidationError
from blockwire import CallableBackend, Player
from blockwire.skills import default_registry, run_skill
from blockwire.skills.looking import describe_look_around


def scene():
    return {'in_world': True, 'alive': True, 'actor_session': 'actor-a', 'sampled_at_ms': 123,
            'position': [.5, 62.88, .5], 'eye_position': [.5, 64.5, .5], 'yaw': 0., 'pitch': 0.,
            'visibility': {'profile': 'sampled_surfaces_v1'},
            'sight_target': {'id': 'minecraft:oak_log', 'position': [0, 64, 10], 'aim_position': [.5, 64.5, 10.]},
            'visible_blocks': {'encoding': 'palette_x_runs_v1', 'origin': [0, 64, 0],
                               'palette': ['minecraft:oak_log'], 'runs': [[0, 0, 0, 10, 1], [0, 2, 0, 10, 2],
                                                                        [0, 0, 0, 16, 1], [0, 0, 0, 5, 1]]}}


class LookAroundContracts(unittest.TestCase):
    def player(self, value):
        self.calls = []
        def call(request):
            self.calls.append(request)
            self.assertEqual(request, {'op': 'observe'})
            return copy.deepcopy(value)
        return Player(CallableBackend(call))

    def test_cone_window_distances_and_no_input_ownership(self):
        from blockwire.ownership import claim_control, release_control, control_busy
        player = self.player(scene()); lease = claim_control(player, lambda: None)
        try:
            try:result = player.look_around()
            except RuntimeError as error:self.fail('Read-only report tried to claim input ownership: '+str(error))
            self.assertTrue(control_busy(player))
        finally:
            release_control(player, lease)
        self.assertEqual(result['status'], 'succeeded'); self.assertEqual(result['cleanup'], 'not_required')
        rows = result['details']['blocks']
        self.assertEqual({tuple(r['position']) for r in rows}, {(0, 64, 10), (2, 64, 10), (0, 64, 5)})
        self.assertEqual(rows[0]['distance_blocks'], 10.)
        self.assertEqual(len(rows[0]['sources']), 2)  # Deduplicated forward/sampled surface.
        self.assertEqual(self.calls, [{'op': 'observe'}])
        self.assertTrue(result['details']['partial_visibility'])
        self.assertFalse(result['details']['interaction_reach_verified'])

    def test_window_is_reticle_centred_not_player_centred(self):
        s = scene(); s['sight_target'].update(position=[0, 64, 30], aim_position=[.5, 64.5, 30.])
        s['visible_blocks']['runs'] = [[0, 5, 0, 30, 2]]
        rows = self.player(s).look_around()['details']['blocks']
        self.assertEqual({tuple(r['position']) for r in rows}, {(0, 64, 30), (5, 64, 30)})
        self.assertEqual(rows[0]['distance_blocks'], 30.)

    def test_pitch_yaw_and_wrapped_yaw(self):
        for yaw in (90., 450., -270.):
            s = scene(); s['yaw'] = yaw; s.pop('visible_blocks')
            s['sight_target'].update(position=[-10, 64, 0], aim_position=[-9., 64.5, .5])
            rows = self.player(s).look_around()['details']['blocks']
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['angle_degrees'], 0.)
        s = scene(); s['pitch'] = 90.; s.pop('visible_blocks')
        s['sight_target'].update(position=[0, 59, 0], aim_position=[.5, 60., .5])
        rows = self.player(s).look_around()['details']['blocks']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['distance_blocks'], 5.)

    def test_no_hit_never_uses_renderer_cache_or_invents_air_anchor(self):
        s = scene(); s['target'] = s.pop('sight_target')
        result = self.player(s).look_around()
        self.assertEqual(result['reason'], 'crosshair_anchor_not_observed')
        self.assertEqual(result['details']['blocks'], [])
        self.assertNotIn('anchor', result['details'])

    def test_unknown_cells_entities_and_snapshot_are_not_expanded(self):
        s = scene(); original = copy.deepcopy(s)
        result = describe_look_around(s)
        self.assertEqual(s, original)
        self.assertEqual(result.details['sampled_at_ms'], 123)
        self.assertIn('unsupported', result.details['entities_status'])
        self.assertNotIn((1, 64, 10), {tuple(r['position']) for r in result.details['blocks']})

    def test_invalid_geometry_profile_and_bounded_expansion(self):
        changes = [lambda s: s.update(yaw=float('nan')), lambda s: s.update(pitch=91.),
                   lambda s: s['sight_target'].update(aim_position=[100., 64.5, 10.]),
                   lambda s: s['visibility'].update(profile='unknown'),
                   lambda s: s['visible_blocks']['runs'].append([0, 0, 0, 0, 338])]
        for change in changes:
            s = scene(); change(s)
            result = self.player(s).look_around()
            self.assertEqual(result['status'], 'blocked', result)
            self.assertEqual(self.calls, [{'op': 'observe'}])

    def test_strict_parameters_and_cancel_before_and_after_read(self):
        p = self.player(scene())
        with self.assertRaises(ValidationError):run_skill(default_registry(), p, 'look_around', {'radius': 100})
        self.assertEqual(self.calls, [])
        event = threading.Event(); event.set()
        self.assertEqual(run_skill(default_registry(), p, 'look_around', {}, cancel_event=event).status, 'cancelled')
        self.assertEqual(self.calls, [])
        event.clear()
        def call(request):
            self.assertEqual(request, {'op': 'observe'}); event.set(); return scene()
        result = run_skill(default_registry(), Player(CallableBackend(call)), 'look_around', {}, cancel_event=event)
        self.assertEqual(result.status, 'cancelled'); self.assertEqual(result.cleanup, 'not_required')
        ticks = iter([0., 100.])
        result = run_skill(default_registry(), p, 'look_around', {}, clock=lambda: next(ticks, 100.))
        self.assertEqual(result.status, 'timed_out'); self.assertEqual(self.calls, [])

    def test_cli(self):
        from blockwire.cli import main
        with patch('blockwire.cli.Bridge.from_env'), patch('blockwire.cli.Player') as factory, patch('sys.stdout'):
            factory.return_value.look_around.return_value = {'status': 'succeeded'}
            main(['look_around'])
            factory.return_value.look_around.assert_called_once_with(timeout_seconds=30)

    def test_mcp_fresh_and_machine_cached_paths(self):
        from blockwire.mcp_server import create_server
        from blockwire.machine_mcp import create_machine_server
        from blockwire.bcl.machine import STATE_EVENTS
        p = self.player(scene())
        with patch('blockwire.mcp_server.Bridge.from_env'), patch('blockwire.mcp_server.Player', return_value=p):
            server = create_server()
        def unpack(reply):return reply[1] if isinstance(reply, tuple) else json.loads(reply[0].text)
        class Client:
            profile = 'machine-v1'; bind = {'actor_session': 'actor-a'}; reader = None; control_state = {}
            async def __aenter__(self):return self
            async def __aexit__(self, *args):pass
            async def report(self, channels):
                for name in STATE_EVENTS:
                    await self.events.put({'type': 'event', 'event_type': name, 'sequence': 17,
                        'data': {'actor_session': 'actor-a', 'observed_monotonic_ns': 42,
                                 'value': scene() if name == 'state.scene' else {}}})
                return {'status': 'completed'}
        async def check():
            direct = unpack(await server.call_tool('look_around', {}))
            self.assertEqual(direct['reason'], 'view_reported')
            client = Client(); client.events = asyncio.Queue()
            machine = create_machine_server(client)
            missing = unpack(await machine.call_tool('look_around', {}))
            self.assertEqual(missing['reason'], 'scene_event_unavailable')
            async with machine.settings.lifespan(machine):
                await client.events.put({'type': 'event', 'event_type': 'command.completed', 'data': {'task_id': 'fixture'}})
                await asyncio.sleep(.02)
                cached = unpack(await machine.call_tool('look_around', {}))
                self.assertTrue(cached['cached']); self.assertEqual(cached['source_metadata']['observed_monotonic_ns'], 42)
                self.assertEqual(cached['details'], direct['details'])
                events = unpack(await machine.call_tool('events', {}))
                self.assertIn('state.scene', events['state'])
                self.assertEqual(events['events'][0]['data']['task_id'], 'fixture')
                bad = scene(); bad['actor_session'] = 'replacement'
                await client.events.put({'type': 'event', 'event_type': 'state.scene',
                    'data': {'actor_session': 'actor-a', 'value': bad}})
                await asyncio.sleep(.02)
                from mcp.server.fastmcp.exceptions import ToolError
                with self.assertRaises(ToolError):await machine.call_tool('look_around', {})
        asyncio.run(check())
        self.assertEqual(self.calls, [{'op': 'observe'}])
