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
RELATIVE_FIRST_BATCH_PREFIX = ('BCL/1', 'S0 sync', 'S1 relative', 'S3 stop')
RELATIVE_CONTINUATION_PREFIX = ('BCL/1', 'S0 sync', 'S3 stop')
MOVEMENT_KEYS = ('forward', 'back', 'left', 'right', 'jump', 'sneak', 'sprint')
MOTION_KEYS = ('forward', 'back', 'left', 'right', 'jump')
AIR_BLOCKS = frozenset({'minecraft:air', 'minecraft:cave_air', 'minecraft:void_air'})
PLACEMENT_FACES = {
    'up': ((0, 1, 0), (.5, 1., .5)),
    'down': ((0, -1, 0), (.5, 0., .5)),
    'north': ((0, 0, -1), (.5, .5, 0.)),
    'south': ((0, 0, 1), (.5, .5, 1.)),
    'east': ((1, 0, 0), (1., .5, .5)),
    'west': ((-1, 0, 0), (0., .5, .5)),
}
ID_PATTERN = re.compile(r"[0-9]{8}T[0-9]{6}\.[0-9]{3}Z-[0-9a-f]{8}")
STABLE_PATTERN = re.compile(r"client_world_state_stable_([0-9]+)_end_ticks")


class Play2CodeError(ValueError):
    pass


@dataclass(frozen=True)
class CoordinateTransform:
    """One explicit world-space lattice transform applied during offline export.

    Reflection is horizontal only. A voxel coordinate C maps to 2*C-v while
    continuous player/hit points reflect about the matching block-centre plane
    C+0.5. Positive quarter turns follow positive Minecraft yaw: clockwise on a
    north-up map viewed from above. Voxel rotations use an explicit anchor voxel;
    points rotate about that voxel's centre. Operations are mirror, rotate, then
    integer translation.
    """

    translation: tuple[int, int, int] = (0, 0, 0)
    mirror_axis: str | None = None
    mirror_coordinate: int | None = None
    rotation: int = 0
    rotation_anchor: tuple[int, int] | None = None

    def __post_init__(self):
        translation = self.translation
        if not isinstance(translation, (tuple, list)) or len(translation) != 3 or any(type(value) is not int for value in translation):
            raise Play2CodeError('coordinate translation must contain three strict integers')
        object.__setattr__(self, 'translation', tuple(translation))
        if self.mirror_axis not in {None, 'x', 'z'}:
            raise Play2CodeError('coordinate mirror axis must be x or z')
        if self.mirror_axis is None:
            if self.mirror_coordinate is not None:
                raise Play2CodeError('mirror coordinate requires a mirror axis')
        elif type(self.mirror_coordinate) is not int:
            raise Play2CodeError('mirror axis requires a strict integer voxel coordinate')
        if type(self.rotation) is not int or self.rotation not in {0, 90, 180, 270}:
            raise Play2CodeError('coordinate rotation must be one of 0, 90, 180 or 270 degrees')
        if self.rotation == 0:
            if self.rotation_anchor is not None:
                raise Play2CodeError('rotation anchor requires a nonzero rotation')
        else:
            anchor = self.rotation_anchor
            if (not isinstance(anchor, (tuple, list)) or len(anchor) != 2
                    or any(type(value) is not int for value in anchor)):
                raise Play2CodeError('nonzero rotation requires two strict integer anchor voxels')
            object.__setattr__(self, 'rotation_anchor', tuple(anchor))

    @property
    def identity(self) -> bool:
        return self.translation == (0, 0, 0) and self.mirror_axis is None and self.rotation == 0

    def _rotate_horizontal(self, x, z, anchor_x, anchor_z):
        dx, dz = x - anchor_x, z - anchor_z
        if self.rotation == 90:
            dx, dz = -dz, dx
        elif self.rotation == 180:
            dx, dz = -dx, -dz
        elif self.rotation == 270:
            dx, dz = dz, -dx
        return anchor_x + dx, anchor_z + dz

    def _orient_horizontal(self, x, z):
        if self.mirror_axis == 'x':
            x = -x
        elif self.mirror_axis == 'z':
            z = -z
        if self.rotation == 90:
            return -z, x
        if self.rotation == 180:
            return -x, -z
        if self.rotation == 270:
            return z, -x
        return x, z

    def point(self, value: tuple) -> tuple:
        if self.identity:
            return tuple(value)
        x, y, z = value
        if self.mirror_axis == 'x':
            x = 2 * self.mirror_coordinate + 1 - x
        elif self.mirror_axis == 'z':
            z = 2 * self.mirror_coordinate + 1 - z
        if self.rotation:
            anchor_x, anchor_z = self.rotation_anchor
            x, z = self._rotate_horizontal(x, z, anchor_x + .5, anchor_z + .5)
        return x + self.translation[0], y + self.translation[1], z + self.translation[2]

    def voxel(self, value: tuple) -> tuple:
        if self.identity:
            return tuple(value)
        x, y, z = value
        if self.mirror_axis == 'x':
            x = 2 * self.mirror_coordinate - x
        elif self.mirror_axis == 'z':
            z = 2 * self.mirror_coordinate - z
        if self.rotation:
            anchor_x, anchor_z = self.rotation_anchor
            x, z = self._rotate_horizontal(x, z, anchor_x, anchor_z)
        return x + self.translation[0], y + self.translation[1], z + self.translation[2]

    def yaw(self, value: int | float) -> int | float:
        if self.mirror_axis is None and self.rotation == 0:
            return value
        transformed = -value if self.mirror_axis == 'x' else 180 - value if self.mirror_axis == 'z' else value
        transformed = (transformed + self.rotation + 180) % 360 - 180
        return 0. if abs(transformed) < 5e-12 else transformed

    def face(self, value: str) -> str:
        if value not in PLACEMENT_FACES:
            raise Play2CodeError('placement face is invalid')
        if value in {'up', 'down'}:
            return value
        vectors = {'east': (1, 0), 'west': (-1, 0), 'south': (0, 1), 'north': (0, -1)}
        names = {vector: name for name, vector in vectors.items()}
        return names[self._orient_horizontal(*vectors[value])]

    def direction(self, value: str) -> str:
        values = {'forward', 'back', 'left', 'right', 'forward_left', 'forward_right',
                  'back_left', 'back_right', 'hold'}
        if value not in values:
            raise Play2CodeError('recorded movement direction is invalid')
        if self.mirror_axis is None:
            return value
        return {'left': 'right', 'right': 'left',
                'forward_left': 'forward_right', 'forward_right': 'forward_left',
                'back_left': 'back_right', 'back_right': 'back_left'}.get(value, value)

    def to_dict(self) -> dict[str, Any]:
        mirror = None if self.mirror_axis is None else {
            'axis': self.mirror_axis,
            'voxel_coordinate': self.mirror_coordinate,
            'continuous_plane': self.mirror_coordinate + .5,
        }
        result = {
            'order': 'mirror_then_translate',
            'translation': list(self.translation),
            'mirror': mirror,
            'point_home_transformed': False,
            'voxel_home_transformed': False,
            'lateral_recorded_controls_swapped': self.mirror_axis is not None,
        }
        if self.rotation:
            anchor_x, anchor_z = self.rotation_anchor
            result['order'] = 'mirror_then_rotate_then_translate'
            result['rotation'] = {
                'degrees': self.rotation,
                'direction': 'positive_minecraft_yaw_clockwise_on_north_up_map',
                'voxel_anchor': [anchor_x, anchor_z],
                'continuous_anchor': [anchor_x + .5, anchor_z + .5],
            }
        return result


