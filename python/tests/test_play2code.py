"""Passive recording/export contracts. Synthetic timelines are parser fixtures, not Minecraft evidence."""
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import unittest

from blockwire.bcl import compile_bcl, default_commands
from blockwire.play2code import (
    CAPTURE_SCHEMA, EVENT_SCHEMA, CoordinateTransform, Play2CodeError, export_recording,
    inspect_recording, load_recording,
)


ID = '20260101T000000.000Z-1234abcd'
ACTOR = 'actor-session-a'


def event(sequence, event_type, **values):
    return {'schema': EVENT_SCHEMA, 'recording_id': ID, 'sequence': sequence, 'type': event_type,
            'wall_time_ms': 1000 + sequence, 'monotonic_ns': 10_000 + sequence, **values}


def tick(sequence, x, *, y=64., z=.5, inputs=None, on_ground=True, remote=None,
         sprinting=False, sneaking=False):
    buttons = {name: False for name in ('forward', 'back', 'left', 'right', 'jump', 'sneak', 'sprint', 'attack', 'use')}
    buttons.update(inputs or {})
    return event(sequence, 'tick', client_tick=sequence-1, actor_session=ACTOR,
                 position_absolute=[x, y, z], position_relative=[x-.5, y-64., z-.5],
                 block_position_absolute=[int(x), int(y), int(z)], block_position_relative=[int(x), 0, int(z)],
                 velocity=[0., 0., 0.], yaw=0., pitch=0., on_ground=on_ground,
                 sprinting=sprinting, sneaking=sneaking, health=20., selected_hotbar=0,
                 main_hand={'empty': True}, off_hand={'empty': True}, inputs=buttons,
                 remote_owned_inputs=[] if remote is None else remote, screen_open=False)


def write_capture(root: Path, rows, *, safe=True):
    directory = root / ID
    directory.mkdir(mode=0o700)
    timeline = directory / 'raw-timeline.jsonl'
    timeline.write_text(''.join(json.dumps(row, separators=(',', ':')) + '\n' for row in rows))
    capture = {
        'schema': CAPTURE_SCHEMA, 'recording_id': ID, 'status': 'completed', 'reason': 'user_requested',
        'timeline': timeline.name, 'timeline_sealed': True, 'event_count': len(rows),
        'timeline_bytes': timeline.stat().st_size, 'started_at_ms': 1000, 'ended_at_ms': 2000,
        'duration_ns': 1_000_000, 'profile': 'native_local_human_timeline_v1',
        'player_uuid': '00000000-0000-0000-0000-000000000001', 'dimension': 'minecraft:overworld',
        'actor_session': ACTOR, 'origin_position_absolute': [.5, 64., .5], 'origin_block_absolute': [0, 64, 0],
        'export_required': True, 'no_remote_controller_interference': safe,
        'remote_control': {'endpoint_disabled_at_start': True,
                           'endpoint_enabled_during_recording': not safe,
                           'remote_owned_input_observed': False},
        'summary': {},
    }
    (directory / 'capture.json').write_text(json.dumps(capture) + '\n')
    return directory


def bracket(middle):
    start = event(0, 'recording_start', profile='native_local_human_timeline_v1', source='local_human_input',
                  control_endpoint_running=False, actor_session=ACTOR,
                  player_uuid='00000000-0000-0000-0000-000000000001', dimension='minecraft:overworld',
                  game_mode='survival', origin_position_absolute=[.5, 64., .5], origin_block_absolute=[0, 64, 0],
                  position_absolute=[.5, 64., .5], position_relative=[0., 0., 0.], yaw=0., pitch=0.,
                  selected_hotbar=0, main_hand={'empty': True}, coordinate_contract='fixture')
    rows = [start, *middle]
    rows.append(event(len(rows), 'recording_stop_requested', client_tick=len(rows), pending_mutations=0))
    rows.append(event(len(rows), 'recording_stop', client_tick=len(rows), actor_session=ACTOR,
                      requested=True, status='completed', reason='user_requested',
                      position_absolute=[.5, 64., .5], position_relative=[0., 0., 0.], health=20., alive=True))
    return rows


