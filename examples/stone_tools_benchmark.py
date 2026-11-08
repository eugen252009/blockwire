#!/usr/bin/env python3
"""Explicit deterministic Survival benchmark over legacy BCL/1, without an LLM.

Run ONLY on an operator-created fresh, isolated Survival world, empty inventory,
no bonus chest/gifts/other players. This program does not create/select a world.
See docs/stone-tools-benchmark.md. --describe is offline; importing does nothing.
"""
import argparse
import json
import math
import os
from pathlib import Path
import signal
import threading
import time

from blockwire import Bridge, Player
from blockwire.bcl import compile_bcl, default_commands
from blockwire.bcl.modal import Modal
from blockwire.bcl.runtime import BCLRunner
from blockwire.recipes import PLANKS, RECIPES, SPECIES, ingredients, item_counts
from blockwire.skills import run_skill
from blockwire.skills.approaching import _reachable
from blockwire.skills.looking import describe_look_around
from blockwire.skills.woodcutting import LOGS, _standing, observed_blocks

VERSION = 'stone-tools-benchmark-v1'
WOOD = 'minecraft:wooden_pickaxe'
STONE = 'minecraft:stone'
COBBLE = 'minecraft:cobblestone'
TABLE = 'minecraft:crafting_table'
STICK = 'minecraft:stick'
TOOLS = ('minecraft:stone_pickaxe', 'minecraft:stone_shovel', 'minecraft:stone_sword')
LOG_GOAL = 8                         # 32 planks: 4 table + 3 pick + 4 sticks + 21 reserve
STONE_GOAL = 9                       # nine DISTINCT exact stone harvests, not receipts
MAX_DEPTH = 8
MAX_EXPLORE = 32
MAX_FRAMES = 512
DIRECTIONS = ((0, -1), (1, 0), (0, 1), (-1, 0))


def describe():
    return {'version': VERSION, 'strategy': 'explicit deterministic Python, legacy BCL/1; no model',
            'stages': ['look around', 'find and collect 8 logs', 'craft/equip wooden pickaxe',
                       'dig descending supported steps', 'harvest at least 9 distinct stone blocks with pickaxe',
                       'jump-place planks and retrace steps to surface', 'craft stone pickaxe, shovel, sword'],
            'bounds': {'seconds': 1800, 'descent_steps': MAX_DEPTH, 'exploration_moves': MAX_EXPLORE,
                       'exploration_radius_blocks': 64, 'bcl_frames': MAX_FRAMES},
            'world': 'Operator-created fresh isolated Survival world; no seed/spawn selection, gifts or cheats.',
            'acceptance': 'Observed inventory gains, exact-target mining evidence, descent, consumed return blocks, grounded surface return and all three final tools.',
            'limits': 'Client observations are partial, not server/save certification; freshness and Survival mode are operator attestations.',
            'graphical_acceptance': 'NOT RUN'}