IDENTITY_TRANSFORM = CoordinateTransform()


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


def _point_coordinates(event: dict[str, Any], origin: tuple, coordinate_mode: str, label: str,
                       transform: CoordinateTransform = IDENTITY_TRANSFORM):
    absolute = _vector(event.get('position_absolute'), f'{label} absolute position')
    if coordinate_mode == 'relative':
        recorded = _vector(event.get('position_relative'), f'{label} relative position')
        expected = tuple(absolute[index] - origin[index] for index in range(3))
        if any(not math.isclose(recorded[index], expected[index], rel_tol=1e-12, abs_tol=1e-9)
               for index in range(3)):
            raise Play2CodeError(f'{label} relative point coordinate does not match capture origin')
    transformed = transform.point(absolute)
    return transformed if coordinate_mode == 'absolute' else tuple(
        transformed[index] - origin[index] for index in range(3))


def _voxel_coordinates(event: dict[str, Any], origin: tuple, coordinate_mode: str, label: str,
                       transform: CoordinateTransform = IDENTITY_TRANSFORM):
    absolute = _vector(event.get('position_absolute'), f'{label} absolute position', integers=True)
    if coordinate_mode == 'relative':
        recorded = _vector(event.get('position_relative'), f'{label} relative position', integers=True)
        expected = tuple(absolute[index] - origin[index] for index in range(3))
        if recorded != expected:
            raise Play2CodeError(f'{label} relative voxel coordinate does not match capture origin')
    transformed = transform.voxel(absolute)
    return transformed if coordinate_mode == 'absolute' else tuple(
        transformed[index] - origin[index] for index in range(3))


def _batch_prefix(coordinate_mode: str, index: int):
    if coordinate_mode == 'absolute':
        return BATCH_PREFIX
    return RELATIVE_FIRST_BATCH_PREFIX if index == 0 else RELATIVE_CONTINUATION_PREFIX


def _batch_payload_limit(coordinate_mode: str, index: int) -> int:
    if coordinate_mode == 'absolute':
        return BATCH_PAYLOAD_LIMIT
    return 32 - (len(_batch_prefix(coordinate_mode, index)) - 1)


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
    if origin_block != tuple(math.floor(value) for value in origin_position):
        raise Play2CodeError('capture point and voxel origins are inconsistent')
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
    if abs(value) < 5e-12:
        return '0'
    return format(value, '.12g')


def _point_array(value) -> str:
    return '[' + ','.join(_number(number) for number in value) + ']'


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


