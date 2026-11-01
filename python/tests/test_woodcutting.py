"""Deterministic wood-harvest contracts; NOT Minecraft gameplay acceptance."""
import math
import threading
import unittest
from pydantic import ValidationError
from blockwire.skills import default_registry, run_skill
from blockwire.skills.woodcutting import observed_logs, _standing
from test_skills import FlatPlayer


class WoodPlayer(FlatPlayer):
    def __init__(self):
        super().__init__()
        self.blocks = {(2, 64, 0): "minecraft:oak_log"}
        self.cells.remove((2, 64, 0))
        self.logs = 0
        self.pickup = True
        self.breaks = True
        self.attacks = 0
        self.after_attack = lambda: None
        self.scene_transform = lambda s: s
        self.stale_target = False

    def navigation(self):
        nav = super().navigation()
        nav['eye_position'] = [self.position[0], self.position[1]+1.62, self.position[2]]
        return nav

    def inventory(self):
        return {"items": [{"item": "minecraft:oak_log", "count": self.logs}] if self.logs else [],
                "carried": {"empty": True}, "container_open": False}

    def observe(self):
        eye = [self.position[0], self.position[1]+1.62, self.position[2]]
        yaw, pitch = math.radians(self.yaw), math.radians(self.pitch)
        view = [-math.sin(yaw)*math.cos(pitch), -math.sin(pitch), math.cos(yaw)*math.cos(pitch)]
        target = sight = None
        palette = sorted(set(self.blocks.values()))
        origin = [math.floor(v) for v in eye]
        runs = []
        for pos, identifier in self.blocks.items():
            runs.append([palette.index(identifier), *(pos[i]-origin[i] for i in range(3)), 1])
            # Independent ray/axis-aligned cube intersection, not the skill's bearing formula.
            low, high = 0., 3.
            for i in range(3):
                if abs(view[i]) < 1e-10:
                    if not pos[i] <= eye[i] <= pos[i]+1:
                        high = -1.
                else:
                    a, b = (pos[i]-eye[i])/view[i], (pos[i]+1-eye[i])/view[i]
                    low, high = max(low, min(a, b)), min(high, max(a, b))
            if low <= high:
                sight = {"id": identifier, "position": list(pos)}
                target = {**sight, "kind": "block"}
        scene = {"in_world": True, "alive": True, "actor_session": self.session,
                 "position": self.position[:], "eye_position": eye, "yaw": self.yaw, "pitch": self.pitch,
                 "visibility": {"profile": "sampled_surfaces_v1"}, "target": target, "sight_target": sight,
                 "visible_blocks": {"encoding": "palette_x_runs_v1", "palette": palette, "origin": origin, "runs": runs}}
        if self.stale_target:
            scene['sight_target'] = None
        return self.scene_transform(scene)

    def drive(self, buttons, ticks, *, wait, actor_session):
        if buttons == ['attack']:
            assert actor_session == self.session and ticks <= 6 and not wait
            self.calls.append(('drive', buttons, ticks))
            self.attacks += 1
            target = self.observe().get('target')
            assert target and target['kind'] == 'block' and target['id'] == 'minecraft:oak_log'
            if self.breaks and self.attacks >= 3:
                self.blocks.pop(tuple(target['position']))
                if self.pickup:
                    self.logs += 1
            self.after_attack()
        else:
            super().drive(buttons, ticks, wait=wait, actor_session=actor_session)


