#!/usr/bin/env python3
"""Isolated offline importer/compiler mutations; no game, provider or native RPC."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
IMPORTER = 'python/src/blockwire/litematic.py'
COMPILER = 'python/src/blockwire/schematic.py'
LC = 'test_schematic.LitematicContracts.'
GC = 'test_schematic.GroundedCompilerContracts.'
CASES = [
    ('cross_word', IMPORTER, 'if shift + bits > 64:', 'if False:', LC+'test_LC02_cross_word_signed_longs_and_exact_palette_bit_width'),
    ('unsigned_longs', IMPORTER, 'tuple(n & ((1 << 64) - 1) for n in words.values)', 'tuple(n for n in words.values)', LC+'test_LC14_signed_word_does_not_sign_extend_into_next_palette_index'),
    ('two_bit_minimum', IMPORTER, 'max(2, (len(palette) - 1).bit_length())', 'max(1, (len(palette) - 1).bit_length())', LC+'test_LC15_two_bit_minimum_and_power_of_two_palette_storage_are_canonical'),
    ('power_of_two_width', IMPORTER, 'max(2, (len(palette) - 1).bit_length())', 'max(2, len(palette).bit_length())', LC+'test_LC15_two_bit_minimum_and_power_of_two_palette_storage_are_canonical'),
    ('negative_region', IMPORTER, 'p + min(0, n + 1)', 'p', LC+'test_LC03_negative_selection_sizes_are_min_corner_not_mirrored'),
    ('axis_order', IMPORTER, 'zip(lower, (x, y, z))', 'zip(lower, (x, z, y))', LC+'test_LC02_cross_word_signed_longs_and_exact_palette_bit_width'),
    ('overlap', IMPORTER, 'not all(lower[i] <= old_upper[i] and old_lower[i] <= upper[i] for i in range(3))', 'True', LC+'test_LC05_overlap_even_air_and_excessive_enclosing_span_rejected'),
    ('entities', IMPORTER, "require(not value.values, 'unsupported_nonempty_' + key)", "require(True, 'unsupported_nonempty_' + key)", LC+'test_LC06_entities_block_entities_ticks_and_unknown_region_fields_not_dropped'),
    ('trailing_gzip', IMPORTER, 'decoder.eof and not decoder.unused_data', 'decoder.eof', LC+'test_LC09_corrupt_gzip_trailing_members_truncation_crc_and_nbt'),
    ('palette_zero', IMPORTER, "palette[0] == BlockState('minecraft:air')", 'True', LC+'test_LC10_malformed_palette_and_word_storage'),
    ('packed_exact_length', IMPORTER, 'len(words.values) == (cells * bits + 63) // 64', 'len(words.values) >= (cells * bits + 63) // 64', LC+'test_LC10_malformed_palette_and_word_storage'),
    ('array_type', IMPORTER, 'isinstance(words, _Array) and words.kind == 12', 'isinstance(words, _Array)', LC+'test_LC10_malformed_palette_and_word_storage'),
    ('clamp_invalid_index', IMPORTER, 'selected = value & ((1 << bits) - 1)', 'selected = (value & ((1 << bits) - 1)) % len(palette)', LC+'test_LC10_malformed_palette_and_word_storage'),
    ('size_bound', IMPORTER, 'MAX_SIDE = 64', 'MAX_SIDE = 65', LC+'test_LC07_versions_shapes_and_nonempty_input'),
    ('nonfinite', IMPORTER, 'not isinstance(value, float) or math.isfinite(value)', 'True', LC+'test_LC11_duplicate_keys_unknown_tags_bad_lists_arrays_and_numbers'),
    ('unsupported_states', COMPILER, "not summary['unsupported_states']", 'True', GC+'test_GC13_unsupported_but_well_formed_states_fail_without_partial_plan'),
    ('preserve_properties', COMPILER, "'state': state.json(),", "'state': {'id': state.name, 'properties': {}},", GC+'test_GC02_states_preserved_and_neighbor_dependent_verification_deferred'),
    ('door_pair', COMPILER, 'voxels.get(other_point) == BlockState(state.name, tuple(sorted(props.items())))', 'True', GC+'test_GC14_both_door_halves_must_agree_on_open_and_hinge'),
    ('door_item_count', COMPILER, 'item = None if upper_door else state.name', 'item = state.name', GC+'test_GC03_two_door_blocks_are_one_item_and_one_placement'),
    ('log_axis_support', COMPILER, "'x': ['east', 'west']", "'x': ['up', 'down']", GC+'test_GC06_axis_restricts_supports_and_no_empty_space_is_assumed_solid'),
    ('neighbor_verification', COMPILER, "deferred = ['shape']", 'deferred = []', GC+'test_GC02_states_preserved_and_neighbor_dependent_verification_deferred'),
    ('invented_observation', COMPILER, "'observed': False", "'observed': True", GC+'test_GC06_axis_restricts_supports_and_no_empty_space_is_assumed_solid'),
    ('origin', COMPILER, 'p - a + o for p, a, o', 'p + o for p, a, o', LC+'test_LC04_regions_air_padding_translation_and_deterministic_order'),
    ('no_flight', COMPILER, "'flight': False", "'flight': True", GC+'test_GC01_explicit_non_executable_no_cheats_no_flight_policy'),
    ('no_commands', COMPILER, "'slash_commands': False", "'slash_commands': True", GC+'test_GC01_explicit_non_executable_no_cheats_no_flight_policy'),
    ('fresh_directory', COMPILER, 'directory.mkdir(mode=0o700)', 'directory.mkdir(mode=0o700, exist_ok=True)', GC+'test_GC15_even_empty_output_directory_is_never_reused'),
    ('native_result', COMPILER, "'native_placement_result_required': True", "'native_placement_result_required': False", GC+'test_GC06_axis_restricts_supports_and_no_empty_space_is_assumed_solid'),
]


def execute(root, tests, logfile):
    env = {**os.environ, 'PYTHONPATH': str(root/'python/src') + os.pathsep + str(root/'python/tests'),
           'PYTHONDONTWRITEBYTECODE': '1'}
    result = subprocess.run([sys.executable, '-B', '-m', 'unittest', *tests],
        cwd=root, env=env, capture_output=True, text=True, timeout=60)
    logfile.write_text(result.stdout + result.stderr)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=False)
    baseline = execute(ROOT, ['test_schematic'], args.output/'baseline.log')
    if baseline.returncode:
        raise RuntimeError('Baseline failed; no valid mutation verdict')
    results = []
    for name, filename, old, new, test in CASES:
        with tempfile.TemporaryDirectory(prefix='blockwire-schematic-mutation-') as directory:
            root = Path(directory)
            shutil.copytree(ROOT/'python/src', root/'python/src', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            (root/'python/tests').mkdir()
            shutil.copyfile(ROOT/'python/tests/test_schematic.py', root/'python/tests/test_schematic.py')
            path = root/filename
            original = path.read_text()
            if original.count(old) != 1:
                raise RuntimeError('Invalid unique mutation anchor: ' + name)
            changed = original.replace(old, new)
            compile(changed, str(path), 'exec')
            path.write_text(changed)
            result = execute(root, [test], args.output/(name + '.log'))
            killed = (result.returncode == 1 and 'FAIL: ' + test.split('.')[-1] in result.stderr
                      and 'FAILED (failures=' in result.stderr and 'ERROR:' not in result.stderr)
            status = 'KILLED' if killed else 'INVALID_OR_SURVIVED'
            results.append({'name': name, 'test': test, 'status': status})
            print(name, status, flush=True)
    (args.output/'results.json').write_text(json.dumps(results, indent=2) + '\n')
    return int(any(row['status'] != 'KILLED' for row in results))


if __name__ == '__main__':
    raise SystemExit(main())