def _placement_support(intent: dict[str, Any], destination: tuple[int, int, int], point_origin: tuple,
                       voxel_origin: tuple, coordinate_mode: str, recorded_sneak: bool,
                       transform: CoordinateTransform):
    face = intent.get('face')
    if face not in PLACEMENT_FACES:
        raise Play2CodeError('placement intent face is invalid')
    if not isinstance(intent.get('target_block'), str):
        raise Play2CodeError('placement intent support block is invalid')
    support_absolute = _vector(intent.get('target_position_absolute'), 'placement support absolute position', integers=True)
    support_relative = _vector(intent.get('target_position_relative'), 'placement support relative position', integers=True)
    expected_relative = tuple(support_absolute[index] - voxel_origin[index] for index in range(3))
    if coordinate_mode == 'relative' and support_relative != expected_relative:
        raise Play2CodeError('placement support relative voxel coordinate does not match capture origin')
    offset, face_point = PLACEMENT_FACES[face]
    expected_destination = tuple(support_absolute[index] + offset[index] for index in range(3))
    if destination != expected_destination:
        return None
    player=_vector(intent.get('player_position_absolute'),'placement player position')
    yaw,pitch=intent.get('yaw'),intent.get('pitch')
    if type(yaw) not in (int,float) or type(pitch) not in (int,float) or not math.isfinite(yaw) or not math.isfinite(pitch):
        raise Play2CodeError('placement view evidence is malformed')
    eye=(player[0],player[1]+(1.27 if recorded_sneak else 1.62),player[2])
    yr,pr=math.radians(yaw),math.radians(pitch)
    direction=(-math.sin(yr)*math.cos(pr),-math.sin(pr),math.cos(yr)*math.cos(pr))
    axis={'east':0,'west':0,'up':1,'down':1,'south':2,'north':2}[face]
    side=1 if face in {'east','up','south'} else 0
    plane=support_absolute[axis]+side
    if abs(direction[axis])<1e-9:raise Play2CodeError('placement view is parallel to recorded support face')
    distance=(plane-eye[axis])/direction[axis]
    if not 0<distance<=4.5:raise Play2CodeError('placement view does not reach recorded support face')
    aim_absolute=[eye[index]+direction[index]*distance for index in range(3)];aim_absolute[axis]=float(plane)
    for index in range(3):
        if index==axis:continue
        low,high=support_absolute[index],support_absolute[index]+1
        if not low-1e-6<=aim_absolute[index]<=high+1e-6:
            raise Play2CodeError('placement view misses recorded support face')
        aim_absolute[index]=min(float(high),max(float(low),aim_absolute[index]))
    aim_absolute=transform.point(tuple(aim_absolute))
    transformed_support=transform.voxel(support_absolute)
    support = transformed_support if coordinate_mode == 'absolute' else tuple(
        transformed_support[index] - voxel_origin[index] for index in range(3))
    aim = aim_absolute if coordinate_mode == 'absolute' else tuple(
        aim_absolute[index] - point_origin[index] for index in range(3))
    return support, transform.face(face), aim


def _recorded_jump_place(intent: dict[str, Any], destination: tuple[int, int, int], point_origin: tuple,
                         coordinate_mode: str, by_sequence: dict[int, dict[str, Any]]) -> bool:
    if intent.get('face') != 'up':
        return False
    player = _vector(intent.get('player_position_absolute'), 'placement intent player position')
    if coordinate_mode == 'relative':
        recorded = _vector(intent.get('player_position_relative'), 'placement intent relative player position')
        expected = tuple(player[index] - point_origin[index] for index in range(3))
        if any(not math.isclose(recorded[index], expected[index], rel_tol=1e-12, abs_tol=1e-9)
               for index in range(3)):
            raise Play2CodeError('placement intent relative point coordinate does not match capture origin')
    ticks = [by_sequence[sequence] for sequence in range(max(0, intent['sequence'] - 20), intent['sequence'])
             if sequence in by_sequence and by_sequence[sequence].get('type') == 'tick']
    if not ticks:
        return False
    nearest = ticks[-1]
    nearest_position = _vector(nearest.get('position_absolute'), 'placement preceding tick position')
    if (math.dist(nearest_position, player) > 1e-6 or nearest.get('on_ground') is not False
            or math.floor(player[0]) != destination[0] or math.floor(player[2]) != destination[2]
            or player[1] < destination[1] + 1.1):
        return False
    recent_jump = False
    for tick in reversed(ticks):
        inputs = tick.get('inputs')
        if not isinstance(inputs, dict) or type(inputs.get('jump', False)) is not bool:
            raise Play2CodeError('placement jump evidence is malformed')
        recent_jump = recent_jump or inputs.get('jump', False)
        if tick.get('on_ground') is True:
            break
    return recent_jump


def _recorded_sneak(intent: dict[str, Any], by_sequence: dict[int, dict[str, Any]]) -> bool:
    player = _vector(intent.get('player_position_absolute'), 'placement intent player position')
    ticks = [by_sequence[sequence] for sequence in range(max(0, intent['sequence'] - 20), intent['sequence'])
             if sequence in by_sequence and by_sequence[sequence].get('type') == 'tick']
    if not ticks:
        return False
    nearest = ticks[-1]
    if math.dist(_vector(nearest.get('position_absolute'), 'placement preceding tick position'), player) > 1e-6:
        return False
    inputs = nearest.get('inputs')
    if not isinstance(inputs, dict) or type(inputs.get('sneak', False)) is not bool:
        raise Play2CodeError('placement sneak evidence is malformed')
    return inputs.get('sneak', False)