class WoodContracts(unittest.TestCase):
    def execute(self, player, **args):
        return run_skill(default_registry(), player, 'gather_wood', {'timeout_seconds': 30., **args},
                         clock=player.clock, sleeper=player.sleep)

    def test_WD01_native_mining_inventory_gain_and_release(self):
        player = WoodPlayer()
        result = self.execute(player, scan=False)
        self.assertEqual(result.status, 'succeeded', result)
        self.assertEqual(result.reason, 'wood_collected')
        self.assertEqual(result.details['collected'], 1)
        self.assertEqual(player.attacks, 3)
        self.assertFalse(any('sneak' in c[1] for c in player.calls if c[0] == 'drive'))
        self.assertEqual(player.calls[-1], ('stop',))
        self.assertEqual(result.cleanup, 'released')

    def test_WD02_existing_logs_and_break_receipts_are_not_collection(self):
        for pickup in [False, True]:
            with self.subTest(pickup=pickup):
                player = WoodPlayer()
                player.logs, player.pickup = 8, pickup
                result = self.execute(player, scan=False)
                if pickup:
                    self.assertEqual(result.details['collected'], 1)
                    self.assertEqual(player.logs, 9)
                else:
                    self.assertEqual(result.reason, 'wood_not_collected')
                    self.assertEqual(result.status, 'blocked')

    def test_WD03_hidden_occluded_and_unsupported_logs_are_not_mined(self):
        for mode in ['no_logs', 'stale_native', 'below_feet', 'no_route', 'occluded', 'wrong_position']:
            with self.subTest(mode=mode):
                player = WoodPlayer()
                if mode == 'no_logs': player.blocks = {}
                if mode == 'stale_native': player.stale_target = True
                if mode == 'below_feet': player.blocks = {(2, 63, 0): 'minecraft:oak_log'}
                if mode == 'no_route': player.cells = {(0, 64, 0)}
                if mode == 'occluded':
                    player.scene_transform = lambda s: dict(s, target={'kind': 'block', 'id': 'minecraft:oak_leaves', 'position': [1, 64, 0]})
                if mode == 'wrong_position':
                    player.scene_transform = lambda s: dict(s, target={'kind': 'block', 'id': 'minecraft:oak_log', 'position': [1, 64, 0]})
                result = self.execute(player, scan=False)
                self.assertEqual(result.status, 'blocked')
                self.assertEqual(player.attacks, 0)
                self.assertEqual(result.cleanup, 'released')

    def test_WD04_actor_damage_danger_and_cancel_stop_before_more_attack(self):
        for mode in ['actor', 'damage', 'danger', 'cancel']:
            with self.subTest(mode=mode):
                player, event = WoodPlayer(), threading.Event()
                def interrupt():
                    if mode == 'actor': player.session = 'replacement'
                    if mode == 'damage': player.health = 19.
                    if mode == 'danger': player.transform = lambda s: dict(s, nearby_hostiles=[{'entity_id': 3}])
                    if mode == 'cancel': event.set()
                player.after_attack = interrupt
                result = run_skill(default_registry(), player, 'gather_wood', {'scan': False},
                    clock=player.clock, sleeper=player.sleep, cancel_event=event)
                self.assertEqual(result.status, 'cancelled' if mode == 'cancel' else 'blocked', result)
                self.assertEqual(player.attacks, 1)
                self.assertEqual(result.cleanup, 'released')

    def test_WD05_no_break_and_deadline_are_bounded(self):
        player = WoodPlayer()
        player.breaks = False
        self.assertEqual(self.execute(player, scan=False).reason, 'mining_not_observed')
        player = WoodPlayer()
        result = self.execute(player, timeout_seconds=.1)
        self.assertEqual(result.status, 'timed_out')
        self.assertEqual(result.cleanup, 'released')

    def test_WD06_strict_parameters_before_actions(self):
        for args in [{'count': True}, {'count': 0}, {'count': 17}, {'scan': 1}, {'extra': True}]:
            player = WoodPlayer()
            with self.subTest(args=args), self.assertRaises(ValidationError):
                self.execute(player, **args)
            self.assertFalse(player.calls)
            self.assertEqual(player.samples, 0)

    def test_WD08_stopped_scan_discovers_a_previously_out_of_view_log(self):
        player = WoodPlayer()
        def limited_view(scene):
            if scene['yaw'] < -20.:
                scene['visible_blocks'] = {'encoding': 'palette_x_runs_v1', 'origin': [0, 65, 0],
                                           'palette': [], 'runs': []}
            return scene
        player.scene_transform = limited_view
        result = self.execute(player)
        self.assertEqual(result.status, 'succeeded', result)
        first_drive = next(i for i, call in enumerate(player.calls) if call[0] == 'drive')
        self.assertGreaterEqual(sum(call[0]=='look' for call in player.calls[:first_drive]),1)
        self.assertTrue(all(request['duration_ms']==200 and request['rotation_profile']=='smoothstep'
                            for request in player.rotation_requests))
        self.assertEqual(player.rotation_requests[0]['yaw'],0.)

    def test_WD09_danger_fire_and_support_guards_precede_input(self):
        for key, value in [('nearby_hostiles', [{'entity_id': 1}]), ('on_fire', True),
                           ('ready', False), ('cells', [])]:
            player = WoodPlayer()
            player.transform = lambda s: dict(s, **{key: value})
            result = self.execute(player)
            self.assertEqual(result.status, 'blocked')
            self.assertEqual(player.calls, [('stop',)])

    def test_WD10_python_helper_dispatches_the_registered_skill(self):
        from blockwire import CallableBackend, Player
        calls = []
        def backend(request):
            calls.append(request)
            return {'profile': 'flat_full_blocks_v1', 'ready': False, 'reason': 'screen_or_pause'}
        result = Player(CallableBackend(backend)).gather_wood(1, scan=False)
        self.assertEqual(result['reason'], 'screen_or_pause')
        self.assertEqual(calls, [{'op': 'observe'}, {'op': 'navigation'}, {'op': 'stop'}])

    def test_WD11_diagonal_mining_reach_is_not_a_pickup_standing_position(self):
        player = WoodPlayer()
        target = ('minecraft:oak_log', (1, 64, 1))
        state = player.navigation()
        destination = _standing(state, target)
        self.assertIsNotNone(destination)
        self.assertNotEqual(destination, (.5, 64., .5))
        self.assertAlmostEqual(math.hypot(destination[0]-1.5, destination[2]-1.5), 1.)
        # If only the diagonal cell is supported, do not pretend pickup is covered.
        player.cells = {(0, 64, 0)}
        self.assertIsNone(_standing(player.navigation(), target))

    def test_WD12_overhead_drop_without_supported_pickup_is_not_mined(self):
        player = WoodPlayer()
        player.blocks = {(2, 66, 0): 'minecraft:oak_log'}
        result = self.execute(player, scan=False)
        self.assertEqual(result.status, 'blocked')
        self.assertEqual(player.attacks, 0)

    def test_WD07_decoder_preserves_run_gaps_and_filters_types(self):
        scene = {'visible_blocks': {'encoding': 'palette_x_runs_v1', 'origin': [-5, 70, 8],
            'palette': ['minecraft:oak_log', 'minecraft:stone'],
            'runs': [[0, -2, -1, 3, 2], [0, 2, -1, 3, 1], [1, 3, -1, 3, 1]]}}
        self.assertEqual(observed_logs(scene), [('minecraft:oak_log', (-7, 69, 11)),
                                              ('minecraft:oak_log', (-6, 69, 11)),
                                              ('minecraft:oak_log', (-3, 69, 11))])


if __name__ == '__main__':
    unittest.main()
