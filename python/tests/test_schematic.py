"""Independent small binary fixtures; no Minecraft/world acceptance claims."""
import copy
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch

from blockwire import litematic as lt
from blockwire.litematic import BlockState, SchematicError, decode_litematic, load_litematic
from blockwire.schematic import compile_schematic, export_plan, inspect_schematic, main


def string(text):
    data = text.encode('utf-8')
    return struct.pack('>H', len(data)) + data


def compound(entries):
    return b''.join(bytes([kind]) + string(name) + payload(kind, value)
                    for name, kind, value in entries) + b'\0'


def payload(kind, value):
    if kind in (1, 2, 3, 4, 5, 6):
        return struct.pack('>' + {1: 'b', 2: 'h', 3: 'i', 4: 'q', 5: 'f', 6: 'd'}[kind], value)
    if kind == 8:
        return string(value)
    if kind == 10:
        return compound(value)
    if kind == 9:
        child, rows = value
        return bytes([child]) + struct.pack('>i', len(rows)) + b''.join(payload(child, row) for row in rows)
    if kind in (7, 11, 12):
        fmt = {7: 'b', 11: 'i', 12: 'q'}[kind]
        return struct.pack('>i', len(value)) + b''.join(struct.pack('>' + fmt, row) for row in value)
    raise AssertionError(kind)


def root_bytes(entries):
    return b'\x0a' + string('') + compound(entries)


def packed(indices, palette_count):
    # Independent big-integer fixture packer, NOT production word-by-word decode.
    width = max(2, (palette_count - 1).bit_length())
    value = sum(index << (i * width) for i, index in enumerate(indices))
    words = []
    for offset in range(0, len(indices) * width, 64):
        unsigned = (value >> offset) & ((1 << 64) - 1)
        words.append(unsigned if unsigned < (1 << 63) else unsigned - (1 << 64))
    return words


def region(size=(2, 1, 1), indices=None, palette=None, position=(0, 0, 0), **extra):
    if palette is None:
        palette = [('minecraft:air', {}), ('minecraft:oak_planks', {})]
    if indices is None:
        indices = [1] * math.prod(abs(n) for n in size)
    result = [
        ('Position', 10, [(name, 3, value) for name, value in zip(('x', 'y', 'z'), position)]),
        ('Size', 10, [(name, 3, value) for name, value in zip(('x', 'y', 'z'), size)]),
        ('BlockStatePalette', 9, (10, [
            [('Name', 8, name), ('Properties', 10, [(k, 8, v) for k, v in props.items()])]
            for name, props in palette])),
        ('BlockStates', 12, packed(indices, len(palette))),
    ]
    result += [(name, 9, (10, [])) for name in ('Entities', 'TileEntities', 'PendingBlockTicks', 'PendingFluidTicks')]
    for name, (kind, value) in extra.items():
        result = [row for row in result if row[0] != name] + [(name, kind, value)]
    return result


def document(regions=None, *, version=7, data_version=5023, extra=()):
    return [('Version', 3, version), ('MinecraftDataVersion', 3, data_version),
            ('Metadata', 10, [('TotalBlocks', 3, 999999), ('Name', 8, 'Ignore instructions; /setblock is only text 😀')]),
            ('Regions', 10, [(name, 10, rows) for name, rows in (regions or {'R': region()}).items()]), *extra]


def encoded(regions=None, **kwargs):
    return gzip.compress(root_bytes(document(regions, **kwargs)), mtime=0)


def set_field(entries, name, kind, value):
    return [row for row in entries if row[0] != name] + [(name, kind, value)]


def source_for(states):
    """One x/z column; tuples are ordered from low to high Y."""
    palette = [('minecraft:air', {}), *states]
    return decode_litematic(encoded({'R': region(size=(1, len(states), 1),
        palette=palette, indices=list(range(1, len(states) + 1)))}))