def record(directory, name, value):
    """Exclusive durable files: no old ledger is overwritten or resumed."""
    with (directory / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def fresh_directory(path):
    # Refuse existing directories too, including empty ones and symlinks.
    path = Path(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=False)
    return path


def require(condition, reason):
    if not condition:
        raise BenchmarkStop(reason)


class BenchmarkStop(RuntimeError):
    pass


class Benchmark:
    def __init__(self, player, directory, player_uuid, world_id, *, duration=1800., clock=time.monotonic):
        if type(duration) not in (int, float) or not math.isfinite(duration) or not 10 <= duration <= 1800:
            raise ValueError('duration must be finite, 10..1800 seconds')
        if any(not isinstance(v, str) or not 1 <= len(v) <= 128 for v in (player_uuid, world_id)):
            raise ValueError('Explicit bounded player/world identities required')
        self.player, self.directory, self.clock = player, Path(directory), clock
        self.identity = {'agent_id': VERSION, 'world_id': world_id, 'player_id': player_uuid}
        self.duration, self.deadline = duration, clock() + duration
        self.registry = default_commands()  # Built-ins only; no providers or machine-v1 migration.
        self.cancelled = threading.Event()
        self.active = None
        self.actor = self.dimension = self.health = None
        self.phase, self.frames, self.scans = 'preflight', 0, 0
        self.cleanup, self.unknown = 'not_required', False
        self.surface = self.table = None
        self.steps, self.harvests, self.placements = [], [], []
        self.started = False

    def cancel(self):
        self.cancelled.set()
        if self.active is not None:
            self.active.cancel()

    def check(self):
        require(not self.cancelled.is_set(), 'cancel_requested')
        require(self.clock() < self.deadline, 'deadline_exceeded')

    def _scene(self, scene):
        require(scene.get('in_world') is True and scene.get('alive') is True, 'live_player_required')
        require(scene.get('player_uuid') == self.identity['player_id'], 'player_identity_mismatch')
        actor = scene.get('actor_session')
        require(isinstance(actor, str) and 1 <= len(actor) <= 128, 'actor_session_required')
        require(scene.get('visibility', {}).get('profile') == 'sampled_surfaces_v1', 'visibility_required')
        require(all(type(v) in (int, float) and math.isfinite(v) for v in scene['position']), 'finite_pose_required')
        if self.actor is None:
            self.actor, self.dimension, self.health = actor, scene['dimension'], scene['health']
        require(actor == self.actor and scene['dimension'] == self.dimension, 'actor_session_changed')
        require(scene['health'] >= self.health, 'damage_observed')

    def read(self):
        self.check(); scene = self.player.observe(); self.check(); self._scene(scene)
        self.check(); inventory = self.player.inventory(); self.check()
        require(inventory.get('actor_session') == self.actor, 'inventory_actor_changed')
        require(inventory.get('guarded_inventory') is True, 'guarded_inventory_required')
        require(inventory.get('carried', {}).get('empty') is True, 'partial_cursor_requires_recovery')
        if inventory.get('container_open'):
            require(inventory.get('menu_type') in {'InventoryMenu', 'CraftingMenu'}, 'unsupported_container')
            grid = range(1, 10 if inventory['menu_type'] == 'CraftingMenu' else 5)
            require(not any(r.get('slot') in grid and not r.get('empty') for r in inventory.get('slots', [])),
                    'partial_grid_requires_recovery')
        self.check(); scene = self.player.observe(); self.check(); self._scene(scene)
        return scene, inventory

    def mesh(self):
        scene, _ = self.read()
        self.check(); nav = self.player.navigation(terrain=True); self.check()
        require(nav.get('actor_session') == self.actor, 'navigation_actor_changed')
        require(nav.get('ready') and nav.get('profile') == 'stepped_full_blocks_v1', 'supported_navigation_required')
        require(nav.get('on_ground') is True and scene.get('on_ground') is True, 'grounded_pose_required')
        require(nav.get('current_center_access') and not nav.get('on_fire') and not nav.get('nearby_hostiles'), 'unsafe_navigation')
        require(nav['health'] >= self.health and math.dist(nav['position'], scene['position']) <= .2, 'unstable_navigation')
        require(tuple(nav['current_cell']) in _reachable(nav, True), 'supported_source_required')
        return nav

    def _execute_frame(self, source, stem, bound):
        runner = BCLRunner(source, self.registry, self.player, self.directory / (stem + '.sqlite'),
                           self.identity, self.actor, duration_seconds=bound,
                           contexts=(Modal(timeout_seconds=bound),))
        self.active = runner
        try:
            self.check()  # Includes cancellation arriving during construction/audit writes.
            return runner.run()
        finally:
            self.active = None

    def frame(self, source, *, seconds=60.):
        self.check(); self.read()
        require(self.frames < MAX_FRAMES, 'frame_budget_exhausted')
        program = compile_bcl(source, self.registry)
        require(len(program.operations) == 1, 'one_observed_action_per_frame_required')
        bound = min(seconds, self.deadline - self.clock())
        require(bound >= .1, 'deadline_exceeded')
        stem = f'{self.frames:04d}'
        record(self.directory, stem + '-intent.json', {'phase': self.phase, 'bcl': source,
               'actor_session': self.actor, 'program_digest': program.digest, 'timeout_seconds': bound})
        self.frames += 1
        self.check()
        self.cleanup = 'not_confirmed'
        result = self._execute_frame(source, stem, min(bound, self.deadline - self.clock()))
        self.cleanup = result.get('cleanup', 'not_confirmed')
        self.unknown |= (self.cleanup != 'released' or result.get('status') == 'failed'
                         or result.get('reason') in {'transport_error', 'handler_error'}
                         or any(h.get('reason') in {'transport_error', 'handler_error'} for h in result.get('history', [])))
        record(self.directory, stem + '-result.json', result)
        require(result.get('program_verified') is True and result.get('status') == 'succeeded'
                and self.cleanup == 'released', 'bcl_stopped:' + str(result.get('reason')))
        self.check(); self.read()  # Receipt and even program success do not certify benchmark goals.
        return result

    def aim(self, point):
        self.frame('V2 X={} Y={} Z={}'.format(*point), seconds=15.)

    def walk(self, point):
        self.frame('M0 X={} Y={} Z={} A=0.15'.format(*point))
        scene, _ = self.read()
        require(scene.get('on_ground') is True and math.dist(scene['position'], point) <= .25, 'arrival_not_observed')

    def scan(self, *, logs=False):
        """Explicit four views; no samples are interpreted as air or absence proof."""
        found = set()
        for dx, dz in DIRECTIONS:
            self.check(); scene, _ = self.read(); x, y, z = scene['eye_position']
            self.aim([x + dx * 8, y if logs else y - 2.5, z + dz * 8])
            scene, _ = self.read()
            look = describe_look_around(scene, self.check)
            require(look.status == 'succeeded' or look.reason == 'crosshair_anchor_not_observed', look.reason)
            report = {'phase': self.phase, 'scene': scene, 'look_around': look.model_dump(mode='json')}
            found.update(observed_blocks(scene, LOGS if logs else {STONE}))
            if logs:
                self.check()
                timeout = min(20., self.deadline - self.clock())
                require(timeout >= .1, 'deadline_exceeded')
                result = run_skill(self.registry.skills, self.player, 'search',
                    {'target': 'logs', 'range': 64, 'cone_degrees': 90, 'timeout_seconds': timeout},
                    cancel_event=self.cancelled)
                self.unknown |= result.status == 'failed'
                report['search'] = result.model_dump(mode='json')
                record(self.directory, f'scan-{self.scans:03d}.json', report); self.scans += 1
                require(result.status == 'succeeded' or result.reason == 'target_not_seen', 'search_stopped:' + result.reason)
                require(result.details.get('actor_session') == self.actor, 'search_actor_changed')
                found.update((r['id'], tuple(r['position'])) for r in result.details['matches'])
                self.check(); self.read()
            else:
                record(self.directory, f'scan-{self.scans:03d}.json', report); self.scans += 1
        return sorted(found)

    def wood(self):
        self.phase = 'look_and_wood'
        origin = self.read()[0]['position'][:]
        visited, moves = [origin], 0
        while True:
            self.check(); before = item_counts(self.read()[1])
            if sum(before.get(i, 0) for i in LOGS) >= LOG_GOAL:
                return
            targets = self.scan(logs=True); nav = self.mesh()
            local = [t for t in targets if math.dist([v + .5 for v in t[1]], nav['position']) <= 6
                     and _standing(nav, t) is not None]
            if local:
                selected = min(local, key=lambda t: (math.dist(nav['position'], t[1]), t))
                self.aim([v + .5 for v in selected[1]])
                self.frame('C1 N=1 E=true')
                after = item_counts(self.read()[1])
                require(sum(after.get(i, 0) - before.get(i, 0) for i in LOGS) >= 1, 'log_pickup_not_observed')
                continue
            require(moves < MAX_EXPLORE, 'wood_exploration_bound')
            candidates = [(x + .5, float(y), z + .5) for x, y, z in _reachable(nav, True)]
            candidates = [p for p in candidates if math.dist(p, nav['position']) >= 1.5
                          and math.dist(p, origin) <= 64 and min(math.dist(p, v) for v in visited) >= 1.]
            require(candidates, 'no_unvisited_supported_frontier')
            # A distant hit is a direction hint only; M0 revalidates every native edge.
            point = min(candidates, key=lambda p: (min(math.dist(p, t[1]) for t in targets), p)) if targets else max(
                candidates, key=lambda p: (min(math.dist(p, v) for v in visited), p))
            self.walk(point); visited.append(point); moves += 1

    def craft(self, item, batches=1):
        before = item_counts(self.read()[1]); recipe = RECIPES[item]
        remaining = dict(before)
        for _ in range(batches):
            plan, missing = ingredients(recipe, remaining)
            require(not missing, 'recipe_materials_missing')
            for _, _, ingredient in plan:
                remaining[ingredient] -= 1
        self.frame(f'C0 I={item} N={batches}', seconds=120.)
        after = item_counts(self.read()[1])
        require(after.get(item, 0) - before.get(item, 0) == recipe.count * batches, 'crafted_tool_or_material_not_observed')
        require(all(after.get(i, 0) == n for i, n in remaining.items() if i != item), 'craft_consumption_not_observed')

    def prepare_pick(self):
        self.phase = 'wooden_pickaxe'
        # Keep species explicit; never assume all collected logs are oak.
        counts = item_counts(self.read()[1])
        for species in SPECIES:
            count = counts.get(f'minecraft:{species}_log', 0)
            if count:
                self.craft(f'minecraft:{species}_planks', count)
        self.craft(TABLE)
        self.craft(STICK, 2)
        nav = self.mesh(); x, y, z = nav['current_cell']
        self.surface = [x + .5, float(y), z + .5]
        self.walk(self.surface)
        # East-side table, northbound stair: never excavate under the workstation.
        require((x + 1, y, z) in _reachable(self.mesh(), True), 'workbench_site_not_supported')
        self.table = [x + 1, y, z]
        self.frame(f'I1 I={TABLE}')
        self.aim([x + 1.5, y - .1, z + .5])
        self.frame('I4 B={} P={}'.format(TABLE, json.dumps(self.table, separators=(',', ':'))))
        self.open_table()
        self.craft(WOOD)
        self.frame(f'I1 I={WOOD}')  # Closes only a clean crafting UI.
        self.walk(self.surface)
        counts = item_counts(self.read()[1])
        require(counts.get(WOOD, 0) >= 1 and counts.get(STICK, 0) >= 5
                and sum(counts.get(i, 0) for i in PLANKS) >= MAX_DEPTH, 'return_or_tool_material_reserve_missing')

    def open_table(self):
        self.aim([v + .5 for v in self.table])
        self.frame('V1 T={} P={} E=true'.format(TABLE, json.dumps(self.table, separators=(',', ':'))))
        inventory = self.read()[1]
        require(inventory.get('container_open') and inventory.get('menu_type') == 'CraftingMenu', 'workbench_not_observed')

    def descend(self):
        self.check(); require(len(self.steps) < MAX_DEPTH, 'descent_bound_no_stone')
        self.frame(f'I1 I={WOOD}')
        start = self.read()[0]['position'][:]
        self.frame('M2 D=north N=1', seconds=120.)
        end = self.read()[0]['position'][:]
        expected = [math.floor(start[0]) + .5, round(start[1]) - 1., math.floor(start[2]) - .5]
        require(math.dist(end, expected) <= .3, 'descent_not_observed')
        self.steps.append({'from': start, 'to': expected})
        record(self.directory, f'descent-{len(self.steps):02d}.json', self.steps[-1])

    def stone(self):
        self.phase = 'descent_and_stone'
        self.descend()  # Surface-only stone does not satisfy this benchmark sequence.
        while len(self.harvests) < STONE_GOAL:
            self.check(); self.walk(self.steps[-1]['to'])
            targets = self.scan(); nav = self.mesh()
            protected = {(math.floor(s['from'][0]), round(s['from'][1]) - 1, math.floor(s['from'][2])) for s in self.steps}
            protected.add((self.table[0], self.table[1] - 1, self.table[2]))
            used = {tuple(r['position']) for r in self.harvests}
            choices = [t for t in targets if t[1] not in protected | used and t[1][1] < self.surface[1]
                       and math.dist([v + .5 for v in t[1]], nav['position']) <= 6 and _standing(nav, t) is not None]
            if not choices:
                self.descend()
                continue
            selected = min(choices, key=lambda t: (math.dist(t[1], nav['position']), t))
            self.frame(f'I1 I={WOOD}')
            self.aim([v + .5 for v in selected[1]])
            scene, inv = self.read(); before = item_counts(inv).get(COBBLE, 0)
            require(scene['holding'].get('item') == WOOD and scene['position'][1] < self.surface[1], 'underground_pickaxe_required')
            result = self.frame('C2 B={} N=1 E=true D=false P={}'.format(STONE, json.dumps(selected[1], separators=(',', ':'))))
            after = item_counts(self.read()[1]).get(COBBLE, 0)
            target = {'id': STONE, 'position': list(selected[1])}
            evidence = [h for h in result.get('history', []) if h.get('action') == 'gather_block' and h.get('status') == 'succeeded'
                        and target in h.get('details', {}).get('mining_targets', [])]
            require(evidence and after - before >= 1, 'stone_break_and_pickup_not_observed')
            self.harvests.append({**target, 'held_item': WOOD, 'inventory_gain': after - before})
            record(self.directory, f'stone-{len(self.harvests):02d}.json', self.harvests[-1])
        require(item_counts(self.read()[1]).get(COBBLE, 0) >= STONE_GOAL, 'nine_cobblestone_not_in_inventory')

    def ascend(self):
        self.phase = 'build_back_to_surface'
        for step in reversed(self.steps):
            self.check(); self.walk(step['to'])
            scene, inv = self.read(); before = item_counts(inv)
            block = next((i for i in PLANKS if before.get(i, 0) > 0), None)
            require(block is not None, 'return_blocks_exhausted')
            x, y, z = math.floor(scene['position'][0]), round(scene['position'][1]), math.floor(scene['position'][2])
            support = [x, y - 1, z]
            self.frame(f'I1 I={block}')
            self.aim([x + .5, y - .1, z + .5])
            self.frame('I3 B={} P={} F=up A=true J=true C=false'.format(block, json.dumps(support, separators=(',', ':'))))
            scene, inv = self.read()
            require(before.get(block, 0) - item_counts(inv).get(block, 0) == 1
                    and scene.get('on_ground') is True and math.dist(scene['position'], [x + .5, y + 1., z + .5]) <= .25,
                    'return_placement_and_landing_not_observed')
            self.placements.append({'block': block, 'position': [x, y, z]})
            self.walk(step['from'])
        self.verify_surface()
        record(self.directory, 'surface-return.json', {'scene': self.read()[0], 'placements': self.placements})

    def verify_surface(self):
        scene, _ = self.read()
        require(self.steps and len(self.placements) == len(self.steps) and scene.get('on_ground') is True
                and math.dist(scene['position'], self.surface) <= .3, 'surface_return_not_observed')

    def finish_tools(self):
        self.phase = 'stone_tools'
        self.verify_surface()
        self.open_table()
        for tool in TOOLS:
            self.craft(tool)
        self.frame(f'I1 I={TOOLS[0]}')
        self.walk(self.surface)
        self.verify_surface()
        counts = item_counts(self.read()[1])
        require(len(self.harvests) >= STONE_GOAL and all(counts.get(i, 0) >= 1 for i in TOOLS), 'final_goal_not_observed')
        return counts

    def run(self):
        require(not self.started, 'benchmark_cannot_resume')
        self.started = True
        # The constructor's one deadline is never reset between stages/frames.
        record(self.directory, 'STARTED.json', {**describe(), 'identity': self.identity, 'duration_seconds': self.duration})
        result = {'status': 'blocked', 'objective_verified': False}
        try:
            scene, inventory = self.read()
            require(not inventory.get('items') and not inventory.get('container_open') and not scene.get('screen'), 'fresh_empty_gameplay_required')
            self.mesh()
            record(self.directory, 'initial.json', {'scene': scene, 'inventory': inventory})
            self.wood(); self.prepare_pick(); self.stone(); self.ascend()
            counts = self.finish_tools()
            result.update(status='succeeded', objective_verified=True, reason='observed_benchmark_postconditions', inventory=counts)
        except BenchmarkStop as error:
            result['reason'] = str(error)
        except Exception as error:
            self.unknown = True
            result['reason'] = 'unknown_no_retry:' + type(error).__name__
        finally:
            # Runners already release their own controls, including cancel/failure.
            # Never reconnect/replay/close a partial crafting UI or launch a rescue.
            self.unknown |= self.cleanup == 'not_confirmed'
            if self.unknown:
                result.update(status='unknown_no_retry', objective_verified=False)
            result.update(phase=self.phase, frames=self.frames, cleanup=self.cleanup, unknown_no_retry=self.unknown,
                          stone_harvests=len(self.harvests), descent_steps=len(self.steps), return_placements=len(self.placements))
            record(self.directory, 'result.json', result)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--describe', action='store_true')
    parser.add_argument('--confirm-fresh-survival-world', action='store_true')
    parser.add_argument('--player-uuid'); parser.add_argument('--world-id')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--duration', type=float, default=1800.)
    args = parser.parse_args(argv)
    if args.describe:
        print(json.dumps(describe(), indent=2)); return 0
    if not all((args.confirm_fresh_survival_world, args.player_uuid, args.world_id, args.output)):
        parser.error('Explicit fresh Survival authorization, player UUID, world label and NEW output directory required')
    # Validate all caller limits/identity before directories or a connection.
    Benchmark(None, args.output, args.player_uuid, args.world_id, duration=args.duration)
    os.umask(0o077)
    directory = fresh_directory(args.output)
    with Bridge.from_env() as bridge:
        benchmark = Benchmark(Player(bridge), directory, args.player_uuid, args.world_id, duration=args.duration)
        old = {sig: signal.signal(sig, lambda *_: benchmark.cancel()) for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            result = benchmark.run()
        finally:
            for sig, handler in old.items():
                signal.signal(sig, handler)
    print(json.dumps(result, indent=2))
    return 0 if result['objective_verified'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