def _convert(recording: Recording, registry, coordinate_mode: str,
             coordinate_transform: CoordinateTransform = IDENTITY_TRANSFORM):
    if coordinate_mode not in {'absolute', 'relative'}:
        raise Play2CodeError('BCL coordinate mode must be absolute or relative')
    if not isinstance(coordinate_transform, CoordinateTransform):
        raise Play2CodeError('coordinate transform must be a CoordinateTransform')
    events = recording.events
    point_origin = _vector(recording.capture['origin_position_absolute'], 'origin player position')
    voxel_origin = _vector(recording.capture['origin_block_absolute'], 'origin block position', integers=True)
    by_sequence = {event['sequence']: event for event in events}
    confirmed_by_intent = {}
    unsupported = []
    groups = []

    previous_position = point_origin
    previous_active = False
    airborne_sequences = []
    uncommanded_sequences = []
    for event in events:
        if event['type'] != 'tick':
            continue
        absolute_position = _vector(event.get('position_absolute'), 'tick position')
        position = _point_coordinates(event, point_origin, coordinate_mode, 'tick', coordinate_transform)
        inputs = event.get('inputs')
        if not isinstance(inputs, dict) or any(type(inputs.get(key, False)) is not bool for key in MOVEMENT_KEYS):
            raise Play2CodeError('tick inputs must be strict booleans')
        active = any(inputs.get(key, False) for key in MOTION_KEYS)
        changed = previous_position is not None and math.dist(absolute_position, previous_position) > .005
        if changed and (active or previous_active):
            if event.get('on_ground') is True:
                mode = 'sneak' if event.get('sneaking') is True or inputs.get('sneak') else 'fast' if event.get('sprinting') is True or inputs.get('sprint') else 'normal'
                line = f'M0 X{_number(position[0])} Y{_number(position[1])} Z{_number(position[2])} F{mode}'
                directions=[key for key in ('forward','back','left','right') if inputs.get(key)]
                recorded_control=None
                if directions or (mode=='sneak' and inputs.get('sneak')):
                    yaw,pitch=event.get('yaw'),event.get('pitch')
                    if type(yaw) not in (int,float) or type(pitch) not in (int,float) or not math.isfinite(yaw) or not math.isfinite(pitch):
                        raise Play2CodeError('movement view evidence is malformed')
                    recorded_control=((yaw+180)%360-180,pitch,'_'.join(directions) if directions else 'hold')
                valid, diagnostic = _line_is_valid(line, registry)
                if valid:
                    groups.append({'order': event['sequence'], 'source_sequence': event['sequence'],
                                   'source_type': 'tick', 'kind': 'movement_checkpoint', 'lines': [line],
                                   'recorded_control':recorded_control})
                else:
                    unsupported.append(_unsupported(event['sequence'], 'tick', 'movement_checkpoint_rejected_by_registry', diagnostic=diagnostic))
            else:
                airborne_sequences.append(event['sequence'])
        elif changed and not active and not previous_active:
            uncommanded_sequences.append(event['sequence'])
        previous_position, previous_active = absolute_position, active

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
        output_position = _voxel_coordinates(event, voxel_origin, coordinate_mode, 'mutation', coordinate_transform)
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
                unsupported.append(_unsupported(event['sequence'], event['type'], 'only_confirmed_main_hand_block_use_maps_to_placement'))
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
            recorded_sneak = _recorded_sneak(intent, by_sequence)
            support = _placement_support(intent, position, point_origin, voxel_origin, coordinate_mode, recorded_sneak,
                                         coordinate_transform)
            if support is None:
                unsupported.append(_unsupported(event['sequence'], event['type'],
                                                'placement_position_does_not_match_recorded_support_face'))
                continue
            support_position, face, aim = support
            pose = _point_coordinates({'position_absolute': intent.get('player_position_absolute'),
                                       'position_relative': intent.get('player_position_relative')},
                                      point_origin, coordinate_mode, 'placement player pose', coordinate_transform)
            jump_place = _recorded_jump_place(intent, position, point_origin, coordinate_mode, by_sequence)
            view = f'V2 X{_number(aim[0])} Y{_number(aim[1])} Z{_number(aim[2])}'
            action = (f'I3 B={block} P={json.dumps(list(support_position), separators=(",", ":"))} '
                      f'F={face} A=true Q={_point_array(pose)} R={_point_array(aim)}'
                      + (' K=true' if recorded_sneak else '') + (' J=true' if jump_place else '') + ' C=false')
            groups.append({'order': intent_sequence, 'source_sequence': event['sequence'], 'intent_sequence': intent_sequence,
                           'source_type': event['type'], 'kind': 'confirmed_placement', 'equip': event_item,
                           'recorded_sneak': recorded_sneak, 'recorded_jump_place': jump_place,
                           'block': block, 'support': list(support_position), 'face': face, 'pose': pose, 'aim': aim,
                           'depleted_stack': event.get('held_count_after') == 0,
                           'lines': [view, action]})
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
            action = f'C3 B={block} P={json.dumps(list(output_position), separators=(",", ":"))} D=false'
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

    ticks=[event for event in events if event['type']=='tick'];mapped_drop_intervals=[]
    group_by_sequence={group['source_sequence']:group for group in groups if group['kind']=='movement_checkpoint'}
    for index,event in enumerate(ticks[:-1]):
        group=group_by_sequence.get(event['sequence']);control=None if group is None else group.get('recorded_control')
        inputs=event.get('inputs',{});next_tick=ticks[index+1]
        if (group is None or control is None or control[2] not in {'forward','back','left','right'}
                or event.get('on_ground') is not True or inputs.get('sneak') or inputs.get('jump')
                or next_tick.get('on_ground') is not False or next_tick.get('client_tick')!=event.get('client_tick')+1):
            continue
        landing_index=None
        for cursor in range(index+1,min(len(ticks),index+22)):
            if ticks[cursor].get('on_ground') is True:
                landing_index=cursor;break
        if landing_index is None:continue
        landing=ticks[landing_index];edge_position=_vector(event.get('position_absolute'),'recorded drop edge')
        landing_position=_vector(landing.get('position_absolute'),'recorded drop landing')
        height=edge_position[1]-landing_position[1]
        airborne=ticks[index+1:landing_index]
        if (not 2.<=height<=4. or math.hypot(edge_position[0]-landing_position[0],edge_position[2]-landing_position[2])>.75
                or any(any(row.get('inputs',{}).get(key,False) for key in MOTION_KEYS) for row in airborne)
                or any(row.get('health',event.get('health'))<event.get('health') for row in airborne+[landing])):
            continue
        edge=_point_coordinates(event,point_origin,coordinate_mode,'recorded drop edge',coordinate_transform)
        landed=_point_coordinates(landing,point_origin,coordinate_mode,'recorded drop landing',coordinate_transform)
        yaw,pitch,direction=control;output_yaw=coordinate_transform.yaw(yaw);output_direction=coordinate_transform.direction(direction)
        group.update(kind='recorded_drop',recorded_drop=True,recorded_control_replay=True,
                     source_sequences=[row['sequence'] for row in ticks[index:landing_index+1]],
                     lines=[f'M5 Q={_point_array(edge)} L={_point_array(landed)} H{_number(output_yaw)} P{_number(pitch)} B={output_direction}'])
        end=landing_index
        while end+1<len(ticks) and not any(ticks[end+1].get('inputs',{}).get(key,False) for key in MOTION_KEYS):end+=1
        mapped_drop_intervals.append((ticks[index+1]['sequence'],ticks[end]['sequence']))
    if mapped_drop_intervals:
        unsupported=[row for row in unsupported if not any(
            start<=row.get('details',{}).get('first_sequence',row['source_sequence'])
            and row.get('details',{}).get('last_sequence',row['source_sequence'])<=end
            for start,end in mapped_drop_intervals)]

    movement_groups=sorted((group for group in groups if group['kind']=='movement_checkpoint'),key=lambda row:row['order'])
    confirmed_positions=[(group['source_sequence'],tuple(by_sequence[group['source_sequence']]['position_absolute']))
                         for group in groups if group['kind']=='confirmed_placement']
    for current,nxt in zip(movement_groups,movement_groups[1:]):
        current_event,nxt_event=by_sequence[current['source_sequence']],by_sequence[nxt['source_sequence']]
        current_position=_vector(current_event.get('position_absolute'),'movement checkpoint position')
        next_position=_vector(nxt_event.get('position_absolute'),'next movement checkpoint position')
        current_cell=tuple(math.floor(value) for value in current_position)
        next_cell=tuple(math.floor(value) for value in next_position)
        support=(next_cell[0],next_cell[1]-1,next_cell[2])
        confirmed_before={position for sequence,position in confirmed_positions if sequence<nxt['source_sequence']}
        if (' Fsneak' in current['lines'][0] and current_cell!=next_cell
                and next_position[1]>point_origin[1]+.5 and support not in confirmed_before):
            current['lines'][0]+=' A=0.15'
            current['recorded_tight_arrival']=True

    lateral=[]
    for group in movement_groups:
        event=by_sequence[group['source_sequence']];position=_vector(event.get('position_absolute'),'movement checkpoint position')
        cell=tuple(math.floor(value) for value in position);support=(cell[0],cell[1]-1,cell[2])
        confirmed_before={placed for sequence,placed in confirmed_positions if sequence<group['source_sequence']}
        control=group.get('recorded_control')
        if (position[1]>point_origin[1]+.5 and support not in confirmed_before and control is not None
                and control[2] in {'left','right'}):
            lateral.append(group)
        else:lateral.append(None)
    selected=set()
    run=[]
    def select_rotating_lateral_run(rows):
        if not rows:return
        yaw=[rows[0]['recorded_control'][0]]
        for row in rows[1:]:yaw.append(yaw[-1]+((row['recorded_control'][0]-yaw[-1]+180)%360-180))
        if max(yaw)-min(yaw)>=35:
            selected.update(row['source_sequence'] for row in rows)
    previous=None
    for row in lateral+[None]:
        if row is not None and (previous is None or row['source_sequence']<=previous+2):
            run.append(row);previous=row['source_sequence'];continue
        select_rotating_lateral_run(run);run=[];previous=None
        if row is not None:run=[row];previous=row['source_sequence']
    for index,group in enumerate(movement_groups):
        if group['source_sequence'] not in selected:continue
        previous=group['source_sequence'];cursor=index+1
        while cursor<len(movement_groups):
            nxt=movement_groups[cursor];control=nxt.get('recorded_control')
            if nxt['source_sequence']>previous+2 or control is None or control[2]!='hold':break
            selected.add(nxt['source_sequence']);previous=nxt['source_sequence'];cursor+=1
    for group in movement_groups:
        if group['source_sequence'] in selected:group['recorded_control_replay']=True

    ordered=sorted(groups,key=lambda row:(row['order'],0 if row['kind']!='movement_checkpoint' else 1,row['source_sequence']))
    groups=[];index=0;direction_codes={'forward':0,'back':1,'left':2,'right':3,'forward_left':4,
                                     'forward_right':5,'back_left':6,'back_right':7,'hold':8}
    while index<len(ordered):
        group=ordered[index]
        if group['kind']=='movement_checkpoint' and group.get('recorded_control_replay'):
            candidate=[];cursor=index
            while cursor<len(ordered):
                row=ordered[cursor]
                if row['kind']=='movement_checkpoint' and row.get('recorded_control_replay'):
                    candidate.append(row);cursor+=1;continue
                if (row['kind']=='confirmed_placement' and row.get('recorded_sneak') and not row.get('recorded_jump_place')
                        and cursor+1<len(ordered) and ordered[cursor+1]['kind']=='movement_checkpoint'
                        and ordered[cursor+1].get('recorded_control_replay')):
                    candidate.append(row);cursor+=1;continue
                break
            placements=[row for row in candidate if row['kind']=='confirmed_placement']
            movement=[row for row in candidate if row['kind']=='movement_checkpoint']
            if (placements and len(movement)>=2 and len({row['block'] for row in placements})==1
                    and not any(row.get('depleted_stack') for row in placements[:-1])):
                events=[]
                for row in candidate:
                    if row['kind']=='movement_checkpoint':
                        event=by_sequence[row['source_sequence']]
                        point=_point_coordinates({'position_absolute':event.get('position_absolute'),
                                                  'position_relative':event.get('position_relative')},
                                                 point_origin,coordinate_mode,'recorded movement sample',coordinate_transform)
                        yaw,pitch,direction=row['recorded_control'];output_yaw=coordinate_transform.yaw(yaw)
                        output_direction=coordinate_transform.direction(direction)
                        events.append([0,*(json.loads(_number(value)) for value in point),
                                       json.loads(_number(output_yaw)),json.loads(_number(pitch)),direction_codes[output_direction]])
                    else:
                        face_code={'up':0,'down':1,'north':2,'south':3,'east':4,'west':5}[row['face']]
                        events.append([1,row['block'],*row['support'],face_code,
                                       *(json.loads(_number(value)) for value in row['pose']),
                                       *(json.loads(_number(value)) for value in row['aim'])])
                groups.append({'order':candidate[0]['order'],'source_sequence':candidate[-1]['source_sequence'],
                               'source_sequences':[row['source_sequence'] for row in movement],
                               'embedded_placement_sequences':[row['source_sequence'] for row in placements],
                               'source_type':'tick_interval','kind':'recorded_action_sequence','equip':placements[0]['block'],
                               'depleted_stack':placements[-1].get('depleted_stack',False),
                               'recorded_control_replay':True,
                               'lines':['M4 E='+json.dumps(json.dumps(events,separators=(',',':')))]})
                index=cursor;continue
            run=[]
            while index<len(ordered) and ordered[index]['kind']=='movement_checkpoint' and ordered[index].get('recorded_control_replay'):
                run.append(ordered[index]);index+=1
            if len(run)>=2:
                samples=[]
                for row in run:
                    event=by_sequence[row['source_sequence']]
                    point=_point_coordinates({'position_absolute':event.get('position_absolute'),
                                              'position_relative':event.get('position_relative')},
                                             point_origin,coordinate_mode,'recorded movement sample',coordinate_transform)
                    yaw,pitch,direction=row['recorded_control'];output_yaw=coordinate_transform.yaw(yaw)
                    output_direction=coordinate_transform.direction(direction)
                    samples.append([*(json.loads(_number(value)) for value in point),
                                    json.loads(_number(output_yaw)),json.loads(_number(pitch)),direction_codes[output_direction]])
                groups.append({'order':run[0]['order'],'source_sequence':run[-1]['source_sequence'],
                               'source_sequences':[row['source_sequence'] for row in run],
                               'source_type':'tick_interval','kind':'recorded_movement_path',
                               'recorded_control_replay':True,
                               'lines':['M3 T='+json.dumps(samples,separators=(',',':'))]})
            else:
                yaw,pitch,direction=run[0]['recorded_control'];output_yaw=coordinate_transform.yaw(yaw)
                output_direction=coordinate_transform.direction(direction)
                suffix=' A=0.15' if run[0]['lines'][0].endswith(' A=0.15') else ''
                if suffix:run[0]['lines'][0]=run[0]['lines'][0][:-len(suffix)]
                run[0]['lines'][0]+=(f' H{_number(output_yaw)} P{_number(pitch)} B={json.dumps(output_direction)}'+suffix)
                groups.extend(run)
            continue
        groups.append(group);index+=1
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
            kind = ('equip_for_confirmed_action' if line.startswith('I1 ') else
                    'aim_for_confirmed_placement' if group['kind'] == 'confirmed_placement' and line.startswith('V2 ') else
                    group['kind'])
            operation = {'source_sequence': group['source_sequence'], 'source_type': group['source_type'],
                         'kind': kind, 'bcl': line}
            if 'intent_sequence' in group:
                operation['intent_sequence'] = group['intent_sequence']
            if group.get('recorded_sneak') and line.startswith('I3 '):
                operation['recorded_sneak'] = True
            if group.get('recorded_jump_place') and line.startswith('I3 '):
                operation['recorded_jump_place'] = True
            if group.get('recorded_tight_arrival') and line.startswith('M0 '):
                operation['recorded_tight_arrival'] = True
            if group.get('recorded_control_replay') and line.startswith(('M0 ','M3 ','M4 ','M5 ')):
                operation['recorded_control_replay'] = True
            if 'source_sequences' in group and line.startswith(('M3 ','M4 ','M5 ')):
                operation['source_sequences']=group['source_sequences']
                operation['recorded_samples']=len(group['source_sequences'])
            if 'embedded_placement_sequences' in group and line.startswith('M4 '):
                operation['embedded_placement_sequences']=group['embedded_placement_sequences']
                operation['embedded_placements']=len(group['embedded_placement_sequences'])
            operations.append(operation);converted.append(operation)
        emitted_groups.append(converted)
        if equip:
            equipped = None if group.get('depleted_stack') else equip

    batches = []
    current = []
    for group in emitted_groups:
        index = len(batches)
        limit = _batch_payload_limit(coordinate_mode, index)
        if len(group) > limit:
            raise AssertionError('conversion group exceeds one BCL batch')
        if current and len(current) + len(group) > limit:
            batches.append(current);current = []
            index = len(batches);limit = _batch_payload_limit(coordinate_mode, index)
        current.extend(group)
    if current:
        batches.append(current)
    compiled = []
    for index, payload in enumerate(batches):
        prefix = _batch_prefix(coordinate_mode, index)
        source = '\n'.join((*prefix, *(row['bcl'] for row in payload))) + '\n'
        program = compile_bcl(source, registry)
        filename = f'{index + 1:04d}.bcl'
        for line_number, operation in enumerate(payload, len(prefix) + 1):
            operation['batch'] = filename;operation['line'] = line_number
        compiled.append({'file': filename, 'source': source, 'payload_operations': len(payload),
                         'compiled_operations': len(program.operations), 'program_digest': program.digest,
                         'registry_digest': program.registry_digest, 'coordinate_mode': coordinate_mode,
                         'captures_home': coordinate_mode == 'relative' and index == 0,
                         'requires_prior_home': coordinate_mode == 'relative' and index > 0,
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
                     benchmark: str | None = None, coordinate_mode: str = 'absolute',
                     coordinate_transform: CoordinateTransform | None = None) -> dict[str, Any]:
    if benchmark not in {None, 'superflat_house_5x5'}:
        raise Play2CodeError('unknown benchmark identity')
    if coordinate_mode not in {'absolute', 'relative'}:
        raise Play2CodeError('BCL coordinate mode must be absolute or relative')
    transform = IDENTITY_TRANSFORM if coordinate_transform is None else coordinate_transform
    if not isinstance(transform, CoordinateTransform):
        raise Play2CodeError('coordinate transform must be a CoordinateTransform')
    recording = load_recording(directory)
    registry = default_commands()
    operations, unsupported, batches = _convert(recording, registry, coordinate_mode, transform)
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
    policy = {
        'path_smoothing': False,
        'action_optimization': False,
        'coordinate_mode': coordinate_mode,
        'movement': f'Every changed grounded end-tick position with active or just-released local movement input becomes an ordered {coordinate_mode} M0 checkpoint.',
        'placement': ('Only a stably confirmed main-hand mutation with matching recorded support and face becomes a V2 face-centre aim '
                      'followed by exact I3 support/face placement. Q carries the validated recorded player pose; A=true reaches and revalidates that pose through native movement. '
                      'K=true preserves a matching recorded crouched placement stance; J=true is emitted only for a matching recorded airborne same-column jump placement; C=false forbids extra plant-clearing effects.'),
        'mining': 'Only a stably confirmed air postcondition becomes exact C3. Drops are not claimed.',
        'equipment': 'I1 is emitted only when a confirmed mapped action requires a different recorded held item.',
    }
    if not transform.identity:
        policy['coordinate_transform'] = transform.to_dict()
    conversion = {
        'schema': CONVERSION_SCHEMA,
        'recording_id': recording.recording_id,
        'policy': policy,
        'generated_operations': operations,
        'unsupported_conversions': unsupported,
        'limitations': [
            *([('The derived coordinate transform changes typed coordinates, horizontal yaw, placement faces and recorded directions; source evidence and action order remain unchanged.'
                if transform.rotation else
                'The derived coordinate transform changes only typed coordinates, horizontal yaw and placement faces; source evidence and action order remain unchanged.')]
              if not transform.identity else []),
            'BCL/1 has no raw key-timing, general yaw/pitch trajectory, mouse-button, jump-arc, or exact hotbar-slot replay opcode.',
            'For confirmed placements only, the recorded native support and face reconstruct one face-centre V2 target; the exact mouse ray is not claimed.',
            'M0 replays ordered position goals through the existing guarded walker; it does not reproduce native input timing.',
            'Airborne and uncommanded paths remain raw evidence and are not converted into M0. Only a confirmed same-column placement with matching airborne pose and recent recorded jump input may authorize bounded I3 J=true.',
            'Relative batches capture one S1 home in the first batch and require the same persisted BCL session for every continuation batch.' if coordinate_mode == 'relative' else
            'Absolute batches do not depend on a persisted S1 home.',
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
    coordinate_contract = {
        'absolute': 'Player positions are native feet coordinates; block positions are integer world voxels.',
        'relative': 'Player deltas use the exact start position. Block deltas use the floored start block.',
        'origin_position_absolute': origin_player,
        'origin_block_absolute': origin_block,
        'bcl_coordinate_mode': coordinate_mode,
    }
    if coordinate_mode == 'relative':
        coordinate_contract.update(
            home_capture='Exactly one S1 relative executes in the first batch.',
            continuation='Every later batch must execute in order in the same persisted BCL session without reset or re-homing.',
        )
    if not transform.identity:
        coordinate_contract['transform'] = transform.to_dict()
        coordinate_contract['transform_semantics'] = (
            'The recorded S1 point/voxel homes remain fixed. Source absolute evidence is mirrored, quarter-turned about the explicit block-centre anchor, '
            'then translated and expressed relative to those unchanged homes.' if transform.rotation else
            'The recorded S1 point/voxel homes remain fixed. Source absolute evidence is mirrored on the block lattice first, '
            'then translated, then expressed relative to those unchanged homes.'
        )
    conversion_record = {'raw_events': len(recording.events), 'generated_payload_operations': len(operations),
                         'unsupported_conversion_records': len(unsupported), 'bcl_batches': len(batches),
                         'coordinate_mode': coordinate_mode, 'path_smoothing': False, 'action_optimization': False,
                         'placement_support_reconstruction': 'recorded_native_support_face_center_v1'}
    if not transform.identity:
        conversion_record['coordinate_transform'] = transform.to_dict()
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
        'coordinate_contract': coordinate_contract,
        'remote_control': {**recording.capture['remote_control'], 'no_remote_controller_interference': True},
        'world_mutations': {'confirmed_placements': event_counts['block_placed'], 'confirmed_breaks': event_counts['block_broken'],
                            'other_confirmed_changes': event_counts['block_changed'],
                            'confirmation_scope': 'client-observed state stable for at least three end ticks; not server-authoritative proof'},
        'conversion': conversion_record,
        'compiler_validation': [{key: batch[key] for key in ('file', 'payload_operations', 'compiled_operations',
                                'program_digest', 'registry_digest', 'coordinate_mode', 'captures_home',
                                'requires_prior_home', 'source_sha256')} for batch in batches],
        'replay': {'attempted': False, 'qualified': False, 'status': 'NOT_RUN',
                   'note': 'Generated BCL compiled successfully but has not been replayed.'},
        'benchmark': benchmark_record,
        'privacy': 'Raw recordings contain player identity and precise world locations. Keep private and out of distributable bundles unless explicitly reviewed.',
        'artifact_sha256': {name: _sha(target / name) for name in artifacts},
    }
    if not transform.identity:
        manifest['derivation'] = {
            'classification': 'DERIVED_COORDINATE_TRANSFORM_NOT_NEW_HUMAN_RECORDING',
            'source_capture_preserved': True,
            'source_action_order_preserved': True,
            'coordinate_transform': transform.to_dict(),
        }
        if manifest['benchmark'] is not None:
            manifest['benchmark']['note'] = (
                'This is a derived coordinate-transformed program from the existing owner recording. '
                'It is not a new independent human baseline; replay and world acceptance remain pending.'
            )
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
    export.add_argument('--coordinate-mode', choices=['absolute', 'relative'], default='absolute',
                        help='Generate self-contained absolute batches (default) or one-home portable relative batches')
    export.add_argument('--translate', type=int, nargs=3, metavar=('X', 'Y', 'Z'), default=(0, 0, 0),
                        help='Apply one integer world translation after any mirror and rotation')
    export.add_argument('--mirror-axis', choices=['x', 'z'], help='Reflect typed coordinates across one horizontal block-lattice axis')
    export.add_argument('--mirror-coordinate', type=int,
                        help='Voxel coordinate C for v\'=2*C-v; continuous points reflect about C+0.5')
    export.add_argument('--rotation', type=int, choices=[0, 90, 180, 270], default=0,
                        help='Positive Minecraft-yaw quarter turn, clockwise on a north-up map')
    export.add_argument('--rotation-anchor', type=int, nargs=2, metavar=('X', 'Z'),
                        help='Explicit anchor voxel; points rotate about its block centre')
    args = parser.parse_args(argv)
    transform = None
    if args.action == 'export':
        transform = CoordinateTransform(
            translation=tuple(args.translate), mirror_axis=args.mirror_axis,
            mirror_coordinate=args.mirror_coordinate, rotation=args.rotation,
            rotation_anchor=None if args.rotation_anchor is None else tuple(args.rotation_anchor))
    value = inspect_recording(args.recording) if args.action == 'inspect' else export_recording(
        args.recording, output_root=args.output_root, benchmark=args.benchmark,
        coordinate_mode=args.coordinate_mode, coordinate_transform=transform)
    print(json.dumps(value, indent=2, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
