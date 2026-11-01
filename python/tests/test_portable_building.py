"""Offline contracts for the frozen relative Test-A building fixture; NOT Minecraft acceptance."""
import hashlib
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests'))

from blockwire.bcl import compile_bcl, default_commands
from blockwire.bcl.compiler import arguments
from building.portable import (
    HOUSE_ORIGIN_LOCAL, ORIGINS, POINT_HOME, PORTABLE_SOURCE_SHA256, VOXEL_HOME,
    expected_house, frame_sources, house_from_home, local_placement_targets,
    resolved_coordinate_rows, source, start_position,
)
from building.fixture import INVENTORY
from building.portable_live import REPL_PIPELINE, _preparation_commands
from building.program import frames
from building.reference import House
import tools.portable_bcl_benchmark as portable_tool


class PortableBuildingContracts(unittest.TestCase):
    def setUp(self):
        self.registry = default_commands()
        self.source = source()

    def test_PB01_frozen_source_starts_with_one_explicit_home_and_all_frames_compile(self):
        self.assertEqual(hashlib.sha256(self.source.encode()).hexdigest(), PORTABLE_SOURCE_SHA256)
        self.assertEqual(self.source.splitlines()[:2], ['S0 sync', 'S1 relative'])
        self.assertEqual(self.source.splitlines().count('S1 relative'), 1)
        self.assertNotIn('S1 absolute', self.source)
        compiled = frames(self.source, self.registry)
        self.assertEqual(len(compiled), 29)
        self.assertEqual(sum(len(program.operations) for _, program in compiled), 231)
        self.assertTrue(all(len(program.operations) <= 32 for _, program in compiled))

    def test_PB02_relative_fixture_preserves_absolute_test_a_order_and_arguments(self):
        absolute = (Path(__file__).resolve().parents[2] / 'tests/building/fixtures/build.bcl').read_text()
        absolute_ops = [operation for _, program in frames(absolute, self.registry) for operation in program.operations]
        relative_ops = [operation for _, program in frames(self.source, self.registry) for operation in program.operations]
        self.assertEqual(len(absolute_ops), len(relative_ops))
        axes = {'point_x': 0, 'point_y': 1, 'point_z': 2}
        for absolute_op, relative_op in zip(absolute_ops, relative_ops):
            self.assertEqual((absolute_op.namespace, absolute_op.opcode), (relative_op.namespace, relative_op.opcode))
            command = self.registry.resolve(relative_op.namespace, relative_op.opcode)
            absolute_values = arguments(absolute_op, command)
            relative_values = arguments(relative_op, command)
            if relative_op.opcode == 'S1':
                self.assertEqual((absolute_values['value'], relative_values['value']), ('absolute', 'relative'))
                continue
            for name, kind in command.coordinate_parameters:
                if name not in relative_values:
                    continue
                value = relative_values[name]
                resolved = ([value[index] + VOXEL_HOME[index] for index in range(3)] if kind == 'voxel'
                            else value + POINT_HOME[axes[kind]])
                relative_values[name] = resolved
            self.assertEqual(relative_values, absolute_values)

    def test_PB03_fractional_home_maps_voxels_and_all_reference_blocks_exactly(self):
        targets = local_placement_targets()
        resolved = {tuple(position[index] + VOXEL_HOME[index] for index in range(3)): block
                    for position, block in targets.items()}
        self.assertEqual({position: block for position, block in resolved.items()
                          if block == 'minecraft:cobblestone'}, House().blocks())
        self.assertEqual(sum(block == 'minecraft:dirt' for block in resolved.values()), 11)
        self.assertEqual(tuple(VOXEL_HOME[index] + HOUSE_ORIGIN_LOCAL[index] for index in range(3)), House().origin)
        self.assertEqual(targets[HOUSE_ORIGIN_LOCAL], 'minecraft:cobblestone')

    def test_PB04_three_origins_share_identical_local_mapping_and_translation(self):
        houses = {}
        rows = {}
        for label in ORIGINS:
            home = start_position(label)
            house = expected_house(label)
            self.assertEqual(house_from_home(home), house)
            houses[label] = house
            rows[label] = resolved_coordinate_rows(home)
            self.assertEqual(len(rows[label]), len(rows['A']) if 'A' in rows else len(rows[label]))
        local_blocks = sorted(House().blocks())
        for left, right in [('A', 'B'), ('A', 'C'), ('B', 'C')]:
            home_delta = tuple(math.floor(start_position(right)[axis]) - math.floor(start_position(left)[axis]) for axis in range(3))
            left_blocks = sorted(houses[left].blocks()); right_blocks = sorted(houses[right].blocks())
            self.assertEqual(len(left_blocks), 71)
            self.assertEqual([tuple(right_blocks[i][axis] - left_blocks[i][axis] for axis in range(3))
                              for i in range(71)], [home_delta] * 71)
        self.assertEqual(len(local_blocks), 71)

    def test_PB05_split_request_variant_moves_only_the_home_boundary(self):
        normal = frame_sources(); body = frame_sources(split_home=True)
        self.assertEqual(len(normal), len(body))
        self.assertNotIn('S1', '\n'.join(body))
        home = compile_bcl('S0 sync\nS1 relative', self.registry)
        body_count = sum(len(compile_bcl(part, self.registry).operations) for part in body)
        normal_count = sum(len(compile_bcl(part, self.registry).operations) for part in normal)
        self.assertEqual(len(home.operations) + body_count, normal_count)
        self.assertEqual(normal_count, 231)

    def test_PB06_administrative_preparation_is_translated_and_pre_execution_only(self):
        commands = _preparation_commands('B')
        self.assertIn('/tp @s 50.5 -60.0 -3.5 0 0', commands)
        self.assertIn('/fill 32 -60 -16 64 -48 16 minecraft:air', commands)
        self.assertIn('/fill 32 -61 -16 64 -61 16 minecraft:grass_block', commands)
        self.assertFalse(any(command.startswith('/setblock') for command in commands))
        self.assertEqual(sum(command.startswith('/give @s ') for command in commands), len(INVENTORY))


    def test_PB07_redirected_repl_uses_eof_to_wait_not_explicit_quit_cancellation(self):
        self.assertTrue(REPL_PIPELINE.endswith('\n'))
        self.assertNotIn(':quit', REPL_PIPELINE)
        for line in REPL_PIPELINE.splitlines():
            self.assertGreaterEqual(len(compile_bcl(line, self.registry).operations), 1)


class PortableToolContracts(unittest.IsolatedAsyncioTestCase):
    async def test_PB08_native_entry_wraps_the_authenticated_bridge_in_player(self):
        backend = object(); player = object()
        class Context:
            def __enter__(self): return backend
            def __exit__(self, *_): return None
        native = AsyncMock(return_value={'passed': True})
        with patch.object(portable_tool.Bridge, 'from_env', return_value=Context()), \
                patch.object(portable_tool, 'Player', return_value=player) as constructor, \
                patch.object(portable_tool, 'run_mapping', native):
            self.assertEqual(await portable_tool._native(SimpleNamespace(action='mapping')), 0)
        constructor.assert_called_once_with(backend)
        native.assert_awaited_once()
        self.assertIs(native.await_args.args[0], player)


if __name__ == '__main__':
    unittest.main()
