"""Passive recording/export contracts. Synthetic timelines are parser fixtures, not Minecraft evidence."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from blockwire.bcl import compile_bcl, default_commands
from blockwire.play2code import (
    CAPTURE_SCHEMA, EVENT_SCHEMA, Play2CodeError, export_recording,
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
                  player_position_absolute=[.65, 64., .5], player_position_relative=[.15, 0., 0.], yaw=0., pitch=45.,
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
        self.assertIn('I4 B=minecraft:cobblestone P=[0,64,0] C=false', lines)
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
        self.assertIn('only_confirmed_main_hand_block_use_maps_to_I4', reasons)
        self.assertIn('no_confirmed_world_mutation', reasons)
        self.assertIn('mutation_not_stably_confirmed', reasons)
        self.assertIn('conversion_rejected_by_installed_registry', reasons)
        self.assertFalse(any(row['bcl'].startswith('I4 ') for row in conversion['generated_operations']))

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
        self.assertFalse(any(row['bcl'].startswith(('I4 ', 'C3 ')) for row in conversion['generated_operations']))

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
