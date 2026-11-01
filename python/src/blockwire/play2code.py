"""Export passive native human-play recordings as raw evidence plus conservative BCL/1 batches.

Compilation proves only that generated source matches the installed registry. It does not
qualify replay or claim that a recorded gameplay outcome will reproduce successfully.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any
import uuid

from .bcl import BCLError, compile_bcl, default_commands

EVENT_SCHEMA = 'blockwire.play2code.event.v1'
CAPTURE_SCHEMA = 'blockwire.play2code.capture.v1'
MANIFEST_SCHEMA = 'blockwire.play2code.manifest.v1'
CONVERSION_SCHEMA = 'blockwire.play2code.conversion.v1'
CAPTURE_PROFILE = 'native_local_human_timeline_v1'
MAX_TIMELINE_BYTES = 256 * 1024 * 1024
MAX_EVENTS = 300_000
MAX_LINE_BYTES = 128 * 1024
BATCH_PREFIX = ('BCL/1', 'S0 sync', 'S1 absolute', 'S3 stop')
BATCH_PAYLOAD_LIMIT = 32 - (len(BATCH_PREFIX) - 1)
MOVEMENT_KEYS = ('forward', 'back', 'left', 'right', 'jump', 'sneak', 'sprint')
MOTION_KEYS = ('forward', 'back', 'left', 'right', 'jump')
AIR_BLOCKS = frozenset({'minecraft:air', 'minecraft:cave_air', 'minecraft:void_air'})
ID_PATTERN = re.compile(r"[0-9]{8}T[0-9]{6}\.[0-9]{3}Z-[0-9a-f]{8}")
STABLE_PATTERN = re.compile(r"client_world_state_stable_([0-9]+)_end_ticks")


class Play2CodeError(ValueError):
    pass


@dataclass(frozen=True)
class Recording:
    directory: Path
    capture: dict[str, Any]
    events: tuple[dict[str, Any], ...]
    timeline: Path

    @property
    def recording_id(self) -> str:
        return self.capture['recording_id']


def _duplicate_safe(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Play2CodeError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def _json(text: str):
    try:
        return json.loads(text, object_pairs_hook=_duplicate_safe,
                          parse_constant=lambda value: (_ for _ in ()).throw(Play2CodeError(f'nonfinite JSON: {value}')))
    except Play2CodeError:
        raise
    except (ValueError, TypeError, RecursionError) as error:
        raise Play2CodeError('malformed recording JSON') from error


def _regular(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise Play2CodeError(f'{label} must be a regular non-symlink file')


def _vector(value, label: str, *, integers: bool = False):
    if not isinstance(value, list) or len(value) != 3:
        raise Play2CodeError(f'{label} must contain three coordinates')
    if integers:
        if any(type(number) is not int for number in value):
            raise Play2CodeError(f'{label} must contain strict integers')
    elif any(type(number) not in (int, float) or not math.isfinite(number) for number in value):
        raise Play2CodeError(f'{label} must contain finite numbers')
    return tuple(value)


def load_recording(directory: str | Path) -> Recording:
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise Play2CodeError('recording directory must be a non-symlink directory')
    capture_path = directory / 'capture.json'
    _regular(capture_path, 'capture metadata')
    capture_bytes = capture_path.read_bytes()
    if len(capture_bytes) > MAX_LINE_BYTES:
        raise Play2CodeError('capture metadata exceeds bound')
    try:
        capture_text = capture_bytes.decode('utf-8')
    except UnicodeDecodeError as error:
        raise Play2CodeError('capture metadata is not valid UTF-8') from error
    capture = _json(capture_text)
    if not isinstance(capture, dict) or capture.get('schema') != CAPTURE_SCHEMA:
        raise Play2CodeError('unsupported capture schema')
    recording_id = capture.get('recording_id')
    if not isinstance(recording_id, str) or not ID_PATTERN.fullmatch(recording_id) or directory.name != recording_id:
        raise Play2CodeError('recording identity/path mismatch')
    if (capture.get('status') != 'completed' or capture.get('reason') != 'user_requested' or
            capture.get('timeline_sealed') is not True):
        raise Play2CodeError('only a user-completed sealed recording can be exported')
    if capture.get('profile') != CAPTURE_PROFILE:
        raise Play2CodeError('unsupported capture profile')
    actor_session = capture.get('actor_session')
    if not isinstance(actor_session, str) or not actor_session or len(actor_session) > 128:
        raise Play2CodeError('capture actor session is invalid')
    player_uuid = capture.get('player_uuid')
    try:
        if not isinstance(player_uuid, str) or str(uuid.UUID(player_uuid)) != player_uuid:
            raise ValueError
    except ValueError as error:
        raise Play2CodeError('capture player UUID is invalid') from error
    dimension = capture.get('dimension')
    if not isinstance(dimension, str) or not re.fullmatch(r'[a-z0-9_.-]+:[a-z0-9_./-]+', dimension):
        raise Play2CodeError('capture dimension is invalid')
    for field in ('started_at_ms', 'ended_at_ms', 'duration_ns'):
        if type(capture.get(field)) is not int or capture[field] < 0:
            raise Play2CodeError(f'capture {field} is invalid')
    if capture['ended_at_ms'] < capture['started_at_ms']:
        raise Play2CodeError('capture wall-clock interval is invalid')
    if capture.get('no_remote_controller_interference') is not True:
        raise Play2CodeError('remote-controller exclusion was not established')
    remote = capture.get('remote_control')
    if not isinstance(remote, dict) or remote != {
        'endpoint_disabled_at_start': True,
        'endpoint_enabled_during_recording': False,
        'remote_owned_input_observed': False,
    }:
        raise Play2CodeError('remote-controller metadata is incomplete or unsafe')
    timeline_name = capture.get('timeline')
    if timeline_name != 'raw-timeline.jsonl':
        raise Play2CodeError('unexpected timeline name')
    timeline = directory / timeline_name
    _regular(timeline, 'raw timeline')
    size = timeline.stat().st_size
    if not 0 < size <= MAX_TIMELINE_BYTES:
        raise Play2CodeError('timeline size outside bound')
    if type(capture.get('timeline_bytes')) is not int or capture['timeline_bytes'] != size:
        raise Play2CodeError('capture timeline byte count mismatch')
    events = []
    prior_monotonic = -1
    with timeline.open('rb') as stream:
        index = 0
        while True:
            raw = stream.readline(MAX_LINE_BYTES + 1)
            if not raw:
                break
            if index >= MAX_EVENTS:
                raise Play2CodeError('event count exceeds bound')
            if len(raw) > MAX_LINE_BYTES:
                raise Play2CodeError('event line exceeds bound')
            if not raw.endswith(b'\n'):
                raise Play2CodeError('event line is not newline terminated')
            try:
                line = raw.decode('utf-8')
            except UnicodeDecodeError as error:
                raise Play2CodeError('event line is not valid UTF-8') from error
            event = _json(line)
            if not isinstance(event, dict) or event.get('schema') != EVENT_SCHEMA:
                raise Play2CodeError('unsupported event schema')
            if event.get('recording_id') != recording_id or type(event.get('sequence')) is not int or event['sequence'] != index:
                raise Play2CodeError('event sequence or identity mismatch')
            if not isinstance(event.get('type'), str):
                raise Play2CodeError('event type missing')
            monotonic = event.get('monotonic_ns')
            if type(monotonic) is not int or monotonic < prior_monotonic:
                raise Play2CodeError('event monotonic time is invalid')
            prior_monotonic = monotonic
            events.append(event)
            index += 1
    if not events or events[0].get('type') != 'recording_start' or events[-1].get('type') != 'recording_stop':
        raise Play2CodeError('timeline must be bracketed by start/stop')
    if type(capture.get('event_count')) is not int or capture['event_count'] != len(events):
        raise Play2CodeError('capture event count mismatch')
    start, stop = events[0], events[-1]
    stop_requests = [event for event in events if event['type'] == 'recording_stop_requested']
    if len(stop_requests) != 1:
        raise Play2CodeError('recording lifecycle requires one local stop request')
    if (start.get('profile') != CAPTURE_PROFILE or start.get('source') != 'local_human_input' or
            start.get('control_endpoint_running') is not False or stop.get('status') != 'completed' or
            stop.get('reason') != 'user_requested' or stop.get('requested') is not True):
        raise Play2CodeError('recording endpoint/lifecycle proof is incomplete')
    if (start.get('actor_session') != actor_session or stop.get('actor_session') != actor_session or
            start.get('player_uuid') != player_uuid or start.get('dimension') != dimension):
        raise Play2CodeError('capture identity changed during recording')
    origin_position = _vector(capture.get('origin_position_absolute'), 'origin player position')
    origin_block = _vector(capture.get('origin_block_absolute'), 'origin block position', integers=True)
    if (_vector(start.get('origin_position_absolute'), 'start origin player position') != origin_position or
            _vector(start.get('origin_block_absolute'), 'start origin block position', integers=True) != origin_block):
        raise Play2CodeError('capture origin changed between metadata and timeline')
    for event in events:
        if event['type'] == 'tick':
            owned = event.get('remote_owned_inputs')
            if owned != []:
                raise Play2CodeError('remote-owned input appears in timeline')
            if event.get('actor_session') != capture.get('actor_session'):
                raise Play2CodeError('tick actor session mismatch')
    return Recording(directory, capture, tuple(events), timeline)


def _number(value: int | float) -> str:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise Play2CodeError('nonfinite BCL coordinate')
    if value == 0:
        return '0'
    return format(value, '.12g')


def _unsupported(sequence, event_type, reason, **details):
    return {'source_sequence': sequence, 'source_type': event_type, 'reason': reason, 'details': details}


def _line_is_valid(line: str, registry) -> tuple[bool, dict | None]:
    try:
        compile_bcl('BCL/1\n' + line + '\n', registry)
        return True, None
    except BCLError as error:
        return False, error.diagnostic.to_dict()


def _group_is_valid(lines: list[str], registry) -> tuple[bool, dict | None]:
    try:
        compile_bcl('BCL/1\n' + '\n'.join(lines) + '\n', registry)
        return True, None
    except BCLError as error:
        return False, error.diagnostic.to_dict()


def _resource_from_intent(intent: dict[str, Any]) -> str | None:
    held = intent.get('held')
    if not isinstance(held, dict):
        return None
    if held.get('empty') is True:
        return 'minecraft:air'
    item = held.get('item')
    return item if isinstance(item, str) else None


def _placement_candidates(intent: dict[str, Any]) -> dict[tuple[int, int, int], str]:
    candidates = intent.get('candidates')
    if not isinstance(candidates, list):
        raise Play2CodeError('placement intent candidates are malformed')
    result = {}
    for candidate in candidates:
        if not isinstance(candidate, dict) or not isinstance(candidate.get('before_block'), str):
            raise Play2CodeError('placement intent candidate is malformed')
        position = _vector(candidate.get('position_absolute'), 'placement candidate position', integers=True)
        if position in result:
            raise Play2CodeError('placement intent contains duplicate candidates')
        result[position] = candidate['before_block']
    return result


def _convert(recording: Recording, registry):
    events = recording.events
    by_sequence = {event['sequence']: event for event in events}
    confirmed_by_intent = {}
    unsupported = []
    groups = []

    previous_position = _vector(recording.capture['origin_position_absolute'], 'origin player position')
    previous_active = False
    airborne_sequences = []
    uncommanded_sequences = []
    for event in events:
        if event['type'] != 'tick':
            continue
        position = _vector(event.get('position_absolute'), 'tick position')
        inputs = event.get('inputs')
        if not isinstance(inputs, dict) or any(type(inputs.get(key, False)) is not bool for key in MOVEMENT_KEYS):
            raise Play2CodeError('tick inputs must be strict booleans')
        active = any(inputs.get(key, False) for key in MOTION_KEYS)
        changed = previous_position is not None and math.dist(position, previous_position) > .005
        if changed and (active or previous_active):
            if event.get('on_ground') is True:
                mode = 'sneak' if event.get('sneaking') is True or inputs.get('sneak') else 'fast' if event.get('sprinting') is True or inputs.get('sprint') else 'normal'
                line = f'M0 X{_number(position[0])} Y{_number(position[1])} Z{_number(position[2])} F{mode}'
                valid, diagnostic = _line_is_valid(line, registry)
                if valid:
                    groups.append({'order': event['sequence'], 'source_sequence': event['sequence'],
                                   'source_type': 'tick', 'kind': 'movement_checkpoint', 'lines': [line]})
                else:
                    unsupported.append(_unsupported(event['sequence'], 'tick', 'movement_checkpoint_rejected_by_registry', diagnostic=diagnostic))
            else:
                airborne_sequences.append(event['sequence'])
        elif changed and not active and not previous_active:
            uncommanded_sequences.append(event['sequence'])
        previous_position, previous_active = position, active

    for event in events:
        if event['type'] not in {'block_placed', 'block_broken', 'block_changed'}:
            continue
        intent_sequence = event.get('intent_sequence')
        if type(intent_sequence) is not int or intent_sequence not in by_sequence or intent_sequence >= event['sequence']:
            raise Play2CodeError('confirmed mutation lacks an earlier intent')
        if intent_sequence in confirmed_by_intent:
            raise Play2CodeError('one intent produced multiple confirmed mutations')
        confirmed_by_intent[intent_sequence] = event
        intent = by_sequence[intent_sequence]
        if event.get('source') != 'local_human_input' or intent.get('source') != 'local_human_input':
            unsupported.append(_unsupported(event['sequence'], event['type'], 'mutation_source_not_local_human'))
            continue
        stable = event.get('confirmed_stable_ticks')
        stable_match = STABLE_PATTERN.fullmatch(str(event.get('confirmation', '')))
        if type(stable) is not int or stable < 3 or stable_match is None or int(stable_match.group(1)) != stable:
            unsupported.append(_unsupported(event['sequence'], event['type'], 'mutation_not_stably_confirmed'))
            continue
        position = _vector(event.get('position_absolute'), 'mutation position', integers=True)
        if event['type'] == 'block_changed':
            unsupported.append(_unsupported(event['sequence'], event['type'], 'confirmed_change_has_no_conservative_BCL_mapping',
                                                before=event.get('before_block'), after=event.get('after_block')))
            continue
        event_item = event.get('held_item')
        intent_item = _resource_from_intent(intent)
        if not isinstance(event_item, str) or not isinstance(intent_item, str) or event_item != intent_item:
            unsupported.append(_unsupported(event['sequence'], event['type'], 'held_item_evidence_missing_or_mismatched',
                                                event_item=event_item, intent_item=intent_item))
            continue
        if event['type'] == 'block_placed':
            if intent.get('type') != 'use_on_block' or event.get('hand') != 'main_hand' or intent.get('hand') != 'main_hand':
                unsupported.append(_unsupported(event['sequence'], event['type'], 'only_confirmed_main_hand_block_use_maps_to_I4'))
                continue
            block = event.get('after_block')
            if (not isinstance(block, str) or block != event.get('expected_block') or
                    block != intent.get('expected_placed_block')):
                unsupported.append(_unsupported(event['sequence'], event['type'], 'placed_block_does_not_match_recorded_block_item'))
                continue
            candidates = _placement_candidates(intent)
            if position not in candidates:
                unsupported.append(_unsupported(event['sequence'], event['type'], 'placement_position_not_watched_by_native_intent'))
                continue
            if not isinstance(event.get('before_block'), str) or event['before_block'] != candidates[position]:
                unsupported.append(_unsupported(event['sequence'], event['type'], 'placement_precondition_does_not_match_native_intent'))
                continue
            if event_item == 'minecraft:air':
                unsupported.append(_unsupported(event['sequence'], event['type'], 'placed_item_evidence_missing_or_empty'))
                continue
            action = f'I4 B={block} P={json.dumps(list(position), separators=(",", ":"))} C=false'
            groups.append({'order': intent_sequence, 'source_sequence': event['sequence'], 'intent_sequence': intent_sequence,
                           'source_type': event['type'], 'kind': 'confirmed_placement', 'equip': event_item, 'lines': [action]})
        else:
            if (intent.get('type') != 'break_intent' or event.get('hand') != 'main_hand' or
                    intent.get('hand') != 'main_hand'):
                unsupported.append(_unsupported(event['sequence'], event['type'], 'confirmed_break_lacks_native_main_hand_intent'))
                continue
            target = _vector(intent.get('target_position_absolute'), 'break intent target', integers=True)
            if target != position:
                unsupported.append(_unsupported(event['sequence'], event['type'], 'break_position_does_not_match_native_intent'))
                continue
            block = event.get('before_block')
            if not isinstance(block, str) or block != intent.get('before_block'):
                unsupported.append(_unsupported(event['sequence'], event['type'], 'break_precondition_does_not_match_native_intent'))
                continue
            if event.get('after_block') not in AIR_BLOCKS:
                unsupported.append(_unsupported(event['sequence'], event['type'], 'confirmed_break_did_not_end_in_air'))
                continue
            action = f'C3 B={block} P={json.dumps(list(position), separators=(",", ":"))} D=false'
            groups.append({'order': intent_sequence, 'source_sequence': event['sequence'], 'intent_sequence': intent_sequence,
                           'source_type': event['type'], 'kind': 'confirmed_break',
                           'equip': None if event_item == 'minecraft:air' else event_item, 'lines': [action]})

    for event in events:
        if event['type'] in {'use_on_block', 'break_intent'} and event['sequence'] not in confirmed_by_intent:
            unsupported.append(_unsupported(event['sequence'], event['type'], 'no_confirmed_world_mutation'))
        elif event['type'] == 'interaction_unsupported':
            unsupported.append(_unsupported(event['sequence'], event['type'], str(event.get('reason', 'unsupported_native_interaction')),
                                                intent_sequence=event.get('intent_sequence')))
        elif event['type'] == 'hotbar_selected':
            unsupported.append(_unsupported(event['sequence'], event['type'], 'exact_hotbar_slot_selection_has_no_BCL_opcode',
                                                selected_slot=event.get('to')))

    def interval_rows(sequences, reason):
        if not sequences:
            return
        start = previous = sequences[0]
        for sequence in sequences[1:] + [None]:
            if sequence is not None and sequence == previous + 1:
                previous = sequence
                continue
            unsupported.append(_unsupported(start, 'tick_interval', reason, first_sequence=start, last_sequence=previous,
                                                sample_count=previous-start+1))
            if sequence is not None:
                start = previous = sequence
    interval_rows(airborne_sequences, 'airborne_movement_has_no_safe_M0_checkpoint')
    interval_rows(uncommanded_sequences, 'motion_without_recorded_movement_input_not_replayed')

    groups.sort(key=lambda row: (row['order'], 0 if row['kind'] != 'movement_checkpoint' else 1, row['source_sequence']))
    operations = []
    emitted_groups = []
    equipped = None
    for group in groups:
        lines = list(group['lines'])
        equip = group.get('equip')
        if equip and equip != equipped:
            lines.insert(0, f'I1 I={equip}')
        valid, diagnostic = _group_is_valid(lines, registry)
        if not valid:
            unsupported.append(_unsupported(group['source_sequence'], group['source_type'], 'conversion_rejected_by_installed_registry',
                                                diagnostic=diagnostic, proposed_lines=lines))
            continue
        converted = []
        for line in lines:
            kind = 'equip_for_confirmed_action' if line.startswith('I1 ') else group['kind']
            operation = {'source_sequence': group['source_sequence'], 'source_type': group['source_type'],
                         'kind': kind, 'bcl': line}
            if 'intent_sequence' in group:
                operation['intent_sequence'] = group['intent_sequence']
            operations.append(operation);converted.append(operation)
        emitted_groups.append(converted)
        if equip:
            equipped = equip

    batches = []
    current = []
    for group in emitted_groups:
        if len(group) > BATCH_PAYLOAD_LIMIT:
            raise AssertionError('conversion group exceeds one BCL batch')
        if current and len(current) + len(group) > BATCH_PAYLOAD_LIMIT:
            batches.append(current);current = []
        current.extend(group)
    if current:
        batches.append(current)
    compiled = []
    for index, payload in enumerate(batches, 1):
        source = '\n'.join((*BATCH_PREFIX, *(row['bcl'] for row in payload))) + '\n'
        program = compile_bcl(source, registry)
        filename = f'{index:04d}.bcl'
        for line_number, operation in enumerate(payload, len(BATCH_PREFIX) + 1):
            operation['batch'] = filename;operation['line'] = line_number
        compiled.append({'file': filename, 'source': source, 'payload_operations': len(payload),
                         'compiled_operations': len(program.operations), 'program_digest': program.digest,
                         'registry_digest': program.registry_digest,
                         'source_sha256': hashlib.sha256(source.encode()).hexdigest()})
    unsupported.sort(key=lambda row: (row['source_sequence'], row['reason']))
    return operations, unsupported, compiled


def _private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=False)
    if os.name == 'posix':
        path.chmod(0o700)


def _atomic_write(path: Path, data: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise Play2CodeError(f'refusing to overwrite {path.name}')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.partial', dir=path.parent)
    temporary = Path(temporary_name)
    try:
        if os.name == 'posix':
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name == 'posix':
            path.chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def _json_bytes(value) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_recording(directory: str | Path, *, output_root: str | Path | None = None,
                     benchmark: str | None = None) -> dict[str, Any]:
    if benchmark not in {None, 'superflat_house_5x5'}:
        raise Play2CodeError('unknown benchmark identity')
    recording = load_recording(directory)
    registry = default_commands()
    operations, unsupported, batches = _convert(recording, registry)
    source = recording.directory
    if output_root is None:
        target = source
        for name in ('manifest.json', 'manifest.sha256', 'conversion.json', 'bcl'):
            if (target / name).exists() or (target / name).is_symlink():
                raise Play2CodeError('recording was already exported or has conflicting artifacts')
    else:
        output_root = Path(output_root)
        if output_root.is_symlink():
            raise Play2CodeError('output root may not be a symlink')
        output_root.mkdir(parents=True, exist_ok=True)
        if os.name == 'posix':
            output_root.chmod(0o700)
        target = output_root / recording.recording_id
        _private_directory(target)
        for name in ('capture.json', 'raw-timeline.jsonl'):
            destination = target / name
            shutil.copyfile(source / name, destination, follow_symlinks=False)
            if os.name == 'posix':
                destination.chmod(0o600)

    bcl_directory = target / 'bcl'
    _private_directory(bcl_directory)
    for batch in batches:
        _atomic_write(bcl_directory / batch['file'], batch['source'].encode())
    conversion = {
        'schema': CONVERSION_SCHEMA,
        'recording_id': recording.recording_id,
        'policy': {
            'path_smoothing': False,
            'action_optimization': False,
            'movement': 'Every changed grounded end-tick position with active or just-released local movement input becomes an ordered absolute M0 checkpoint.',
            'placement': 'Only a stably confirmed main-hand block mutation becomes I4; C=false forbids extra plant-clearing effects.',
            'mining': 'Only a stably confirmed air postcondition becomes exact C3. Drops are not claimed.',
            'equipment': 'I1 is emitted only when a confirmed mapped action requires a different recorded held item.',
        },
        'generated_operations': operations,
        'unsupported_conversions': unsupported,
        'limitations': [
            'BCL/1 has no raw key-timing, yaw/pitch, mouse-button, jump-arc, or exact hotbar-slot replay opcode.',
            'M0 replays ordered position goals through the existing guarded walker; it does not reproduce native input timing or camera trajectory.',
            'Airborne and uncommanded motion remain raw evidence and are not converted into optimistic movement commands.',
            'Compilation is static validation only. No replay outcome is claimed.',
        ],
    }
    _atomic_write(target / 'conversion.json', _json_bytes(conversion))

    artifacts = ['capture.json', 'raw-timeline.jsonl', 'conversion.json'] + [f"bcl/{batch['file']}" for batch in batches]
    event_counts = Counter(event['type'] for event in recording.events)
    origin_player = recording.capture['origin_position_absolute']
    origin_block = recording.capture['origin_block_absolute']
    benchmark_record = None
    if benchmark is not None:
        benchmark_record = {
            'id': benchmark,
            'human_capture_status': 'RECORDED',
            'independent_world_acceptance': 'PENDING',
            'replay_status': 'PENDING',
            'note': 'The owner must perform the manual build. Export alone is not benchmark acceptance.',
        }
    manifest = {
        'schema': MANIFEST_SCHEMA,
        'recording_id': recording.recording_id,
        'profile': recording.capture.get('profile'),
        'capture_status': 'completed',
        'source': 'local_human_input',
        'player': {'uuid': recording.capture.get('player_uuid'), 'dimension': recording.capture.get('dimension'),
                   'actor_session': recording.capture.get('actor_session')},
        'timing': {'started_at_ms': recording.capture.get('started_at_ms'), 'ended_at_ms': recording.capture.get('ended_at_ms'),
                   'duration_ns': recording.capture.get('duration_ns'), 'native_tick_samples': event_counts['tick']},
        'coordinate_contract': {
            'absolute': 'Player positions are native feet coordinates; block positions are integer world voxels.',
            'relative': 'Player deltas use the exact start position. Block deltas use the floored start block.',
            'origin_position_absolute': origin_player,
            'origin_block_absolute': origin_block,
            'bcl_coordinate_mode': 'absolute',
        },
        'remote_control': {**recording.capture['remote_control'], 'no_remote_controller_interference': True},
        'world_mutations': {'confirmed_placements': event_counts['block_placed'], 'confirmed_breaks': event_counts['block_broken'],
                            'other_confirmed_changes': event_counts['block_changed'],
                            'confirmation_scope': 'client-observed state stable for at least three end ticks; not server-authoritative proof'},
        'conversion': {'raw_events': len(recording.events), 'generated_payload_operations': len(operations),
                       'unsupported_conversion_records': len(unsupported), 'bcl_batches': len(batches),
                       'path_smoothing': False, 'action_optimization': False},
        'compiler_validation': [{key: batch[key] for key in ('file', 'payload_operations', 'compiled_operations', 'program_digest', 'registry_digest', 'source_sha256')}
                                for batch in batches],
        'replay': {'attempted': False, 'qualified': False, 'status': 'NOT_RUN',
                   'note': 'Generated BCL compiled successfully but has not been replayed.'},
        'benchmark': benchmark_record,
        'privacy': 'Raw recordings contain player identity and precise world locations. Keep private and out of distributable bundles unless explicitly reviewed.',
        'artifact_sha256': {name: _sha(target / name) for name in artifacts},
    }
    _atomic_write(target / 'manifest.json', _json_bytes(manifest))
    manifest_hash = _sha(target / 'manifest.json')
    _atomic_write(target / 'manifest.sha256', f'{manifest_hash}  manifest.json\n'.encode())
    return {**manifest, 'directory': str(target), 'manifest_sha256': manifest_hash}


def inspect_recording(directory: str | Path) -> dict[str, Any]:
    recording = load_recording(directory)
    counts = Counter(event['type'] for event in recording.events)
    return {'recording_id': recording.recording_id, 'status': recording.capture['status'],
            'events': len(recording.events), 'event_counts': dict(sorted(counts.items())),
            'no_remote_controller_interference': True, 'directory': str(recording.directory)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    inspect = sub.add_parser('inspect', help='Validate and summarize one sealed native recording')
    inspect.add_argument('recording', type=Path)
    export = sub.add_parser('export', help='Generate conservative compiling BCL batches and a hashed manifest')
    export.add_argument('recording', type=Path)
    export.add_argument('--output-root', type=Path, help='Copy into OUTPUT/recording-id instead of exporting in place')
    export.add_argument('--benchmark', choices=['superflat_house_5x5'])
    args = parser.parse_args(argv)
    value = inspect_recording(args.recording) if args.action == 'inspect' else export_recording(
        args.recording, output_root=args.output_root, benchmark=args.benchmark)
    print(json.dumps(value, indent=2, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