class Play2CodeContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_P2C01_export_preserves_raw_events_and_compiles_conservative_BCL(self):
        middle = [tick(1, .5), tick(2, .65, inputs={'forward': True})]
        middle += [
            event(3, 'use_on_block', client_tick=2, action='use', source='local_human_input', hand='main_hand',
                  target_position_absolute=[0, 63, 0], target_position_relative=[0, -1, 0], face='up',
                  held={'empty': False, 'item': 'minecraft:cobblestone', 'count': 64}, selected_hotbar=0,
                  player_position_absolute=[.65, 64., .5], player_position_relative=[.15, 0., 0.], yaw=0., pitch=90.,
                  target_block='minecraft:grass_block', expected_placed_block='minecraft:cobblestone',
                  candidates=[{'position_absolute': [0, 64, 0], 'position_relative': [0, 0, 0],
                               'before_block': 'minecraft:air'}]),
            event(4, 'block_placed', client_tick=4, intent_sequence=3, source='local_human_input', hand='main_hand',
                  position_absolute=[0, 64, 0], position_relative=[0, 0, 0], before_block='minecraft:air',
                  after_block='minecraft:cobblestone', expected_block='minecraft:cobblestone',
                  held_item='minecraft:cobblestone', held_count_before=64, held_count_after=63,
                  inventory_consumption_observed=True, confirmation='client_world_state_stable_3_end_ticks',
                  confirmed_stable_ticks=3),
            event(5, 'break_intent', client_tick=5, action='break', source='local_human_input', hand='main_hand',
                  target_position_absolute=[1, 64, 0], target_position_relative=[1, 0, 0], face='up',
                  held={'empty': False, 'item': 'minecraft:diamond_pickaxe', 'count': 1}, selected_hotbar=1,
                  player_position_absolute=[.65, 64., .5], player_position_relative=[.15, 0., 0.], yaw=0., pitch=45.,
                  before_block='minecraft:cobblestone'),
            event(6, 'block_broken', client_tick=8, intent_sequence=5, source='local_human_input', hand='main_hand',
                  position_absolute=[1, 64, 0], position_relative=[1, 0, 0], before_block='minecraft:cobblestone',
                  after_block='minecraft:air', held_item='minecraft:diamond_pickaxe', held_count_before=1,
                  held_count_after=1, inventory_consumption_observed=False,
                  confirmation='client_world_state_stable_3_end_ticks', confirmed_stable_ticks=3),
        ]
        rows = bracket(middle)
        directory = write_capture(self.root, rows)
        before = hashlib.sha256((directory / 'raw-timeline.jsonl').read_bytes()).hexdigest()
        result = export_recording(directory)
        self.assertEqual(hashlib.sha256((directory / 'raw-timeline.jsonl').read_bytes()).hexdigest(), before)
        self.assertFalse(result['replay']['attempted']);self.assertFalse(result['replay']['qualified'])
        self.assertTrue(result['remote_control']['no_remote_controller_interference'])
        self.assertEqual(result['world_mutations']['confirmed_placements'], 1)
        self.assertEqual(result['world_mutations']['confirmed_breaks'], 1)
        conversion = json.loads((directory / 'conversion.json').read_text())
        lines = [row['bcl'] for row in conversion['generated_operations']]
        self.assertTrue(any(line.startswith('M0 ') for line in lines), lines)
        self.assertIn('V2 X0.65 Y64 Z0.5', lines)
        self.assertIn('I3 B=minecraft:cobblestone P=[0,63,0] F=up A=true Q=[0.65,64,0.5] R=[0.65,64,0.5] C=false', lines)
        self.assertIn('C3 B=minecraft:cobblestone P=[1,64,0] D=false', lines)
        self.assertIn('I1 I=minecraft:cobblestone', lines)
        self.assertIn('I1 I=minecraft:diamond_pickaxe', lines)
        registry = default_commands()
        for path in sorted((directory / 'bcl').glob('*.bcl')):
            source = path.read_text();self.assertIn('S1 absolute', source)
            self.assertLessEqual(len(compile_bcl(source, registry).operations), 32)
        manifest = json.loads((directory / 'manifest.json').read_text())
        for name, digest in manifest['artifact_sha256'].items():
            self.assertEqual(hashlib.sha256((directory / name).read_bytes()).hexdigest(), digest)
        self.assertEqual(manifest['coordinate_contract']['origin_position_absolute'], [.5, 64., .5])
        self.assertEqual(inspect_recording(directory)['recording_id'], ID)

    def test_P2C02_every_eligible_tick_is_retained_and_batches_stay_bounded(self):
        rows = [tick(1, .5)]
        for index in range(2, 42):
            rows.append(tick(index, .5 + (index-1)*.1, inputs={'forward': True}))
        directory = write_capture(self.root, bracket(rows))
        result = export_recording(directory)
        conversion = json.loads((directory / 'conversion.json').read_text())
        movement = [row for row in conversion['generated_operations'] if row['kind'] == 'movement_checkpoint']
        self.assertEqual(len(movement), 40)  # no path smoothing or waypoint optimization
        self.assertEqual(result['conversion']['bcl_batches'], 2)
        for check in result['compiler_validation']:
            self.assertLessEqual(check['compiled_operations'], 32)
            self.assertEqual(check['registry_digest'], result['compiler_validation'][0]['registry_digest'])

    def test_P2C10_relative_export_uses_one_persistent_home_across_batches(self):
        rows = [tick(1, .5)]
        for index in range(2, 42):
            rows.append(tick(index, .5 + (index-1)*.1, inputs={'forward': True}))
        rows += [
            event(42, 'use_on_block', client_tick=41, action='use', source='local_human_input', hand='main_hand',
                  target_position_absolute=[1, 63, 2], target_position_relative=[1, -1, 2], face='up',
                  held={'empty': False, 'item': 'minecraft:cobblestone', 'count': 64}, selected_hotbar=0,
                  player_position_absolute=[1.5, 64., 2.5], player_position_relative=[1., 0., 2.], yaw=0., pitch=90.,
                  target_block='minecraft:grass_block', expected_placed_block='minecraft:cobblestone',
                  candidates=[{'position_absolute': [1, 64, 2], 'position_relative': [1, 0, 2],
                               'before_block': 'minecraft:air'}]),
            event(43, 'block_placed', client_tick=44, intent_sequence=42, source='local_human_input', hand='main_hand',
                  position_absolute=[1, 64, 2], position_relative=[1, 0, 2], before_block='minecraft:air',
                  after_block='minecraft:cobblestone', expected_block='minecraft:cobblestone',
                  held_item='minecraft:cobblestone', held_count_before=64, held_count_after=63,
                  inventory_consumption_observed=True, confirmation='client_world_state_stable_3_end_ticks',
                  confirmed_stable_ticks=3),
        ]
        directory = write_capture(self.root, bracket(rows))
        result = export_recording(directory, coordinate_mode='relative', benchmark='superflat_house_5x5')
        sources = [path.read_text() for path in sorted((directory / 'bcl').glob('*.bcl'))]
        self.assertEqual(len(sources), 2)
        self.assertEqual(sum(source.count('S1 relative') for source in sources), 1)
        self.assertIn('S1 relative', sources[0]);self.assertNotIn('S1 ', sources[1])
        self.assertFalse(any('S1 absolute' in source for source in sources))
        conversion = json.loads((directory / 'conversion.json').read_text())
        lines = [row['bcl'] for row in conversion['generated_operations']]
        self.assertIn('M0 X0.1 Y0 Z0 Fnormal', lines)
        self.assertIn('V2 X1 Y0 Z2', lines)
        self.assertIn('I3 B=minecraft:cobblestone P=[1,-1,2] F=up A=true Q=[1,0,2] R=[1,0,2] C=false', lines)
        placement = [row for row in conversion['generated_operations']
                     if row['kind'] in {'aim_for_confirmed_placement', 'confirmed_placement'}]
        self.assertEqual([row['kind'] for row in placement],
                         ['aim_for_confirmed_placement', 'confirmed_placement'])
        self.assertEqual(placement[0]['batch'], placement[1]['batch'])
        self.assertEqual(placement[0]['line'] + 1, placement[1]['line'])
        manifest = json.loads((directory / 'manifest.json').read_text())
        self.assertEqual(manifest['coordinate_contract']['bcl_coordinate_mode'], 'relative')
        self.assertTrue(manifest['compiler_validation'][0]['captures_home'])
        self.assertTrue(manifest['compiler_validation'][1]['requires_prior_home'])
        self.assertEqual(manifest['benchmark']['independent_world_acceptance'], 'PENDING')
        for source in sources:
            self.assertLessEqual(len(compile_bcl(source, default_commands()).operations), 32)

    def test_P2C11_relative_export_rejects_inconsistent_coordinate_evidence(self):
        rows = bracket([tick(1, .65, inputs={'forward': True})])
        rows[1]['position_relative'][0] = 99.
        directory = write_capture(self.root, rows)
        with self.assertRaisesRegex(Play2CodeError, 'relative point coordinate'):
            export_recording(directory, coordinate_mode='relative')
        self.assertFalse((directory / 'manifest.json').exists())

    def test_P2C06_first_grounded_checkpoint_is_measured_from_capture_origin(self):
        directory = write_capture(self.root, bracket([tick(1, .65, inputs={'forward': True})]))
        export_recording(directory)
        conversion = json.loads((directory / 'conversion.json').read_text())
        movement = [row for row in conversion['generated_operations'] if row['kind'] == 'movement_checkpoint']
        self.assertEqual([row['bcl'] for row in movement], ['M0 X0.65 Y64 Z0.5 Fnormal'])

    def test_P2C03_unsupported_effects_are_explicit_and_never_guessed(self):
        rows = [tick(1, .5), tick(2, .7, y=64.2, inputs={'jump': True, 'forward': True}, on_ground=False),
                tick(3, .9, inputs={'forward': True})]
        rows += [
            event(4, 'use_on_block', client_tick=3, action='use', source='local_human_input', hand='off_hand',
                  target_position_absolute=[0, 63, 0], target_position_relative=[0, -1, 0], face='up',
                  held={'empty': False, 'item': 'minecraft:cobblestone', 'count': 1}, selected_hotbar=0,
                  player_position_absolute=[.9, 64., .5], player_position_relative=[.4, 0., 0.], yaw=0., pitch=45.,
                  target_block='minecraft:grass_block', expected_placed_block='minecraft:cobblestone', candidates=[]),
            event(5, 'block_placed', client_tick=6, intent_sequence=4, source='local_human_input', hand='off_hand',
                  position_absolute=[0, 64, 0], position_relative=[0, 0, 0], before_block='minecraft:air',
                  after_block='minecraft:cobblestone', expected_block='minecraft:cobblestone',
                  held_item='minecraft:cobblestone', held_count_before=1, held_count_after=0,
                  inventory_consumption_observed=True, confirmation='client_world_state_stable_3_end_ticks',
                  confirmed_stable_ticks=3),
            event(6, 'break_intent', client_tick=7, action='break', source='local_human_input', hand='main_hand',
                  target_position_absolute=[2, 64, 0], target_position_relative=[2, 0, 0], face='up',
                  held={'empty': True}, selected_hotbar=0, player_position_absolute=[.9, 64., .5],
                  player_position_relative=[.4, 0., 0.], yaw=0., pitch=45., before_block='minecraft:obsidian'),
            event(7, 'interaction_unconfirmed', intent_sequence=6, kind='break',
                  position_absolute=[2, 64, 0], position_relative=[2, 0, 0], reason='confirmation_timeout'),
            event(8, 'use_on_block', client_tick=8, action='use', source='local_human_input', hand='main_hand',
                  target_position_absolute=[0, 63, 1], target_position_relative=[0, -1, 1], face='up',
                  held={'empty': False, 'item': 'minecraft:cobblestone', 'count': 1}, selected_hotbar=0,
                  player_position_absolute=[.9, 64., .5], player_position_relative=[.4, 0., 0.], yaw=0., pitch=45.,
                  target_block='minecraft:grass_block', expected_placed_block='minecraft:cobblestone', candidates=[]),
            event(9, 'block_placed', client_tick=9, intent_sequence=8, source='local_human_input', hand='main_hand',
                  position_absolute=[0, 64, 1], position_relative=[0, 0, 1], before_block='minecraft:air',
                  after_block='minecraft:cobblestone', expected_block='minecraft:cobblestone',
                  held_item='minecraft:cobblestone', held_count_before=1, held_count_after=0,
                  inventory_consumption_observed=True, confirmation='client_world_state_stable_1_end_ticks',
                  confirmed_stable_ticks=1),
            event(10, 'break_intent', client_tick=10, action='break', source='local_human_input', hand='main_hand',
                  target_position_absolute=[3, 64, 0], target_position_relative=[3, 0, 0], face='up',
                  held={'empty': False, 'item': 'minecraft:diamond_pickaxe', 'count': 1}, selected_hotbar=1,
                  player_position_absolute=[.9, 64., .5], player_position_relative=[.4, 0., 0.], yaw=0., pitch=45.,
                  before_block='minecraft:obsidian'),
            event(11, 'block_broken', client_tick=13, intent_sequence=10, source='local_human_input', hand='main_hand',
                  position_absolute=[3, 64, 0], position_relative=[3, 0, 0], before_block='minecraft:obsidian',
                  after_block='minecraft:air', held_item='minecraft:diamond_pickaxe', held_count_before=1,
                  held_count_after=1, inventory_consumption_observed=False,
                  confirmation='client_world_state_stable_3_end_ticks', confirmed_stable_ticks=3),
        ]
        directory = write_capture(self.root, bracket(rows))
        export_recording(directory)
        conversion = json.loads((directory / 'conversion.json').read_text())
        reasons = {row['reason'] for row in conversion['unsupported_conversions']}
        self.assertIn('airborne_movement_has_no_safe_M0_checkpoint', reasons)
        self.assertIn('only_confirmed_main_hand_block_use_maps_to_placement', reasons)
        self.assertIn('no_confirmed_world_mutation', reasons)
        self.assertIn('mutation_not_stably_confirmed', reasons)
        self.assertIn('conversion_rejected_by_installed_registry', reasons)
        self.assertFalse(any(row['bcl'].startswith('I3 ') for row in conversion['generated_operations']))

    def test_P2C07_confirmed_mutations_must_match_their_native_intents(self):
        rows = [
            event(1, 'use_on_block', client_tick=1, action='use', source='local_human_input', hand='main_hand',
                  target_position_absolute=[0, 63, 0], target_position_relative=[0, -1, 0], face='up',
                  held={'empty': False, 'item': 'minecraft:cobblestone', 'count': 1}, selected_hotbar=0,
                  player_position_absolute=[.5, 64., .5], player_position_relative=[0., 0., 0.], yaw=0., pitch=45.,
                  target_block='minecraft:grass_block', expected_placed_block='minecraft:cobblestone',
                  candidates=[{'position_absolute': [0, 64, 0], 'position_relative': [0, 0, 0],
                               'before_block': 'minecraft:air'}]),
            event(2, 'block_placed', client_tick=4, intent_sequence=1, source='local_human_input', hand='main_hand',
                  position_absolute=[1, 64, 0], position_relative=[1, 0, 0], before_block='minecraft:air',
                  after_block='minecraft:cobblestone', expected_block='minecraft:cobblestone',
                  held_item='minecraft:cobblestone', held_count_before=1, held_count_after=0,
                  inventory_consumption_observed=True, confirmation='client_world_state_stable_3_end_ticks',
                  confirmed_stable_ticks=3),
            event(3, 'break_intent', client_tick=5, action='break', source='local_human_input', hand='main_hand',
                  target_position_absolute=[2, 64, 0], target_position_relative=[2, 0, 0], face='up',
                  held={'empty': False, 'item': 'minecraft:diamond_pickaxe', 'count': 1}, selected_hotbar=1,
                  player_position_absolute=[.5, 64., .5], player_position_relative=[0., 0., 0.], yaw=0., pitch=45.,
                  before_block='minecraft:cobblestone'),
            event(4, 'block_broken', client_tick=8, intent_sequence=3, source='local_human_input', hand='main_hand',
                  position_absolute=[2, 64, 0], position_relative=[2, 0, 0], before_block='minecraft:cobblestone',
                  after_block='minecraft:stone', held_item='minecraft:diamond_pickaxe', held_count_before=1,
                  held_count_after=1, inventory_consumption_observed=False,
                  confirmation='client_world_state_stable_3_end_ticks', confirmed_stable_ticks=3),
        ]
        directory = write_capture(self.root, bracket(rows))
        export_recording(directory)
        conversion = json.loads((directory / 'conversion.json').read_text())
        reasons = {row['reason'] for row in conversion['unsupported_conversions']}
        self.assertIn('placement_position_not_watched_by_native_intent', reasons)
        self.assertIn('confirmed_break_did_not_end_in_air', reasons)
        self.assertFalse(any(row['bcl'].startswith(('I3 ', 'C3 ')) for row in conversion['generated_operations']))

    def test_P2C12_placement_replay_requires_matching_recorded_support_face(self):
        rows = [
            event(1, 'use_on_block', client_tick=1, action='use', source='local_human_input', hand='main_hand',
                  target_position_absolute=[0, 63, 0], target_position_relative=[0, -1, 0], face='north',
                  held={'empty': False, 'item': 'minecraft:cobblestone', 'count': 1}, selected_hotbar=0,
                  player_position_absolute=[.5, 64., .5], player_position_relative=[0., 0., 0.], yaw=0., pitch=45.,
                  target_block='minecraft:grass_block', expected_placed_block='minecraft:cobblestone',
                  candidates=[{'position_absolute': [0, 64, 0], 'position_relative': [0, 0, 0],
                               'before_block': 'minecraft:air'}]),
            event(2, 'block_placed', client_tick=4, intent_sequence=1, source='local_human_input', hand='main_hand',
                  position_absolute=[0, 64, 0], position_relative=[0, 0, 0], before_block='minecraft:air',
                  after_block='minecraft:cobblestone', expected_block='minecraft:cobblestone',
                  held_item='minecraft:cobblestone', held_count_before=1, held_count_after=0,
                  inventory_consumption_observed=True, confirmation='client_world_state_stable_3_end_ticks',
                  confirmed_stable_ticks=3),
        ]
        directory = write_capture(self.root, bracket(rows))
        export_recording(directory)
        conversion = json.loads((directory / 'conversion.json').read_text())
        self.assertIn('placement_position_does_not_match_recorded_support_face',
                      {row['reason'] for row in conversion['unsupported_conversions']})
        self.assertFalse(any(row['bcl'].startswith(('V2 ', 'I3 '))
                             for row in conversion['generated_operations']))

        relative_root = self.root / 'relative-support';relative_root.mkdir()
        rows[0]['face'] = 'up';rows[0]['target_position_relative'] = [99, -1, 0]
        directory = write_capture(relative_root, bracket(rows))
        with self.assertRaisesRegex(Play2CodeError, 'placement support relative voxel'):
            export_recording(directory, coordinate_mode='relative')

    def test_P2C13_matching_airborne_jump_placement_is_explicitly_authorized(self):
        rows = [
            tick(1, .5),
            tick(2, .5, y=64.42, inputs={'jump': True}, on_ground=False),
            tick(3, .5, y=65.15, on_ground=False),
            event(4, 'use_on_block', client_tick=3, action='use', source='local_human_input', hand='main_hand',
                  target_position_absolute=[0, 63, 0], target_position_relative=[0, -1, 0], face='up',
                  held={'empty': False, 'item': 'minecraft:cobblestone', 'count': 1}, selected_hotbar=0,
                  player_position_absolute=[.5, 65.15, .5], player_position_relative=[0., 1.15, 0.],
                  yaw=0., pitch=90., target_block='minecraft:grass_block',
                  expected_placed_block='minecraft:cobblestone',
                  candidates=[{'position_absolute': [0, 64, 0], 'position_relative': [0, 0, 0],
                               'before_block': 'minecraft:air'}]),
            event(5, 'block_placed', client_tick=5, intent_sequence=4, source='local_human_input', hand='main_hand',
                  position_absolute=[0, 64, 0], position_relative=[0, 0, 0], before_block='minecraft:air',
                  after_block='minecraft:cobblestone', expected_block='minecraft:cobblestone',
                  held_item='minecraft:cobblestone', held_count_before=1, held_count_after=0,
                  inventory_consumption_observed=True, confirmation='client_world_state_stable_3_end_ticks',
                  confirmed_stable_ticks=3),
        ]
        directory = write_capture(self.root, bracket(rows))
        export_recording(directory, coordinate_mode='relative')
        conversion = json.loads((directory / 'conversion.json').read_text())
        placement = next(row for row in conversion['generated_operations'] if row['kind'] == 'confirmed_placement')
        self.assertEqual(placement['bcl'],
                         'I3 B=minecraft:cobblestone P=[0,-1,0] F=up A=true Q=[0,1.15,0] R=[0,0,0] J=true C=false')
        self.assertTrue(placement['recorded_jump_place'])

        nonjump_root = self.root / 'nonjump-placement';nonjump_root.mkdir()
        nonjump = json.loads(json.dumps(rows));nonjump[1]['inputs']['jump'] = False
        directory = write_capture(nonjump_root, bracket(nonjump))
        export_recording(directory, coordinate_mode='relative')
        conversion = json.loads((directory / 'conversion.json').read_text())
        placement = next(row for row in conversion['generated_operations'] if row['kind'] == 'confirmed_placement')
        self.assertNotIn('J=true', placement['bcl'])
        self.assertNotIn('recorded_jump_place', placement)

    def test_P2C14_matching_crouched_placement_stance_is_explicit(self):
        rows = [
            tick(1, .5, inputs={'sneak': True}),
            tick(2, .55, inputs={'forward': True, 'sneak': True}),
            event(3, 'use_on_block', client_tick=2, action='use', source='local_human_input', hand='main_hand',
                  target_position_absolute=[0, 63, 0], target_position_relative=[0, -1, 0], face='up',
                  held={'empty': False, 'item': 'minecraft:cobblestone', 'count': 1}, selected_hotbar=0,
                  player_position_absolute=[.55, 64., .5], player_position_relative=[.05, 0., 0.],
                  yaw=0., pitch=90., target_block='minecraft:grass_block',
                  expected_placed_block='minecraft:cobblestone',
                  candidates=[{'position_absolute': [0, 64, 0], 'position_relative': [0, 0, 0],
                               'before_block': 'minecraft:air'}]),
            event(4, 'block_placed', client_tick=4, intent_sequence=3, source='local_human_input', hand='main_hand',
                  position_absolute=[0, 64, 0], position_relative=[0, 0, 0], before_block='minecraft:air',
                  after_block='minecraft:cobblestone', expected_block='minecraft:cobblestone',
                  held_item='minecraft:cobblestone', held_count_before=1, held_count_after=0,
                  inventory_consumption_observed=True, confirmation='client_world_state_stable_3_end_ticks',
                  confirmed_stable_ticks=3),
        ]
        directory = write_capture(self.root, bracket(rows))
        export_recording(directory, coordinate_mode='relative')
        conversion = json.loads((directory / 'conversion.json').read_text())
        placement = next(row for row in conversion['generated_operations'] if row['kind'] == 'confirmed_placement')
        self.assertEqual(placement['bcl'],
                         'I3 B=minecraft:cobblestone P=[0,-1,0] F=up A=true Q=[0.05,0,0] R=[0.05,0,0] K=true C=false')
        self.assertTrue(placement['recorded_sneak'])

        invalid_root=self.root/'invalid-view';invalid_root.mkdir()
        invalid=json.loads(json.dumps(rows));invalid[2]['pitch']=0.
        directory=write_capture(invalid_root,bracket(invalid))
        with self.assertRaisesRegex(Play2CodeError,'parallel to recorded support face'):
            export_recording(directory,coordinate_mode='relative')

    def test_P2C15_elevated_recorded_sneak_edge_transition_tightens_only_its_predecessor(self):
        rows=[tick(1,.5,y=67.,z=.95,inputs={'forward':True,'sneak':True}),
              tick(2,.5,y=67.,z=1.02,inputs={'forward':True,'sneak':True})]
        directory=write_capture(self.root,bracket(rows))
        export_recording(directory,coordinate_mode='relative')
        conversion=json.loads((directory/'conversion.json').read_text())
        movement=[row for row in conversion['generated_operations'] if row['kind']=='movement_checkpoint']
        self.assertEqual([row['bcl'] for row in movement],
                         ['M0 X0 Y3 Z0.45 Fsneak A=0.15',
                          'M0 X0 Y3 Z0.52 Fsneak'])
        self.assertTrue(movement[0]['recorded_tight_arrival'])
        self.assertNotIn('recorded_tight_arrival',movement[1])

    def test_P2C16_rotating_lateral_edge_run_carries_exact_recorded_controls(self):
        rows=[tick(1,.5,y=67.,z=.95,inputs={'right':True,'sneak':True}),
              tick(2,.5,y=67.,z=1.02,inputs={'right':True,'sneak':True}),
              tick(3,.5,y=67.,z=1.09,inputs={'right':True,'sneak':True})]
        rows[1]['yaw']=40.;rows[2]['yaw']=40.
        directory=write_capture(self.root,bracket(rows))
        export_recording(directory,coordinate_mode='relative')
        conversion=json.loads((directory/'conversion.json').read_text())
        path=next(row for row in conversion['generated_operations'] if row['kind']=='recorded_movement_path')
        self.assertEqual(path['bcl'],'M3 T=[[0,3,0.45,0,0,3],[0,3,0.52,40,0,3],[0,3,0.59,40,0,3]]')
        self.assertEqual(path['source_sequences'],[1,2,3])
        self.assertEqual(path['recorded_samples'],3)
        self.assertTrue(path['recorded_control_replay'])

    def test_P2C17_crouched_placements_inside_selected_edge_run_form_one_sequence(self):
        first=tick(1,.5,y=67.,z=.95,inputs={'right':True,'sneak':True})
        second=tick(2,.5,y=67.,z=1.02,inputs={'right':True,'sneak':True})
        first['yaw']=0.;second['yaw']=40.
        eye=(.5,68.27,1.02);aim=(-1.,67.5,1.5);dx,dy,dz=[aim[i]-eye[i] for i in range(3)]
        yaw=math.degrees(math.atan2(-dx,dz));pitch=-math.degrees(math.atan2(dy,math.hypot(dx,dz)))
        intent=event(3,'use_on_block',client_tick=2,action='use',source='local_human_input',hand='main_hand',
                     target_position_absolute=[-2,67,1],target_position_relative=[-2,3,1],face='east',
                     held={'empty':False,'item':'minecraft:cobblestone','count':1},selected_hotbar=0,
                     player_position_absolute=[.5,67.,1.02],player_position_relative=[0.,3.,.52],yaw=yaw,pitch=pitch,
                     target_block='minecraft:cobblestone',expected_placed_block='minecraft:cobblestone',
                     candidates=[{'position_absolute':[-1,67,1],'position_relative':[-1,3,1],'before_block':'minecraft:air'}])
        third=tick(4,.5,y=67.,z=1.09,inputs={'right':True,'sneak':True});third['yaw']=40.
        confirmed=event(5,'block_placed',client_tick=5,intent_sequence=3,source='local_human_input',hand='main_hand',
                        position_absolute=[-1,67,1],position_relative=[-1,3,1],before_block='minecraft:air',
                        after_block='minecraft:cobblestone',expected_block='minecraft:cobblestone',
                        held_item='minecraft:cobblestone',held_count_before=1,held_count_after=0,
                        inventory_consumption_observed=True,confirmation='client_world_state_stable_3_end_ticks',confirmed_stable_ticks=3)
        directory=write_capture(self.root,bracket([first,second,intent,third,confirmed]))
        export_recording(directory,coordinate_mode='relative')
        conversion=json.loads((directory/'conversion.json').read_text())
        sequence=next(row for row in conversion['generated_operations'] if row['kind']=='recorded_action_sequence')
        events=json.loads(json.loads(sequence['bcl'].split('=',1)[1]))
        self.assertEqual([row[0] for row in events],[0,0,1,0])
        self.assertEqual(events[2][1:6],['minecraft:cobblestone',-2,3,1,4])
        self.assertEqual(sequence['source_sequences'],[1,2,4])
        self.assertEqual(sequence['embedded_placement_sequences'],[5])
        self.assertEqual(sequence['embedded_placements'],1)

    def test_P2C18_confirmed_hotbar_stack_depletion_forces_same_item_reequip(self):
        first=tick(1,.65)
        intent1=event(2,'use_on_block',client_tick=1,action='use',source='local_human_input',hand='main_hand',
                      target_position_absolute=[0,63,0],target_position_relative=[0,-1,0],face='up',
                      held={'empty':False,'item':'minecraft:cobblestone','count':1},selected_hotbar=0,
                      player_position_absolute=[.65,64.,.5],player_position_relative=[.15,0.,0.],yaw=0.,pitch=90.,
                      target_block='minecraft:grass_block',expected_placed_block='minecraft:cobblestone',
                      candidates=[{'position_absolute':[0,64,0],'position_relative':[0,0,0],'before_block':'minecraft:air'}])
        placed1=event(3,'block_placed',client_tick=3,intent_sequence=2,source='local_human_input',hand='main_hand',
                      position_absolute=[0,64,0],position_relative=[0,0,0],before_block='minecraft:air',
                      after_block='minecraft:cobblestone',expected_block='minecraft:cobblestone',
                      held_item='minecraft:cobblestone',held_count_before=1,held_count_after=0,
                      inventory_consumption_observed=True,confirmation='client_world_state_stable_3_end_ticks',confirmed_stable_ticks=3)
        second=tick(4,1.5)
        intent2=event(5,'use_on_block',client_tick=3,action='use',source='local_human_input',hand='main_hand',
                      target_position_absolute=[1,63,0],target_position_relative=[1,-1,0],face='up',
                      held={'empty':False,'item':'minecraft:cobblestone','count':64},selected_hotbar=1,
                      player_position_absolute=[1.5,64.,.5],player_position_relative=[1.,0.,0.],yaw=0.,pitch=90.,
                      target_block='minecraft:grass_block',expected_placed_block='minecraft:cobblestone',
                      candidates=[{'position_absolute':[1,64,0],'position_relative':[1,0,0],'before_block':'minecraft:air'}])
        placed2=event(6,'block_placed',client_tick=6,intent_sequence=5,source='local_human_input',hand='main_hand',
                      position_absolute=[1,64,0],position_relative=[1,0,0],before_block='minecraft:air',
                      after_block='minecraft:cobblestone',expected_block='minecraft:cobblestone',
                      held_item='minecraft:cobblestone',held_count_before=64,held_count_after=63,
                      inventory_consumption_observed=True,confirmation='client_world_state_stable_3_end_ticks',confirmed_stable_ticks=3)
        directory=write_capture(self.root,bracket([first,intent1,placed1,second,intent2,placed2]))
        export_recording(directory,coordinate_mode='relative')
        operations=json.loads((directory/'conversion.json').read_text())['generated_operations']
        self.assertEqual([row['bcl'] for row in operations if row['bcl'].startswith('I1 ')],
                         ['I1 I=minecraft:cobblestone','I1 I=minecraft:cobblestone'])

    def test_P2C19_bounded_recorded_step_off_maps_to_native_drop_with_landing(self):
        approach=tick(1,.5,y=67.,z=.5,inputs={'forward':True,'sneak':True},sneaking=True)
        edge=tick(2,.4,y=67.,z=.4,inputs={'forward':True});edge['yaw']=45.;edge['pitch']=10.
        air1=tick(3,.3,y=66.8,z=.3,on_ground=False)
        air2=tick(4,.2,y=65.,z=.2,on_ground=False)
        landed=tick(5,.1,y=64.,z=.1)
        directory=write_capture(self.root,bracket([approach,edge,air1,air2,landed]))
        export_recording(directory,coordinate_mode='relative')
        conversion=json.loads((directory/'conversion.json').read_text())
        drop=next(row for row in conversion['generated_operations'] if row['kind']=='recorded_drop')
        self.assertEqual(drop['bcl'],'M5 Q=[-0.1,3,-0.1] L=[-0.4,0,-0.4] H45 P10 B=forward')
        self.assertEqual(drop['source_sequences'],[2,3,4,5]);self.assertTrue(drop['recorded_control_replay'])
        self.assertFalse(any(row['source_sequence'] in {3,4,5} for row in conversion['unsupported_conversions']))

    def test_P2C20_integer_translation_transforms_typed_coordinates_without_reordering(self):
        rows = [tick(1, .5), tick(2, .65, inputs={'forward': True})]
        rows += [
            event(3, 'use_on_block', client_tick=2, action='use', source='local_human_input', hand='main_hand',
                  target_position_absolute=[0, 63, 0], target_position_relative=[0, -1, 0], face='up',
                  held={'empty': False, 'item': 'minecraft:cobblestone', 'count': 64}, selected_hotbar=0,
                  player_position_absolute=[.65, 64., .5], player_position_relative=[.15, 0., 0.], yaw=0., pitch=90.,
                  target_block='minecraft:grass_block', expected_placed_block='minecraft:cobblestone',
                  candidates=[{'position_absolute': [0, 64, 0], 'position_relative': [0, 0, 0],
                               'before_block': 'minecraft:air'}]),
            event(4, 'block_placed', client_tick=4, intent_sequence=3, source='local_human_input', hand='main_hand',
                  position_absolute=[0, 64, 0], position_relative=[0, 0, 0], before_block='minecraft:air',
                  after_block='minecraft:cobblestone', expected_block='minecraft:cobblestone',
                  held_item='minecraft:cobblestone', held_count_before=64, held_count_after=63,
                  inventory_consumption_observed=True, confirmation='client_world_state_stable_3_end_ticks',
                  confirmed_stable_ticks=3),
            event(5, 'break_intent', client_tick=5, action='break', source='local_human_input', hand='main_hand',
                  target_position_absolute=[1, 64, 0], target_position_relative=[1, 0, 0], face='up',
                  held={'empty': False, 'item': 'minecraft:diamond_pickaxe', 'count': 1}, selected_hotbar=1,
                  player_position_absolute=[.65, 64., .5], player_position_relative=[.15, 0., 0.], yaw=0., pitch=45.,
                  before_block='minecraft:cobblestone'),
            event(6, 'block_broken', client_tick=8, intent_sequence=5, source='local_human_input', hand='main_hand',
                  position_absolute=[1, 64, 0], position_relative=[1, 0, 0], before_block='minecraft:cobblestone',
                  after_block='minecraft:air', held_item='minecraft:diamond_pickaxe', held_count_before=1,
                  held_count_after=1, inventory_consumption_observed=False,
                  confirmation='client_world_state_stable_3_end_ticks', confirmed_stable_ticks=3),
        ]
        directory = write_capture(self.root, bracket(rows))
        original = export_recording(directory, output_root=self.root/'original', coordinate_mode='relative')
        transformed = export_recording(directory, output_root=self.root/'translated', coordinate_mode='relative',
                                       coordinate_transform=CoordinateTransform((10, 0, -4)))
        original_conversion = json.loads((Path(original['directory'])/'conversion.json').read_text())
        conversion = json.loads((Path(transformed['directory'])/'conversion.json').read_text())
        identity = [(row['source_sequence'], row['kind']) for row in original_conversion['generated_operations']]
        derived = [(row['source_sequence'], row['kind']) for row in conversion['generated_operations']]
        self.assertEqual(derived, identity)
        lines = [row['bcl'] for row in conversion['generated_operations']]
        self.assertIn('M0 X10.15 Y0 Z-4 Fnormal', lines)
        self.assertIn('V2 X10.15 Y0 Z-4', lines)
        self.assertIn('I3 B=minecraft:cobblestone P=[10,-1,-4] F=up A=true Q=[10.15,0,-4] R=[10.15,0,-4] C=false', lines)
        self.assertIn('C3 B=minecraft:cobblestone P=[11,0,-4] D=false', lines)
        target = Path(transformed['directory'])
        self.assertEqual((target/'raw-timeline.jsonl').read_bytes(), (directory/'raw-timeline.jsonl').read_bytes())
        manifest = json.loads((target/'manifest.json').read_text())
        self.assertEqual(manifest['derivation']['classification'], 'DERIVED_COORDINATE_TRANSFORM_NOT_NEW_HUMAN_RECORDING')
        self.assertEqual(manifest['coordinate_contract']['transform']['translation'], [10, 0, -4])
        self.assertEqual(sum(path.read_text().count('S1 relative') for path in (target/'bcl').glob('*.bcl')), 1)
        self.assertNotIn('derivation', json.loads((Path(original['directory'])/'manifest.json').read_text()))

    def test_P2C21_horizontal_mirror_transforms_yaw_faces_hit_points_and_native_drop(self):
        approach=tick(1,.5,y=67.,z=.5,inputs={'forward':True,'sneak':True},sneaking=True)
        edge=tick(2,.4,y=67.,z=.4,inputs={'forward':True});edge['yaw']=45.;edge['pitch']=10.
        air1=tick(3,.3,y=66.8,z=.3,on_ground=False);air2=tick(4,.2,y=65.,z=.2,on_ground=False)
        landed=tick(5,.1,y=64.,z=.1)
        pitch=math.degrees(math.atan2(1.12,2.))
        intent=event(6,'use_on_block',client_tick=5,action='use',source='local_human_input',hand='main_hand',
                     target_position_absolute=[0,64,1],target_position_relative=[0,0,1],face='north',
                     held={'empty':False,'item':'minecraft:cobblestone','count':1},selected_hotbar=0,
                     player_position_absolute=[.5,64.,-1.],player_position_relative=[0.,0.,-1.5],yaw=0.,pitch=pitch,
                     target_block='minecraft:cobblestone',expected_placed_block='minecraft:cobblestone',
                     candidates=[{'position_absolute':[0,64,0],'position_relative':[0,0,0],'before_block':'minecraft:air'}])
        placed=event(7,'block_placed',client_tick=7,intent_sequence=6,source='local_human_input',hand='main_hand',
                     position_absolute=[0,64,0],position_relative=[0,0,0],before_block='minecraft:air',
                     after_block='minecraft:cobblestone',expected_block='minecraft:cobblestone',
                     held_item='minecraft:cobblestone',held_count_before=1,held_count_after=0,
                     inventory_consumption_observed=True,confirmation='client_world_state_stable_3_end_ticks',confirmed_stable_ticks=3)
        directory=write_capture(self.root,bracket([approach,edge,air1,air2,landed,intent,placed]))
        transform=CoordinateTransform(mirror_axis='z',mirror_coordinate=0)
        result=export_recording(directory,output_root=self.root/'mirrored',coordinate_mode='relative',
                                coordinate_transform=transform)
        operations=json.loads((Path(result['directory'])/'conversion.json').read_text())['generated_operations']
        lines=[row['bcl'] for row in operations]
        self.assertIn('M5 Q=[-0.1,3,0.1] L=[-0.4,0,0.4] H135 P10 B=forward',lines)
        self.assertIn('V2 X0 Y0.5 Z-0.5',lines)
        self.assertIn('I3 B=minecraft:cobblestone P=[0,0,-1] F=south A=true Q=[0,0,1.5] R=[0,0.5,-0.5] C=false',lines)
        self.assertEqual(transform.voxel((0,64,1)),(0,64,-1))
        self.assertEqual(transform.point((.5,64.,-1.)),(.5,64.,2.))
        self.assertEqual(transform.face('north'),'south');self.assertAlmostEqual(transform.yaw(45.),135.)
        self.assertEqual(transform.direction('right'),'left');self.assertEqual(transform.direction('forward_right'),'forward_left')
        mirror=json.loads((Path(result['directory'])/'manifest.json').read_text())['coordinate_contract']['transform']['mirror']
        self.assertEqual(mirror,{'axis':'z','continuous_plane':.5,'voxel_coordinate':0})

    def test_P2C23_mirror_swaps_lateral_recorded_controls_with_reflected_yaw(self):
        rows=[tick(1,.5,y=67.,z=.95,inputs={'right':True,'sneak':True}),
              tick(2,.5,y=67.,z=1.02,inputs={'right':True,'sneak':True}),
              tick(3,.5,y=67.,z=1.09,inputs={'right':True,'sneak':True})]
        rows[1]['yaw']=40.;rows[2]['yaw']=40.
        directory=write_capture(self.root,bracket(rows))
        result=export_recording(directory,output_root=self.root/'mirrored-controls',coordinate_mode='relative',
                                coordinate_transform=CoordinateTransform(mirror_axis='z',mirror_coordinate=0))
        conversion=json.loads((Path(result['directory'])/'conversion.json').read_text())
        path=next(row for row in conversion['generated_operations'] if row['kind']=='recorded_movement_path')
        self.assertEqual(path['bcl'],'M3 T=[[0,3,-0.45,-180,0,2],[0,3,-0.52,140,0,2],[0,3,-0.59,140,0,2]]')
        self.assertEqual(path['source_sequences'],[1,2,3]);self.assertTrue(path['recorded_control_replay'])

    def test_P2C24_quarter_turns_use_explicit_block_centre_anchor_and_minecraft_yaw(self):
        anchor=(3,-2);voxel=(5,64,-1);point=(5.25,64.5,-.75)
        expected={
            90:((2,64,0),(2.75,64.5,.25)),
            180:((1,64,-3),(1.75,64.5,-2.25)),
            270:((4,64,-4),(4.25,64.5,-3.25)),
        }
        face_expected={
            90:{'north':'east','east':'south','south':'west','west':'north'},
            180:{'north':'south','east':'west','south':'north','west':'east'},
            270:{'north':'west','east':'north','south':'east','west':'south'},
        }
        offsets={'up':(0,1,0),'down':(0,-1,0),'north':(0,0,-1),'south':(0,0,1),'east':(1,0,0),'west':(-1,0,0)}
        face_points={'up':(.5,1.,.5),'down':(.5,0.,.5),'north':(.5,.5,0.),'south':(.5,.5,1.),'east':(1.,.5,.5),'west':(0.,.5,.5)}
        support=(2,10,-3)
        for rotation in (90,180,270):
            transform=CoordinateTransform(rotation=rotation,rotation_anchor=anchor)
            self.assertEqual(transform.voxel(voxel),expected[rotation][0]);self.assertEqual(transform.point(point),expected[rotation][1])
            self.assertEqual(transform.point((-4.25,-7.,3.5))[1],-7.)
            self.assertEqual({face:transform.face(face) for face in ('north','east','south','west')},face_expected[rotation])
            self.assertEqual(transform.face('up'),'up');self.assertEqual(transform.face('down'),'down')
            for face,offset in offsets.items():
                destination=tuple(support[index]+offset[index] for index in range(3));output_face=transform.face(face)
                transformed_support=transform.voxel(support);transformed_destination=transform.voxel(destination)
                self.assertEqual(transformed_destination,tuple(transformed_support[index]+offsets[output_face][index] for index in range(3)))
                hit=tuple(support[index]+face_points[face][index] for index in range(3));transformed_hit=transform.point(hit)
                expected_hit=tuple(transformed_support[index]+face_points[output_face][index] for index in range(3))
                self.assertEqual(transformed_hit,expected_hit)
            self.assertEqual(transform.direction('right'),'right');self.assertEqual(transform.direction('forward_left'),'forward_left')
            for yaw in (-180.,-135.,-90.,-45.,0.,45.,90.,135.,179.):
                expected_yaw=(yaw+rotation+180)%360-180
                self.assertAlmostEqual(transform.yaw(yaw),expected_yaw)
            metadata=transform.to_dict()['rotation']
            self.assertEqual(metadata['voxel_anchor'],[3,-2]);self.assertEqual(metadata['continuous_anchor'],[3.5,-1.5])
            self.assertEqual(metadata['direction'],'positive_minecraft_yaw_clockwise_on_north_up_map')

    def test_P2C25_quarter_turn_composition_preserves_distance_precision_and_order(self):
        anchor=(3,-2);turn90=CoordinateTransform(rotation=90,rotation_anchor=anchor)
        turn180=CoordinateTransform(rotation=180,rotation_anchor=anchor)
        turn270=CoordinateTransform(rotation=270,rotation_anchor=anchor)
        original_point=(-4.25,12.5,3.75);original_voxel=(-4,12,3)
        point=original_point;voxel=original_voxel
        for _ in range(4):point=turn90.point(point);voxel=turn90.voxel(voxel)
        self.assertEqual(point,original_point);self.assertEqual(voxel,original_voxel)
        self.assertEqual(turn180.point(turn180.point(original_point)),original_point)
        self.assertEqual(turn270.point(turn90.point(original_point)),original_point)
        centre=(anchor[0]+.5,anchor[1]+.5)
        rotated=turn90.point(original_point)
        self.assertAlmostEqual(math.hypot(original_point[0]-centre[0],original_point[2]-centre[1]),
                               math.hypot(rotated[0]-centre[0],rotated[2]-centre[1]))
        combined=CoordinateTransform((10,2,-4),'z',0,90,(0,0))
        self.assertEqual(combined.voxel((2,5,3)),(13,7,-2))
        self.assertEqual(combined.point((2.25,5.5,3.75)),(13.75,7.5,-1.75))
        self.assertEqual(combined.face('north'),'west');self.assertEqual(combined.yaw(0),-90)
        self.assertEqual(combined.direction('right'),'left')
        self.assertEqual(combined.to_dict()['order'],'mirror_then_rotate_then_translate')

    def test_P2C26_rotation_transforms_drop_support_face_pose_aim_and_bcl_without_reordering(self):
        approach=tick(1,.5,y=67.,z=.5,inputs={'forward':True,'sneak':True},sneaking=True)
        edge=tick(2,.4,y=67.,z=.4,inputs={'forward':True});edge['yaw']=45.;edge['pitch']=10.
        air1=tick(3,.3,y=66.8,z=.3,on_ground=False);air2=tick(4,.2,y=65.,z=.2,on_ground=False)
        landed=tick(5,.1,y=64.,z=.1)
        pitch=math.degrees(math.atan2(1.12,2.))
        intent=event(6,'use_on_block',client_tick=5,action='use',source='local_human_input',hand='main_hand',
                     target_position_absolute=[0,64,1],target_position_relative=[0,0,1],face='north',
                     held={'empty':False,'item':'minecraft:cobblestone','count':1},selected_hotbar=0,
                     player_position_absolute=[.5,64.,-1.],player_position_relative=[0.,0.,-1.5],yaw=0.,pitch=pitch,
                     target_block='minecraft:cobblestone',expected_placed_block='minecraft:cobblestone',
                     candidates=[{'position_absolute':[0,64,0],'position_relative':[0,0,0],'before_block':'minecraft:air'}])
        placed=event(7,'block_placed',client_tick=7,intent_sequence=6,source='local_human_input',hand='main_hand',
                     position_absolute=[0,64,0],position_relative=[0,0,0],before_block='minecraft:air',
                     after_block='minecraft:cobblestone',expected_block='minecraft:cobblestone',
                     held_item='minecraft:cobblestone',held_count_before=1,held_count_after=0,
                     inventory_consumption_observed=True,confirmation='client_world_state_stable_3_end_ticks',confirmed_stable_ticks=3)
        directory=write_capture(self.root,bracket([approach,edge,air1,air2,landed,intent,placed]))
        original=export_recording(directory,output_root=self.root/'rotation-original',coordinate_mode='relative')
        result=export_recording(directory,output_root=self.root/'rotated',coordinate_mode='relative',
                                coordinate_transform=CoordinateTransform(rotation=90,rotation_anchor=(0,0)))
        original_operations=json.loads((Path(original['directory'])/'conversion.json').read_text())['generated_operations']
        operations=json.loads((Path(result['directory'])/'conversion.json').read_text())['generated_operations']
        self.assertEqual([(row['source_sequence'],row['kind']) for row in operations],
                         [(row['source_sequence'],row['kind']) for row in original_operations])
        lines=[row['bcl'] for row in operations]
        self.assertIn('M5 Q=[0.1,3,-0.1] L=[0.4,0,-0.4] H135 P10 B=forward',lines)
        self.assertIn('V2 X-0.5 Y0.5 Z0',lines)
        self.assertIn('I3 B=minecraft:cobblestone P=[-1,0,0] F=east A=true Q=[1.5,0,0] R=[-0.5,0.5,0] C=false',lines)
        manifest=json.loads((Path(result['directory'])/'manifest.json').read_text())
        self.assertEqual(manifest['coordinate_contract']['transform']['rotation']['degrees'],90)
        self.assertEqual(sum(path.read_text().count('S1 relative') for path in (Path(result['directory'])/'bcl').glob('*.bcl')),1)

    def test_P2C27_rotation_preserves_player_local_M3_direction_while_rotating_path_and_yaw(self):
        rows=[tick(1,.5,y=67.,z=.95,inputs={'right':True,'sneak':True}),
              tick(2,.5,y=67.,z=1.02,inputs={'right':True,'sneak':True}),
              tick(3,.5,y=67.,z=1.09,inputs={'right':True,'sneak':True})]
        rows[1]['yaw']=40.;rows[2]['yaw']=40.
        directory=write_capture(self.root,bracket(rows))
        result=export_recording(directory,output_root=self.root/'rotated-controls',coordinate_mode='relative',
                                coordinate_transform=CoordinateTransform(rotation=90,rotation_anchor=(0,0)))
        conversion=json.loads((Path(result['directory'])/'conversion.json').read_text())
        path=next(row for row in conversion['generated_operations'] if row['kind']=='recorded_movement_path')
        self.assertEqual(path['bcl'],'M3 T=[[-0.45,3,0,90,0,3],[-0.52,3,0,130,0,3],[-0.59,3,0,130,0,3]]')
        self.assertEqual(path['source_sequences'],[1,2,3]);self.assertTrue(path['recorded_control_replay'])

    def test_P2C22_invalid_or_implicit_coordinate_transforms_fail_closed(self):
        with self.assertRaisesRegex(Play2CodeError,'three strict integers'):CoordinateTransform((0,False,0))
        with self.assertRaisesRegex(Play2CodeError,'axis must be x or z'):CoordinateTransform(mirror_axis='y',mirror_coordinate=0)
        with self.assertRaisesRegex(Play2CodeError,'requires a strict integer'):CoordinateTransform(mirror_axis='z')
        with self.assertRaisesRegex(Play2CodeError,'requires a mirror axis'):CoordinateTransform(mirror_coordinate=0)
        with self.assertRaisesRegex(Play2CodeError,'one of 0, 90, 180 or 270'):CoordinateTransform(rotation=45,rotation_anchor=(0,0))
        with self.assertRaisesRegex(Play2CodeError,'requires two strict integer'):CoordinateTransform(rotation=90)
        with self.assertRaisesRegex(Play2CodeError,'two strict integer'):CoordinateTransform(rotation=90,rotation_anchor=(0,False))
        with self.assertRaisesRegex(Play2CodeError,'requires a nonzero rotation'):CoordinateTransform(rotation_anchor=(0,0))
        directory=write_capture(self.root,bracket([tick(1,.5)]))
        with self.assertRaisesRegex(Play2CodeError,'CoordinateTransform'):
            export_recording(directory,coordinate_transform={})
        self.assertFalse((directory/'manifest.json').exists())

    def test_P2C04_remote_interference_actor_and_sequence_fail_closed(self):
        rows = bracket([tick(1, .5)])
        unsafe = write_capture(self.root, rows, safe=False)
        unsafe_capture = json.loads((unsafe / 'capture.json').read_text())
        unsafe_capture['remote_control'] = {'endpoint_disabled_at_start': True,
                                            'endpoint_enabled_during_recording': False,
                                            'remote_owned_input_observed': False}
        (unsafe / 'capture.json').write_text(json.dumps(unsafe_capture))
        with self.assertRaisesRegex(Play2CodeError, 'remote-controller'):
            load_recording(unsafe)
        self.assertFalse((unsafe / 'manifest.json').exists())

        remote_root = self.root / 'remote-tick';remote_root.mkdir()
        remote_tick = write_capture(remote_root, bracket([tick(1, .5, remote=['forward'])]))
        with self.assertRaisesRegex(Play2CodeError, 'remote-owned input'):
            load_recording(remote_tick)

        actor_root = self.root / 'actor-tick';actor_root.mkdir()
        actor_tick = tick(1, .5);actor_tick['actor_session'] = 'actor-session-b'
        actor_capture = write_capture(actor_root, bracket([actor_tick]))
        with self.assertRaisesRegex(Play2CodeError, 'actor session'):
            load_recording(actor_capture)

        other = self.root / 'other';other.mkdir()
        # Keep a valid path identity, then corrupt one event sequence.
        directory = other / ID;directory.mkdir()
        broken = bracket([tick(1, .5)]);broken[1]['sequence'] = 9
        timeline = directory / 'raw-timeline.jsonl'
        timeline.write_text(''.join(json.dumps(row) + '\n' for row in broken))
        capture = json.loads((unsafe / 'capture.json').read_text())
        capture.update(no_remote_controller_interference=True,
                       remote_control={'endpoint_disabled_at_start': True,
                                       'endpoint_enabled_during_recording': False,
                                       'remote_owned_input_observed': False},
                       event_count=len(broken), timeline_bytes=timeline.stat().st_size)
        (directory / 'capture.json').write_text(json.dumps(capture))
        with self.assertRaisesRegex(Play2CodeError, 'sequence'):
            load_recording(directory)

    def test_P2C08_completed_capture_requires_one_explicit_stop_request(self):
        rows = [row for row in bracket([tick(1, .5)]) if row['type'] != 'recording_stop_requested']
        for sequence, row in enumerate(rows):row['sequence'] = sequence
        directory = write_capture(self.root, rows)
        with self.assertRaisesRegex(Play2CodeError, 'lifecycle'):
            load_recording(directory)

    def test_P2C09_invalid_utf8_and_unterminated_timeline_fail_closed(self):
        utf_root = self.root / 'invalid-utf8';utf_root.mkdir()
        invalid_utf = write_capture(utf_root, bracket([tick(1, .5)]))
        (invalid_utf / 'capture.json').write_bytes(b'\xff\n')
        with self.assertRaisesRegex(Play2CodeError, 'UTF-8'):
            load_recording(invalid_utf)

        line_root = self.root / 'unterminated';line_root.mkdir()
        unterminated = write_capture(line_root, bracket([tick(1, .5)]))
        timeline = unterminated / 'raw-timeline.jsonl'
        timeline.write_bytes(timeline.read_bytes()[:-1])
        capture = json.loads((unterminated / 'capture.json').read_text())
        capture['timeline_bytes'] = timeline.stat().st_size
        (unterminated / 'capture.json').write_text(json.dumps(capture) + '\n')
        with self.assertRaisesRegex(Play2CodeError, 'newline terminated'):
            load_recording(unterminated)

    def test_P2C05_output_copy_is_private_and_raw_hash_is_retained(self):
        directory = write_capture(self.root, bracket([tick(1, .5), tick(2, .7, inputs={'forward': True})]))
        output = self.root / 'exports'
        result = export_recording(directory, output_root=output)
        target = Path(result['directory'])
        self.assertNotEqual(target, directory)
        self.assertEqual((target / 'raw-timeline.jsonl').read_bytes(), (directory / 'raw-timeline.jsonl').read_bytes())
        self.assertEqual(json.loads((target / 'manifest.json').read_text())['replay']['status'], 'NOT_RUN')
        with self.assertRaisesRegex(Play2CodeError, 'already exported|conflicting'):
            export_recording(target)
        if os.name == 'posix':
            self.assertEqual(target.stat().st_mode & 0o777, 0o700)
            self.assertEqual((target / 'manifest.json').stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
