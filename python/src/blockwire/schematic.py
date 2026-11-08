"""Offline Litematica -> grounded Creative build specification (NOT a runner).

Do not emit fabricated BCL for unsupported Creative/stateful placement motors.
The output separates desired voxels, placement operations, neighbor-dependent
verification and as-yet-unproven grounded access. Importing/compiling never connects.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path

from .litematic import BlockState, Schematic, SchematicError, load_litematic, require

FORMAT = 'blockwire-grounded-build-plan-v1'
COMPILER = 'litematic-grounded-v1'
FULL_CUBES = frozenset({
    'minecraft:stone', 'minecraft:cobblestone', 'minecraft:stone_bricks',
    'minecraft:dirt', 'minecraft:grass_block', 'minecraft:oak_planks',
    'minecraft:oak_log', 'minecraft:oak_wood',
})
DIRECTIONS = {'up': (0, 1, 0), 'down': (0, -1, 0),
              'north': (0, 0, -1), 'south': (0, 0, 1),
              'west': (-1, 0, 0), 'east': (1, 0, 0)}
FACING = {'north', 'south', 'west', 'east'}
BOOLEAN = {'true', 'false'}
PROFILES = {
    **{name: {} for name in FULL_CUBES},
    'minecraft:grass_block': {'snowy': {'false'}},
    'minecraft:oak_log': {'axis': {'x', 'y', 'z'}},
    'minecraft:oak_wood': {'axis': {'x', 'y', 'z'}},
    'minecraft:oak_stairs': {'facing': FACING, 'half': {'top', 'bottom'},
        'shape': {'straight', 'inner_left', 'inner_right', 'outer_left', 'outer_right'},
        'waterlogged': {'false'}},
    'minecraft:glass_pane': {**{face: BOOLEAN for face in FACING}, 'waterlogged': {'false'}},
    'minecraft:spruce_door': {'facing': FACING, 'half': {'lower', 'upper'},
        'hinge': {'left', 'right'}, 'open': BOOLEAN, 'powered': {'false'}},
}


def supported(state: BlockState) -> bool:
    profile, props = PROFILES.get(state.name), dict(state.properties)
    return (profile is not None and set(props) == set(profile)
            and all(value in profile[key] for key, value in props.items()))


def _bounds(voxels):
    lower = tuple(min(row.position[i] for row in voxels) for i in range(3))
    upper = tuple(max(row.position[i] for row in voxels) for i in range(3))
    return lower, upper


def inspect_schematic(source: Schematic) -> dict:
    lower, upper = _bounds(source.voxels)
    unsupported = Counter(row.state for row in source.voxels if not supported(row.state))
    return {
        'source_sha256': source.sha256, 'litematic_version': source.version,
        'minecraft_data_version': source.data_version, 'regions': source.regions,
        'selection_volume': source.volume, 'non_air_blocks': len(source.voxels),
        'occupied_min': list(lower), 'occupied_max': list(upper),
        'occupied_size': [b - a + 1 for a, b in zip(lower, upper)],
        'block_counts': dict(sorted(Counter(row.state.name for row in source.voxels).items())),
        'unsupported_states': [dict(state.json(), count=count)
                               for state, count in sorted(unsupported.items(), key=lambda item: (item[0].name, item[0].properties))],
        'gameplay_started': False,
    }


def _origin(value):
    require(isinstance(value, (tuple, list)) and len(value) == 3
            and all(type(n) is int for n in value), 'integer_origin_required')
    return tuple(value)


def compile_schematic(source: Schematic, *, origin=(0, 0, 0)) -> dict:
    """Compile exact desired states, not a collision/placement simulation.

    Origin names the minimum OCCUPIED corner, not padding or the selection
    origin. The complete plan is rejected on an unsupported state or door pair;
    there is no partial compilation, air clearing or silent block substitution.
    """
    origin = _origin(origin)
    summary = inspect_schematic(source)
    require(not summary['unsupported_states'], 'unsupported_block_states_inspect_first')
    source_min, _ = _bounds(source.voxels)
    voxels = {tuple(p - a + o for p, a, o in zip(row.position, source_min, origin)): row.state
              for row in source.voxels}
    require(all(abs(p[0]) <= 29_999_984 and -2048 <= p[1] <= 2048 and abs(p[2]) <= 29_999_984
                for p in voxels), 'translated_build_outside_world_bounds')
    # Native dimensions can impose tighter build-height/border limits. This
    # offline check is deliberately not permission or runtime world validation.
    order = sorted(voxels, key=lambda p: (p[1], p[2], p[0]))
    identifiers = {point: f'voxel-{index:05d}' for index, point in enumerate(order, 1)}
    for point, state in voxels.items():
        if state.name != 'minecraft:spruce_door':
            continue
        props = dict(state.properties)
        half = props['half']
        other_point = (point[0], point[1] + (1 if half == 'lower' else -1), point[2])
        props['half'] = 'upper' if half == 'lower' else 'lower'
        require(voxels.get(other_point) == BlockState(state.name, tuple(sorted(props.items()))),
                'incomplete_or_inconsistent_door_pair')

    targets, materials, layers = [], Counter(), {}
    support_needed, neighbor_checks = 0, 0
    for point in order:
        state, key = voxels[point], identifiers[point]
        props = dict(state.properties)
        upper_door = state.name == 'minecraft:spruce_door' and props['half'] == 'upper'
        group_point = (point[0], point[1] - 1, point[2]) if upper_door else point
        deferred = []
        if state.name == 'minecraft:oak_stairs':
            deferred = ['shape']
        elif state.name == 'minecraft:glass_pane':
            deferred = sorted(FACING)
        neighbor_checks += bool(deferred)
        faces = list(DIRECTIONS)
        if 'axis' in props:
            faces = {'x': ['east', 'west'], 'y': ['up', 'down'], 'z': ['north', 'south']}[props['axis']]
        elif state.name == 'minecraft:spruce_door':
            faces = ['up']
        candidates = []
        for face in faces:
            support = tuple(p - d for p, d in zip(point, DIRECTIONS[face]))
            support_state = voxels.get(support)
            # These are design relationships, NOT native sightings or reach.
            if support_state is not None and support_state.name in FULL_CUBES:
                candidates.append({'target': identifiers[support], 'face': face,
                                   'position': list(support), 'observed': False})
        needs_support = not upper_door and not candidates
        support_needed += needs_support
        item = None if upper_door else state.name
        if item is not None:
            materials[item] += 1
        target = {
            'id': key, 'position': list(point), 'state': state.json(),
            'operation': 'verify_multiblock_part' if upper_door else 'place_block',
            'placement_group': identifiers[group_point], 'item': item,
            'placement_constraints': {
                'allowed_support_faces': [] if upper_door else faces,
                'desired_facing': props.get('facing'),
                'desired_half': props.get('half'),
                'desired_hinge': props.get('hinge'),
                'desired_open': props.get('open'),
                'native_placement_result_required': True,
            },
            'blueprint_support_candidates': [] if upper_door else candidates,
            'observed_support_or_temporary_scaffold_required': needs_support,
            'grounded_access': 'NOT_PLANNED_REQUIRES_NATIVE_GEOMETRY',
            'postcondition': 'observed_exact_block_state',
            'defer_properties_until_neighbors_complete': deferred,
        }
        targets.append(target)
        layers.setdefault(point[1], []).append(key)
    return {
        'format': FORMAT, 'compiler': COMPILER,
        'status': 'COMPILED_PLAN_ONLY', 'execution_ready': False,
        'graphical_acceptance': 'NOT_RUN',
        'source': {**summary, 'metadata_labels_used_as_instructions': False},
        'coordinates': {'origin': list(origin), 'origin_means': 'minimum_occupied_corner',
                        'source_occupied_min': list(source_min), 'rotation_degrees': 0},
        'policy': {
            'mode': 'creative_grounded', 'flight': False, 'teleport': False,
            'slash_commands': False, 'direct_world_writes': False,
            'clear_schematic_air': False, 'remove_existing_world_blocks': False,
            'movement': 'native_grounded_walking_and_bounded_jumps_only',
            'materials': 'native_creative_inventory_not_give_commands',
            'temporary_scaffolds': 'require_observed_empty_cells_and_owned_placement_evidence',
            'scaffold_removal_required_for_completion': True,
            'unknown_action_result': 'STOP_NO_RETRY',
        },
        'counts': {'target_blocks': len(targets), 'placement_operations': sum(materials.values()),
                   'multiblock_verifications': sum(row['operation'] == 'verify_multiblock_part' for row in targets),
                   'neighbor_state_verifications': neighbor_checks,
                   'targets_without_blueprint_full_cube_support': support_needed},
        'materials': dict(sorted(materials.items())),
        'layers': [{'y': y, 'targets': keys} for y, keys in sorted(layers.items())],
        'ordering': 'bottom_up_work_groups_not_an_executable_schedule',
        'targets': targets,
        'execution_blockers': [
            'native_creative_material_selection_and_non_consuming_placement',
            'exact_native_block_state_placement_and_observation',
            'runtime_grounded_access_and_scaffold_planning',
            'owned_scaffold_removal_and_final_structure_verification',
        ],
        'runtime_requirements': [
            'explicit_owned_creative_world_player_actor_and_dimension_binding',
            'client_data_version_and_build_height_compatibility',
            'fresh_known_safe_grounded_pose_and_support_before_each_placement',
            'native_reach_collision_and_actual_placement_result',
            'no_flight_toggle_or_airborne_creative_travel',
            'deadline_cancel_actor_guards_and_owned_input_release',
            'fresh_postconditions_not_input_receipts_or_this_plan',
        ],
    }


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def export_plan(plan: dict, output: str | Path) -> dict:
    """Publish a compiler result into a NEW private directory, never overwrite.

    The manifest is written last. An interrupted/incomplete directory is retained
    for inspection and cannot be resumed. This API accepts compiler output, not
    an untrusted runtime executable or a claimed validation of arbitrary plans.
    """
    require(plan.get('format') == FORMAT and plan.get('execution_ready') is False,
            'compiler_plan_required')
    directory = Path(output)
    # mkdir is the exclusive reservation; it also rejects dangling symlinks.
    try:
        directory.mkdir(mode=0o700)
    except FileExistsError as error:
        raise SchematicError('output_must_not_exist') from error
    files = {
        'plan.json': _json_bytes(plan),
        'materials.json': _json_bytes({'placement_items': plan['materials'],
            'creative_stacks_are_not_consumed': True,
            'temporary_scaffold_materials': 'NOT_PLANNED',
            'note': 'Voxel counts are not required stack sizes. Door upper halves consume no separate item.'}),
        'README.txt': (
            'Blockwire grounded Creative build specification\n\n'
            'COMPILED_PLAN_ONLY — NOT EXECUTABLE; Minecraft NOT RUN.\n'
            'No flight, teleport, slash commands, direct world writes or air clearing.\n'
            'plan.json preserves exact desired block states and groups door halves.\n'
            'Layer order and blueprint supports are NOT verified poses, paths or a safe schedule.\n'
            'See execution_blockers. Existing Survival BCL placement is not a Creative/stateful executor.\n'
            'Build only after grounded access, native Creative placement, scaffold cleanup and\n'
            'fresh exact-state verification have been implemented and independently qualified.\n'
        ).encode('utf-8'),
    }
    manifest = {'format': FORMAT, 'compiler': COMPILER, 'status': 'COMPILED_PLAN_ONLY',
                'execution_ready': False, 'graphical_acceptance': 'NOT_RUN',
                'source_sha256': plan['source']['source_sha256'],
                'files': {name: {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
                          for name, data in sorted(files.items())}}
    for name, data in [*files.items(), ('manifest.json', _json_bytes(manifest))]:
        with (directory / name).open('xb') as stream:
            os.chmod(directory / name, 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline Litematica -> grounded Creative plan; no Minecraft connection or execution.')
    commands = parser.add_subparsers(dest='command', required=True)
    inspect = commands.add_parser('inspect', help='Inspect computed geometry/counts and unsupported states.')
    inspect.add_argument('schematic', type=Path)
    compile_parser = commands.add_parser('compile', help='Write a NEW private plan directory, NOT executable BCL.')
    compile_parser.add_argument('schematic', type=Path)
    compile_parser.add_argument('--origin', type=int, nargs=3, default=(0, 0, 0), metavar=('X', 'Y', 'Z'))
    compile_parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        source = load_litematic(args.schematic)
        if args.command == 'inspect':
            result = inspect_schematic(source)
        else:
            plan = compile_schematic(source, origin=args.origin)
            manifest = export_plan(plan, args.output)
            result = {'status': manifest['status'], 'execution_ready': False,
                      'output': str(args.output), 'counts': plan['counts'],
                      'materials': plan['materials'], 'graphical_acceptance': 'NOT_RUN'}
    except (SchematicError, OSError) as error:
        parser.exit(2, f'Compilation stopped; no gameplay: {type(error).__name__}: {error}\n')
    print(json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
