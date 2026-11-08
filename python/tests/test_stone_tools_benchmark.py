"""Deterministic strategy fixtures, NOT native gameplay/physics qualification."""
import contextlib
import copy
import importlib.util
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from blockwire.bcl.compiler import arguments
from blockwire.skills import SkillResult

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('stone_tools_benchmark', ROOT / 'examples/stone_tools_benchmark.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class World:
    """Independent state transitions at the BCL boundary; native motors tested elsewhere."""
    def __init__(self):
        self.actor = 'actor-a'; self.position = [.5, 64., .5]
        self.yaw = self.pitch = 0.
        self.health = 20.; self.items = {}; self.held = None; self.open = False
        self.logs = [('minecraft:birch_log' if y == 65 else 'minecraft:oak_log', (x, y, z))
                     for x in (1, 2) for y in (64, 65) for z in (0, 1)]
        self.stones = [(b.STONE, (x, 63, z)) for x, z in [(1,-1),(-1,-1),(0,-2),(1,-2),(-1,-2),(2,-1),(-2,-1),(0,-3),(1,-3)]]
        self.blocks = []
        self.calls = []; self.searches = 0; self.stops = 0; self.now = 0.
        self.after = lambda op: None
        self.omit = None; self.omit_mining_evidence = False
        self.cleanup = 'released'
        self.nav_actor = None
        self.cursor = {'empty': True}

    def observe(self):
        rows = self.logs + (self.stones if self.position[1] < 64 else []) + self.blocks
        palette = sorted({i for i, _ in rows})
        origin = [math.floor(self.position[0]), math.floor(self.position[1] + 1.62), math.floor(self.position[2])]
        runs = [[palette.index(i), *(p[k] - origin[k] for k in range(3)), 1] for i, p in rows]
        sight = {'id': rows[0][0], 'kind': 'block', 'position': list(rows[0][1]),
                 'aim_position': [v + .5 for v in rows[0][1]]} if rows else None
        return {'actor_session': self.actor, 'player_uuid': 'player-a', 'dimension': 'minecraft:overworld',
                'in_world': True, 'alive': True, 'on_ground': True, 'health': self.health,
                'position': self.position[:], 'eye_position': [self.position[0], self.position[1] + 1.62, self.position[2]],
                'yaw': self.yaw, 'pitch': self.pitch, 'hunger': 20, 'holding': {'item': self.held, 'empty': self.held is None},
                'screen': 'Crafting' if self.open else None, 'target': sight, 'sight_target': sight,
                'visibility': {'profile': 'sampled_surfaces_v1'}, 'search_supported': True,
                'visible_blocks': {'encoding': 'palette_x_runs_v1', 'origin': origin, 'palette': palette, 'runs': runs}}

    def inventory(self):
        return {'actor_session': self.actor, 'guarded_inventory': True, 'carried': self.cursor,
                'container_open': self.open, 'menu_type': 'CraftingMenu',
                'slots': [{'slot': i, 'empty': True} for i in range(10)],
                'items': [{'item': item, 'count': count, 'inventory_index': i}
                          for i, (item, count) in enumerate(self.items.items()) if count > 0]}

    def navigation(self, *, terrain):
        assert terrain
        x, y, z = math.floor(self.position[0]), round(self.position[1]), math.floor(self.position[2])
        cells = [{'position': [x + dx, y, z + dz], 'hazards': []} for dx in range(-3,4) for dz in range(-3,4)]
        edges = [[a, c] for a, row in enumerate(cells) for c, other in enumerate(cells) if a < c
                 and sum(abs(v - w) for v, w in zip(row['position'], other['position'])) == 1]
        return {'actor_session': self.nav_actor or self.actor, 'profile': 'stepped_full_blocks_v1', 'ready': True,
                'on_ground': True, 'health': self.health, 'position': self.position[:], 'eye_position': self.observe()['eye_position'],
                'current_center_access': True, 'current_cell': [x,y,z], 'cells': cells, 'edges': edges}

    def menu(self):
        return {'type': 'CraftingScreen' if self.open else None, 'screen_open': self.open}

    def stop(self):
        self.stops += 1

    def add(self, item, n):
        self.items[item] = self.items.get(item, 0) + n
        assert self.items[item] >= 0

    def search(self, registry, player, name, parameters, **kwargs):
        assert name == 'search' and parameters['range'] == 64
        self.searches += 1
        return SkillResult(status='succeeded' if self.logs else 'blocked',
                           reason='targets_observed' if self.logs else 'target_not_seen', text='simulated perception',
                           details={'actor_session': self.actor, 'matches': [{'id': i, 'position': list(p)} for i,p in self.logs]})

    def execute(self, source, registry):
        program = b.compile_bcl(source, registry)
        op = program.operations[0]; q = arguments(op, registry.resolve(op.namespace, op.opcode))
        code = op.opcode; self.calls.append((code, q))
        history = []
        if self.omit != code:
            if code == 'V2':
                eye = self.observe()['eye_position']; dx, dy, dz = [q[k] - eye[i] for i,k in enumerate(('x','y','z'))]
                self.yaw = math.degrees(math.atan2(-dx, dz)); self.pitch = -math.degrees(math.atan2(dy, math.hypot(dx, dz)))
            elif code == 'M0':
                self.position = [q[k] for k in ('x','y','z')]
            elif code == 'C1':
                item, _ = self.logs.pop(0); self.add(item, 1)
            elif code == 'I1':
                assert self.items[q['item']] >= 1
                self.held = q['item']; self.open = False
            elif code == 'I4':
                self.add(q['block'], -1); self.blocks.append((q['block'], tuple(q['position'])))
            elif code == 'V1':
                assert self.position[1] == 64
                self.open = True
            elif code == 'C0':
                item = q['item']; n = q.get('batches', 1)
                # Independently specified costs, not recipes.py as a fake native oracle.
                if item.endswith('_planks'):
                    self.add(item.replace('_planks', '_log'), -n); self.add(item, 4*n)
                else:
                    planks, sticks, cobble, amount = {
                        b.TABLE: (4,0,0,1), b.STICK: (2,0,0,4), b.WOOD: (3,2,0,1),
                        b.TOOLS[0]: (0,2,3,1), b.TOOLS[1]: (0,2,1,1), b.TOOLS[2]: (0,1,2,1)}[item]
                    if item in (b.WOOD, *b.TOOLS):
                        assert self.open
                    for _ in range(planks*n):
                        plank = next(i for i in b.PLANKS if self.items.get(i, 0))
                        self.add(plank, -1)
                    self.add(b.STICK, -sticks*n); self.add(b.COBBLE, -cobble*n); self.add(item, amount*n)
            elif code == 'M2':
                assert self.held == b.WOOD
                self.position[1] -= 1; self.position[2] -= 1
            elif code == 'C2':
                assert self.held == b.WOOD and self.position[1] < 64
                target = (b.STONE, tuple(q['position'])); self.stones.remove(target)
                self.add(b.COBBLE, 1)
                if not self.omit_mining_evidence:
                    history = [{'action': 'gather_block', 'status': 'succeeded',
                                'details': {'mining_targets': [{'id': b.STONE, 'position': q['position']}]}}]
            elif code == 'I3':
                assert q['jump_place'] and q['auto_position'] and q['face'] == 'up'
                self.add(q['block'], -1); self.position[1] += 1
            elif code != 'V0':
                raise AssertionError(code)
        self.after(code)
        return {'status': 'succeeded', 'program_verified': True, 'reason': 'simulated', 'cleanup': self.cleanup, 'history': history}


class SimulatedBenchmark(b.Benchmark):
    def _execute_frame(self, source, stem, bound):
        self.asserted_bound = bound
        return self.player.execute(source, self.registry)


class BenchmarkContracts(unittest.TestCase):
    def perform(self, world=None, *, configure=lambda bench: None):
        world = world or World()
        with tempfile.TemporaryDirectory() as directory:
            benchmark = SimulatedBenchmark(world, directory, 'player-a', 'fresh-test-world', clock=lambda: world.now)
            configure(benchmark)
            with patch.object(b, 'run_skill', side_effect=world.search):
                result = benchmark.run()
            saved = json.loads((Path(directory) / 'result.json').read_text())
            self.assertEqual(saved, result)
            self.assertTrue((Path(directory) / 'STARTED.json').exists())
            return result, world, benchmark

    def test_complete_sequence_materials_and_nine_distinct_stone_targets(self):
        result, world, benchmark = self.perform()
        self.assertTrue(result['objective_verified'], result)
        self.assertEqual(result['stone_harvests'], 9)
        self.assertEqual(len({tuple(h['position']) for h in benchmark.harvests}), 9)
        self.assertEqual(result['descent_steps'], result['return_placements'])
        self.assertGreaterEqual(result['return_placements'], 1)
        self.assertEqual([world.items.get(i, 0) for i in b.TOOLS], [1,1,1])
        self.assertEqual(world.items[b.COBBLE], 3)
        self.assertEqual(world.items[b.STICK], 1)
        self.assertEqual(sum(world.items.get(i,0) for i in b.PLANKS), 21 - result['descent_steps'])
        codes = [op for op,_ in world.calls]
        self.assertLess(codes.index('V2'), codes.index('C1'))
        self.assertEqual(codes.count('C1'), 8)
        self.assertLess(codes.index('M2'), codes.index('C2'))
        self.assertLess(max(i for i,c in enumerate(codes) if c=='C2'), codes.index('I3'))
        last_crafts = [q['item'] for op,q in world.calls if op == 'C0'][-3:]
        self.assertEqual(last_crafts, list(b.TOOLS))
        self.assertLess(codes.index('I3'), next(i for i,(op,q) in enumerate(world.calls) if op=='C0' and q['item'] in b.TOOLS))
        self.assertEqual(world.position, benchmark.surface)
        self.assertFalse(result['unknown_no_retry'])

    def test_receipts_without_wood_craft_descent_stone_or_ascent_never_pass(self):
        for code, reason in [('C1', 'log_pickup_not_observed'), ('C0', 'crafted_tool_or_material_not_observed'),
                             ('M2', 'descent_not_observed'), ('C2', 'stone_break_and_pickup_not_observed'),
                             ('I3', 'return_placement_and_landing_not_observed')]:
            with self.subTest(code=code):
                world = World(); world.omit = code
                result, world, _ = self.perform(world)
                self.assertFalse(result['objective_verified'])
                self.assertEqual(result['reason'], reason, result)
                self.assertEqual(sum(op == code for op,_ in world.calls), 1)

    def test_pickup_without_mining_evidence_cannot_count_as_nine_stone(self):
        world = World(); world.omit_mining_evidence = True
        result, _, _ = self.perform(world)
        self.assertEqual(result['reason'], 'stone_break_and_pickup_not_observed')
        self.assertEqual(result['stone_harvests'], 0)
        self.assertFalse(result['objective_verified'])

    def test_wrong_held_tool_prevents_stone_dispatch(self):
        world = World()
        def wrong_held(op):
            if op == 'I1' and world.position[1] < 64:
                world.held = 'minecraft:wooden_axe'
        world.after = wrong_held
        result, world, _ = self.perform(world)
        self.assertEqual(result['reason'], 'underground_pickaxe_required')
        self.assertNotIn('C2', [op for op,_ in world.calls])

    def test_no_stone_stops_at_depth_bound_without_fake_return_or_tools(self):
        world = World(); world.stones = []
        result, world, _ = self.perform(world)
        self.assertEqual(result['reason'], 'descent_bound_no_stone')
        self.assertEqual(result['descent_steps'], 8)
        self.assertNotIn('I3', [op for op,_ in world.calls])
        self.assertFalse(result['objective_verified'])

    def test_exploration_is_bounded_and_uses_only_mesh_destinations(self):
        world = World(); world.logs = []
        with patch.object(b, 'MAX_EXPLORE', 2):
            result, world, _ = self.perform(world)
        self.assertEqual(result['reason'], 'wood_exploration_bound')
        self.assertEqual(sum(op == 'M0' for op,_ in world.calls), 2)
        self.assertNotIn('C1', [op for op,_ in world.calls])
        self.assertEqual(world.searches, 12)
        self.assertFalse(result['objective_verified'])

    def test_preflight_inventory_cursor_identity_and_navigation_actor(self):
        for field, value, reason in [('items', {b.COBBLE: 9}, 'fresh_empty_gameplay_required'),
                                    ('cursor', {'empty': False}, 'partial_cursor_requires_recovery'),
                                    ('nav_actor', 'replacement', 'navigation_actor_changed')]:
            with self.subTest(field=field):
                world = World(); setattr(world, field, value)
                result, world, _ = self.perform(world)
                self.assertEqual(result['reason'], reason)
                self.assertFalse(world.calls)
        result, world, _ = self.perform(configure=lambda bench: bench.identity.update(player_id='wrong-player'))
        self.assertEqual(result['reason'], 'player_identity_mismatch')
        self.assertFalse(world.calls)

    def test_actor_damage_cancel_and_deadline_stop_after_one_frame(self):
        for condition, reason in [('actor', 'actor_session_changed'), ('health', 'damage_observed'),
                                  ('clock', 'deadline_exceeded'), ('cancel', 'cancel_requested')]:
            with self.subTest(condition=condition):
                world = World()
                def configure(bench):
                    def after(op):
                        if condition == 'actor': world.actor = 'replaced'
                        if condition == 'health': world.health = 19.
                        if condition == 'clock': world.now = 1801.
                        if condition == 'cancel': bench.cancel()
                    world.after = after
                result, world, _ = self.perform(world, configure=configure)
                self.assertEqual(result['reason'], reason, result)
                self.assertEqual(len(world.calls), 1)
                self.assertFalse(result['objective_verified'])

    def test_deadline_and_cancel_before_action_and_frame_bound(self):
        for configure, reason in [(lambda x: x.cancel(), 'cancel_requested'),
                                  (lambda x: setattr(x, 'deadline', -1), 'deadline_exceeded'),
                                  (lambda x: setattr(x, 'frames', b.MAX_FRAMES), 'frame_budget_exhausted')]:
            result, world, _ = self.perform(configure=configure)
            self.assertEqual(result['reason'], reason)
            self.assertFalse(world.calls)

    def test_expired_deadline_forbids_even_new_observations(self):
        world = World()
        with tempfile.TemporaryDirectory() as directory:
            bench = b.Benchmark(world, directory, 'player-a', 'world', clock=lambda: world.now)
            world.now = 1801.
            with patch.object(world, 'observe', wraps=world.observe) as observe:
                with self.assertRaisesRegex(b.BenchmarkStop, 'deadline_exceeded'):
                    bench.read()
                observe.assert_not_called()

    def test_unconfirmed_release_is_terminal_unknown_without_retry(self):
        world = World(); world.cleanup = 'not_confirmed'
        result, world, _ = self.perform(world)
        self.assertEqual(result['status'], 'unknown_no_retry')
        self.assertFalse(result['objective_verified'])
        self.assertEqual(len(world.calls), 1)

    def test_surface_and_final_inventory_are_required_not_model_finish(self):
        world = World()
        def drop_tool(op):
            if op == 'M0' and world.items.get(b.TOOLS[-1], 0):
                world.items[b.TOOLS[0]] = 0
        world.after = drop_tool
        result, _, _ = self.perform(world)
        self.assertFalse(result['objective_verified'])
        self.assertEqual(result['reason'], 'final_goal_not_observed')
        with tempfile.TemporaryDirectory() as directory:
            bench = b.Benchmark(World(), directory, 'player-a', 'world')
            bench.surface = [.5,64.,.5]; bench.steps = [{'from': bench.surface, 'to': [.5,63.,-.5]}]
            bench.placements = [{'position': [0,63,-1]}]
            bench.player.position[1] = 63
            with self.assertRaisesRegex(b.BenchmarkStop, 'surface_return_not_observed'):
                bench.verify_surface()

    def test_three_step_return_and_protected_stair_supports(self):
        world = World()
        world.stones = [(i, (p[0],61,p[2])) for i,p in world.stones] + [(b.STONE, (2,61,-3))]
        result, _, bench = self.perform(world)
        self.assertTrue(result['objective_verified'], result)
        self.assertEqual(result['descent_steps'], 3)
        self.assertEqual(result['return_placements'], 3)
        protected = [0,61,-2]
        self.assertNotIn(protected, [h['position'] for h in bench.harvests])
        self.assertEqual(world.position, bench.surface)

    def test_return_materials_reserved_before_any_descent(self):
        world = World()
        def lose_planks(op):
            if op == 'M0' and world.items.get(b.WOOD, 0):
                for plank in b.PLANKS:
                    world.items[plank] = 0
        world.after = lose_planks
        result, world, _ = self.perform(world)
        self.assertEqual(result['reason'], 'return_or_tool_material_reserve_missing')
        self.assertNotIn('M2', [op for op,_ in world.calls])

    def test_failed_search_is_terminal_unknown_and_never_replayed(self):
        world = World()
        def fail(*args, **kwargs):
            world.searches += 1
            return SkillResult(status='failed', reason='transport_error', text='fixture failure')
        world.search = fail
        result, world, _ = self.perform(world)
        self.assertEqual(result['status'], 'unknown_no_retry')
        self.assertEqual(world.searches, 1)
        self.assertEqual(len(world.calls), 1)

    def test_audit_failure_prevents_dispatch_and_no_used_run_is_resumed(self):
        original = b.record
        def fail(directory, name, value):
            if name.endswith('-intent.json'):
                raise OSError('simulated full disk')
            return original(directory, name, value)
        with patch.object(b, 'record', side_effect=fail):
            result, world, bench = self.perform()
        self.assertFalse(world.calls)
        self.assertEqual(result['status'], 'unknown_no_retry')
        with self.assertRaisesRegex(b.BenchmarkStop, 'benchmark_cannot_resume'):
            bench.run()

    def test_real_bcl_runner_observation_and_bound_actor_are_not_bypassed(self):
        for mismatch in (False, True):
            with self.subTest(mismatch=mismatch), tempfile.TemporaryDirectory() as directory:
                world = World(); world.logs = []
                bench = b.Benchmark(world, directory, 'player-a', 'world')
                bench.read()
                if mismatch:
                    world.actor = 'replacement'
                result = bench._execute_frame('V0', 'real-runner', 5.)
                self.assertEqual(result['program_verified'], not mismatch, result)
                self.assertEqual(result['status'], 'blocked' if mismatch else 'succeeded')
                if mismatch:
                    self.assertFalse(result['operations'])

    def test_authorization_describe_limits_and_fresh_ledger(self):
        with patch.object(b.Bridge, 'from_env', side_effect=AssertionError('must not connect')):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(b.main(['--describe']), 0)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                b.main([])
            for value in (True, float('nan'), 9, 1801):
                with self.assertRaises(ValueError):
                    b.Benchmark(None, '/unused', 'player', 'world', duration=value)
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'new'
            self.assertEqual(b.fresh_directory(p), p)
            self.assertEqual(p.stat().st_mode & 0o777, 0o700)
            with self.assertRaises(FileExistsError):
                b.fresh_directory(p)
            link = Path(directory) / 'link'; link.symlink_to(p)
            with self.assertRaises(FileExistsError):
                b.fresh_directory(link)
            b.record(p, 'data.json', {'original': True})
            with self.assertRaises(FileExistsError):
                b.record(p, 'data.json', {'original': False})


if __name__ == '__main__':
    unittest.main()