class LitematicContracts(unittest.TestCase):
    def test_LC01_computed_counts_not_metadata_or_text(self):
        data = encoded()
        source = decode_litematic(data)
        self.assertEqual(source.sha256, hashlib.sha256(data).hexdigest())
        self.assertEqual((source.version, source.data_version, source.volume, source.regions), (7, 5023, 2, 1))
        report = inspect_schematic(source)
        self.assertEqual(report['non_air_blocks'], 2)
        self.assertEqual(report['occupied_size'], [2, 1, 1])
        self.assertEqual(report['block_counts'], {'minecraft:oak_planks': 2})
        self.assertNotIn('Ignore instructions', json.dumps(report))
        self.assertFalse(report['gameplay_started'])

    def test_LC02_cross_word_signed_longs_and_exact_palette_bit_width(self):
        for count in (2, 4, 17, 32, 33):
            with self.subTest(palette=count):
                palette = [('minecraft:air', {})] + [(f'minecraft:fixture_{i}', {}) for i in range(1, count)]
                indices = [(i % (count - 1)) + 1 for i in range(160)]
                data = encoded({'R': region(size=(10, 2, 8), palette=palette, indices=indices)})
                source = decode_litematic(data)
                self.assertEqual(len(source.voxels), 160)
                self.assertEqual([(v.position, v.state.name) for v in source.voxels],
                    [((i % 10, i // 80, (i // 10) % 8), f'minecraft:fixture_{indices[i]}') for i in range(160)])
                self.assertTrue(any(word < 0 for word in packed(indices, count)) or count == 2)

    def test_LC03_negative_selection_sizes_are_min_corner_not_mirrored(self):
        palette = [('minecraft:air', {}), ('minecraft:stone', {}), ('minecraft:oak_planks', {})]
        for size in ((-2, 2, 2), (2, -2, 2), (2, 2, -2), (-2, -2, -2)):
            with self.subTest(size=size):
                source = decode_litematic(encoded({'R': region(size=size, position=(10, 20, 30),
                    palette=palette, indices=[1, 2] * 4)}))
                lower = tuple(p - 1 if n < 0 else p for p, n in zip((10, 20, 30), size))
                self.assertEqual(source.selection_min, lower)
                self.assertEqual([(v.position, v.state.name) for v in source.voxels],
                    [((lower[0] + i % 2, lower[1] + i // 4, lower[2] + (i // 2) % 2),
                      'minecraft:stone' if i % 2 == 0 else 'minecraft:oak_planks') for i in range(8)])

    def test_LC04_regions_air_padding_translation_and_deterministic_order(self):
        rows = {'B': region(position=(3, 2, -4)), 'A': region(position=(-2, 0, 0), indices=[0, 1])}
        a = decode_litematic(encoded(rows))
        b = decode_litematic(encoded(dict(reversed(list(rows.items())))))
        self.assertEqual(a.voxels, b.voxels)
        plan = compile_schematic(a, origin=(10, 64, -20))
        self.assertEqual(plan['coordinates']['source_occupied_min'], [-1, 0, -4])
        self.assertEqual([v['position'] for v in plan['targets']], [[10, 64, -16], [14, 66, -20], [15, 66, -20]])
        self.assertEqual(plan['counts']['target_blocks'], 3)
        self.assertFalse(plan['policy']['clear_schematic_air'])
        self.assertFalse(plan['policy']['remove_existing_world_blocks'])

    def test_LC05_overlap_even_air_and_excessive_enclosing_span_rejected(self):
        for regions, reason in (
            ({'A': region(), 'B': region(indices=[0, 0])}, 'overlapping_regions'),
            ({'A': region(), 'B': region(position=(64, 0, 0))}, 'enclosing_size'),
        ):
            with self.subTest(reason=reason), self.assertRaisesRegex(SchematicError, reason):
                decode_litematic(encoded(regions))

    def test_LC06_entities_block_entities_ticks_and_unknown_region_fields_not_dropped(self):
        for key in ('Entities', 'TileEntities', 'PendingBlockTicks', 'PendingFluidTicks'):
            with self.subTest(key=key), self.assertRaisesRegex(SchematicError, 'unsupported_nonempty_' + key):
                decode_litematic(encoded({'R': region(**{key: (9, (10, [[('id', 8, 'minecraft:chest')]]))})}))
        with self.assertRaisesRegex(SchematicError, 'unsupported_region_field'):
            decode_litematic(encoded({'R': region(UnknownMutations=(3, 1))}))
        with self.assertRaisesRegex(SchematicError, 'invalid_region_Entities'):
            decode_litematic(encoded({'R': region(Entities=(3, 0))}))

    def test_LC07_versions_shapes_and_nonempty_input(self):
        self.assertEqual(decode_litematic(encoded(version=6)).version, 6)
        for kwargs, reason in (({'version': 8}, 'version'), ({'version': 5}, 'version'),
            ({'data_version': 0}, 'data_version'), ({'extra': [('SubVersion', 3, 1)]}, 'subversion')):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(SchematicError, reason):
                decode_litematic(encoded(**kwargs))
        for size in ((0, 1, 1), (65, 1, 1)):
            with self.assertRaisesRegex(SchematicError, 'region_size'):
                decode_litematic(encoded({'R': region(size=size)}))
        with self.assertRaisesRegex(SchematicError, 'empty_schematic'):
            decode_litematic(encoded({'R': region(indices=[0, 0])}))
        with self.assertRaisesRegex(SchematicError, 'region_count'):
            decode_litematic(encoded({str(i): region(position=(i * 2, 0, 0)) for i in range(33)}))

    def test_LC08_size_node_depth_and_block_budgets(self):
        data = encoded()
        for constant, limit, reason in (('MAX_COMPRESSED', 2, 'compressed_size'), ('MAX_NBT', 20, 'decompressed_size'),
            ('MAX_NODES', 3, 'nbt_'), ('MAX_DEPTH', 1, 'depth'), ('MAX_VOLUME', 1, 'volume'), ('MAX_BLOCKS', 1, 'block_count')):
            with self.subTest(constant=constant), patch.object(lt, constant, limit), self.assertRaisesRegex(SchematicError, reason):
                decode_litematic(data)

    def test_LC09_corrupt_gzip_trailing_members_truncation_crc_and_nbt(self):
        data = encoded()
        for corrupt in (b'', b'not gzip', data[:-1], data + data, data + b'x', data[:-5] + bytes([data[-5] ^ 1]) + data[-4:]):
            with self.subTest(corrupt_size=len(corrupt)), self.assertRaises(SchematicError):
                decode_litematic(corrupt)
        with self.assertRaisesRegex(SchematicError, 'trailing_nbt'):
            decode_litematic(gzip.compress(root_bytes(document()) + b'\0'))
        with self.assertRaisesRegex(SchematicError, 'truncated_nbt'):
            decode_litematic(gzip.compress(root_bytes(document())[:-3]))
        with self.assertRaisesRegex(SchematicError, 'compound_root'):
            decode_litematic(gzip.compress(b'\x08' + string('')))

    def test_LC10_malformed_palette_and_word_storage(self):
        cases = [
            region(BlockStates=(12, [])), region(BlockStates=(12, [5, 0])),
            region(BlockStates=(11, [5])), region(BlockStates=(12, [3])),
            region(BlockStatePalette=(9, (8, ['minecraft:air']))),
            region(palette=[('minecraft:stone', {}), ('minecraft:oak_planks', {})]),
            region(palette=[('minecraft:air', {}), ('/setblock', {})]),
            region(palette=[('minecraft:air', {}), ('minecraft:oak_log', {'axis': 'x;command'})]),
            region(palette=[('minecraft:air', {'bad': 'true'}), ('minecraft:oak_planks', {})]),
        ]
        for index, rows in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(SchematicError):
                decode_litematic(encoded({'R': rows}))

    def test_LC11_duplicate_keys_unknown_tags_bad_lists_arrays_and_numbers(self):
        for rows in (
            document(extra=[('Version', 3, 7)]),
            document(extra=[('float', 5, float('nan'))]),
            document({'R': region(Size=(10, [('x', 8, '2'), ('y', 3, 1), ('z', 3, 1)]))}),
        ):
            with self.assertRaises(SchematicError):
                decode_litematic(gzip.compress(root_bytes(rows)))
        for tag in (b'\x0d' + string('x'), b'\x09' + string('x') + b'\0' + struct.pack('>i', 1),
                    b'\x0c' + string('x') + struct.pack('>i', -1),
                    b'\x09' + string('x') + b'\x0a' + struct.pack('>i', 2**31 - 1)):
            with self.assertRaises(SchematicError):
                decode_litematic(gzip.compress(b'\x0a\0\0' + tag + b'\0'))

    def test_LC12_modified_utf8_is_data_and_invalid_surrogates_rejected(self):
        text = b'a\xc0\x80\xed\xa0\xbd\xed\xb8\x80'
        raw = root_bytes(document())
        named = b'\x0a' + struct.pack('>H', len(text)) + text + raw[3:]
        self.assertEqual(len(decode_litematic(gzip.compress(named)).voxels), 2)
        bad = b'\x0a\0\x03\xed\xa0\xbd' + raw[3:]
        with self.assertRaisesRegex(SchematicError, 'invalid_nbt_string'):
            decode_litematic(gzip.compress(bad))

    def test_LC14_signed_word_does_not_sign_extend_into_next_palette_index(self):
        palette = [('minecraft:air', {})] + [(f'minecraft:fixture_{i}', {}) for i in range(1, 32)]
        indices = [31] * 64
        indices[12] = 10  # Bit 63 set; bit 64 clear, crossing a signed long boundary.
        source = decode_litematic(encoded({'R': region(size=(16, 1, 4), palette=palette, indices=indices)}))
        self.assertEqual([v.state.name for v in source.voxels], [f'minecraft:fixture_{i}' for i in indices])

    def test_LC15_two_bit_minimum_and_power_of_two_palette_storage_are_canonical(self):
        with self.assertRaisesRegex(SchematicError, 'packed_array_length'):
            decode_litematic(encoded({'R': region(size=(64, 1, 1), BlockStates=(12, [(1 << 63) - 1]))}))
        palette = [('minecraft:air', {}), ('minecraft:stone', {}), ('minecraft:dirt', {}), ('minecraft:oak_planks', {})]
        with self.assertRaisesRegex(SchematicError, 'packed_array_length'):
            decode_litematic(encoded({'R': region(size=(64, 1, 1), palette=palette, BlockStates=(12, [1, 0, 0]))}))

    def test_LC13_explicit_regular_input_no_symlinks_directory_or_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input with spaces.litematic'
            source.write_bytes(encoded())
            self.assertEqual(len(load_litematic(source).voxels), 2)
            link = root / 'link.litematic'
            link.symlink_to(source)
            for bad in (root, root / 'missing', link):
                with self.subTest(path=bad.name), self.assertRaises(SchematicError):
                    load_litematic(bad)


DOOR = {'facing': 'north', 'half': 'lower', 'hinge': 'left', 'open': 'true', 'powered': 'false'}
STAIR = {'facing': 'west', 'half': 'bottom', 'shape': 'inner_left', 'waterlogged': 'false'}
PANE = {'north': 'true', 'south': 'true', 'east': 'false', 'west': 'false', 'waterlogged': 'false'}


class GroundedCompilerContracts(unittest.TestCase):
    def test_GC01_explicit_non_executable_no_cheats_no_flight_policy(self):
        plan = compile_schematic(decode_litematic(encoded()))
        self.assertEqual(plan['status'], 'COMPILED_PLAN_ONLY')
        self.assertIs(plan['execution_ready'], False)
        self.assertEqual(plan['graphical_acceptance'], 'NOT_RUN')
        self.assertEqual(plan['policy']['mode'], 'creative_grounded')
        for flag in ('flight', 'teleport', 'slash_commands', 'direct_world_writes', 'clear_schematic_air', 'remove_existing_world_blocks'):
            self.assertIs(plan['policy'][flag], False)
        self.assertTrue(plan['policy']['scaffold_removal_required_for_completion'])
        self.assertEqual(plan['policy']['unknown_action_result'], 'STOP_NO_RETRY')
        self.assertEqual(len(plan['execution_blockers']), 4)
        self.assertIn('not_an_executable_schedule', plan['ordering'])
        for target in plan['targets']:
            self.assertEqual(target['grounded_access'], 'NOT_PLANNED_REQUIRES_NATIVE_GEOMETRY')
            self.assertEqual(target['postcondition'], 'observed_exact_block_state')

    def test_GC02_states_preserved_and_neighbor_dependent_verification_deferred(self):
        states = [('minecraft:oak_log', {'axis': 'z'}), ('minecraft:oak_stairs', STAIR), ('minecraft:glass_pane', PANE)]
        plan = compile_schematic(source_for(states))
        self.assertEqual([r['state'] for r in plan['targets']], [{'id': name, 'properties': props} for name, props in states])
        self.assertEqual(plan['targets'][0]['placement_constraints']['allowed_support_faces'], ['north', 'south'])
        self.assertEqual(plan['targets'][1]['placement_constraints']['desired_facing'], 'west')
        self.assertEqual(plan['targets'][1]['defer_properties_until_neighbors_complete'], ['shape'])
        self.assertEqual(plan['targets'][2]['defer_properties_until_neighbors_complete'], ['east', 'north', 'south', 'west'])
        self.assertEqual(plan['counts']['neighbor_state_verifications'], 2)

    def test_GC03_two_door_blocks_are_one_item_and_one_placement(self):
        plan = compile_schematic(source_for([('minecraft:stone_bricks', {}),
            ('minecraft:spruce_door', DOOR), ('minecraft:spruce_door', {**DOOR, 'half': 'upper'})]))
        self.assertEqual(plan['materials'], {'minecraft:spruce_door': 1, 'minecraft:stone_bricks': 1})
        self.assertEqual(plan['counts']['target_blocks'], 3)
        self.assertEqual(plan['counts']['placement_operations'], 2)
        self.assertEqual(plan['counts']['multiblock_verifications'], 1)
        lower, upper = plan['targets'][1:]
        self.assertEqual(lower['operation'], 'place_block')
        self.assertEqual(upper['operation'], 'verify_multiblock_part')
        self.assertIsNone(upper['item'])
        self.assertEqual(upper['placement_group'], lower['id'])
        self.assertEqual(upper['placement_constraints']['allowed_support_faces'], [])
        self.assertEqual(lower['placement_constraints']['desired_open'], 'true')
        self.assertEqual(lower['blueprint_support_candidates'], [{'target': 'voxel-00001', 'face': 'up', 'position': [0, 0, 0], 'observed': False}])

    def test_GC04_incomplete_and_inconsistent_doors_reject_entire_compile(self):
        for states in ([('minecraft:spruce_door', DOOR)],
            [('minecraft:spruce_door', {**DOOR, 'half': 'upper'})],
            [('minecraft:spruce_door', DOOR), ('minecraft:spruce_door', {**DOOR, 'half': 'upper', 'open': 'false'})]):
            with self.subTest(states=states), self.assertRaisesRegex(SchematicError, 'door_pair'):
                compile_schematic(source_for(states))

    def test_GC05_unknown_or_unhandled_states_are_never_substituted_or_ignored(self):
        for state in (('mod:planks', {}), ('minecraft:oak_log', {}), ('minecraft:oak_log', {'axis': 'w'}),
                      ('minecraft:oak_planks', {'made_up': 'true'}), ('minecraft:grass_block', {'snowy': 'true'}),
                      ('minecraft:oak_stairs', {**STAIR, 'waterlogged': 'true'}),
                      ('minecraft:spruce_door', {**DOOR, 'powered': 'true'})):
            with self.subTest(state=state):
                source = source_for([('minecraft:stone', {}), state])
                self.assertEqual(inspect_schematic(source)['unsupported_states'], [{'id': state[0], 'properties': state[1], 'count': 1}])
                with self.assertRaisesRegex(SchematicError, 'unsupported_block_states'):
                    compile_schematic(source)

    def test_GC06_axis_restricts_supports_and_no_empty_space_is_assumed_solid(self):
        plan = compile_schematic(source_for([('minecraft:stone', {}), ('minecraft:oak_log', {'axis': 'x'})]))
        row = plan['targets'][1]
        self.assertEqual(row['placement_constraints']['allowed_support_faces'], ['east', 'west'])
        self.assertEqual(row['blueprint_support_candidates'], [])
        self.assertTrue(row['observed_support_or_temporary_scaffold_required'])
        # Ordinary full cube can use the designed support below, but not assert
        # that this support is already in the real world or reachable.
        other = compile_schematic(source_for([('minecraft:stone', {}), ('minecraft:oak_planks', {})]))
        row = other['targets'][1]
        self.assertFalse(row['observed_support_or_temporary_scaffold_required'])
        self.assertEqual(row['blueprint_support_candidates'][0]['position'], [0, 0, 0])
        self.assertIs(row['blueprint_support_candidates'][0]['observed'], False)
        self.assertTrue(row['placement_constraints']['native_placement_result_required'])

    def test_GC07_translation_strict_and_bounded_on_every_target(self):
        source = decode_litematic(encoded())
        for origin in ((True, 0, 0), (0., 0, 0), ('0', 0, 0), (0, 0), (29_999_984, 0, 0), (0, 2049, 0)):
            with self.subTest(origin=origin), self.assertRaises(SchematicError):
                compile_schematic(source, origin=origin)
        p = compile_schematic(source, origin=(-29_999_984, -2048, 29_999_984))
        self.assertEqual(p['targets'][0]['position'], [-29_999_984, -2048, 29_999_984])

    def test_GC08_layer_ids_cover_all_targets_once_and_compilation_is_repeatable(self):
        source = source_for([('minecraft:stone', {}), ('minecraft:oak_planks', {})])
        first = compile_schematic(source)
        self.assertEqual(first, compile_schematic(source))
        self.assertEqual(first['layers'], [{'y': 0, 'targets': ['voxel-00001']}, {'y': 1, 'targets': ['voxel-00002']}])
        self.assertEqual(sum(first['materials'].values()), 2)
        self.assertEqual(first['coordinates']['rotation_degrees'], 0)

    def test_GC09_new_private_directory_hashed_manifest_no_overwrite_or_resume(self):
        plan = compile_schematic(decode_litematic(encoded()))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out = root / 'first'
            manifest = export_plan(plan, out)
            self.assertEqual(json.loads((out / 'manifest.json').read_text()), manifest)
            self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o700)
            before = {file.name: file.read_bytes() for file in out.iterdir()}
            for name, record in manifest['files'].items():
                self.assertEqual(record['sha256'], hashlib.sha256(before[name]).hexdigest())
                self.assertEqual(record['bytes'], len(before[name]))
                self.assertEqual(stat.S_IMODE((out / name).stat().st_mode), 0o600)
            self.assertEqual(json.loads(before['plan.json']), plan)
            second = root / 'second'
            self.assertEqual(export_plan(plan, second), manifest)
            self.assertEqual({file.name: file.read_bytes() for file in second.iterdir()}, before)
            for target in (out, root / 'empty', root / 'link'):
                if target.name == 'empty': target.mkdir()
                if target.name == 'link': target.symlink_to(root / 'absent')
                with self.assertRaisesRegex(SchematicError, 'output_must_not_exist'):
                    export_plan(plan, target)
            self.assertEqual({file.name: file.read_bytes() for file in out.iterdir()}, before)

    def test_GC10_output_cannot_be_marked_executable_and_manifest_is_last(self):
        plan = compile_schematic(decode_litematic(encoded()))
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'out'
            bad = copy.deepcopy(plan)
            bad['execution_ready'] = True
            with self.assertRaisesRegex(SchematicError, 'compiler_plan_required'):
                export_plan(bad, out)
            self.assertFalse(out.exists())
            with patch('blockwire.schematic.os.fsync', side_effect=OSError('simulated write failure')):
                with self.assertRaises(OSError):
                    export_plan(plan, out)
            self.assertFalse((out / 'manifest.json').exists())
            with self.assertRaisesRegex(SchematicError, 'output_must_not_exist'):
                export_plan(plan, out)

    def test_GC11_cli_is_offline_and_does_not_expose_run_or_use_source_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.litematic'
            source.write_bytes(encoded())
            with patch('blockwire.client.Bridge.from_env', side_effect=AssertionError('no connection')):
                with patch('sys.stdout', new_callable=io.StringIO) as output:
                    self.assertEqual(main(['inspect', str(source)]), 0)
                    self.assertEqual(json.loads(output.getvalue())['non_air_blocks'], 2)
                with patch('sys.stdout', new_callable=io.StringIO) as output:
                    self.assertEqual(main(['compile', str(source), '--origin', '10', '64', '20', '--output', str(root / 'plan')]), 0)
                    self.assertFalse(json.loads(output.getvalue())['execution_ready'])
                for args in (['run', str(source)], ['compile', str(source), '--output', str(root / 'plan')]):
                    with patch('sys.stderr', new_callable=io.StringIO), self.assertRaises(SystemExit) as caught:
                        main(args)
                    self.assertEqual(caught.exception.code, 2)

    def test_GC13_unsupported_but_well_formed_states_fail_without_partial_plan(self):
        for state in (('mod:planks', {}), ('minecraft:oak_stairs', {**STAIR, 'waterlogged': 'true'})):
            with self.subTest(state=state), self.assertRaisesRegex(SchematicError, 'unsupported_block_states'):
                compile_schematic(source_for([('minecraft:stone', {}), state]))

    def test_GC14_both_door_halves_must_agree_on_open_and_hinge(self):
        for changed in ({'open': 'false'}, {'hinge': 'right'}):
            with self.subTest(changed=changed), self.assertRaisesRegex(SchematicError, 'door_pair'):
                compile_schematic(source_for([('minecraft:spruce_door', DOOR),
                    ('minecraft:spruce_door', {**DOOR, 'half': 'upper', **changed})]))

    def test_GC15_even_empty_output_directory_is_never_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = compile_schematic(decode_litematic(encoded()))
            with self.assertRaisesRegex(SchematicError, 'output_must_not_exist'):
                export_plan(plan, directory)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_GC12_failed_compilation_creates_no_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'unsupported.litematic'
            source.write_bytes(encoded({'R': region(palette=[('minecraft:air', {}), ('minecraft:lava', {})])}))
            with patch('sys.stderr', new_callable=io.StringIO), self.assertRaises(SystemExit) as caught:
                main(['compile', str(source), '--output', str(root / 'out')])
            self.assertEqual(caught.exception.code, 2)
            self.assertFalse((root / 'out').exists())


if __name__ == '__main__':
    unittest.main()
