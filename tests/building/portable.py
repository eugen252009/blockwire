"""Frozen portable Test-A fixture metadata; never a building language or controller."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

from blockwire.bcl import default_commands
from blockwire.bcl.compiler import arguments
from .program import frames
from .reference import House

FIXTURE_PATH = Path(__file__).parent / 'fixtures' / 'superflat-house-relative.bcl'
PORTABLE_SOURCE_SHA256 = '72e2368fb9861de72342d32b8a21825623e7dbabaf946348d786898f5d69c60b'
POINT_HOME = (2.5, -60.0, -3.5)
VOXEL_HOME = (2, -60, -4)
HOUSE_ORIGIN_LOCAL = (-2, 0, 4)
ORIGINS = {
    'A': (0, -60, 0),
    'B': (48, -60, 0),
    'C': (48, -60, 48),
}


def source() -> str:
    value = FIXTURE_PATH.read_text()
    if hashlib.sha256(value.encode()).hexdigest() != PORTABLE_SOURCE_SHA256:
        raise ValueError('Portable BCL fixture hash changed; start a new explicit qualification cohort')
    return value


def start_position(label: str) -> tuple[float, float, float]:
    origin = ORIGINS[label]
    return (origin[0] + POINT_HOME[0], POINT_HOME[1], origin[2] + POINT_HOME[2])


def expected_house(label: str) -> House:
    return House(origin=ORIGINS[label])


def house_from_home(home) -> House:
    if not isinstance(home, (list, tuple)) or len(home) != 3:
        raise ValueError('Three-axis captured home required')
    voxel = tuple(math.floor(float(value)) for value in home)
    return House(origin=tuple(voxel[index] + HOUSE_ORIGIN_LOCAL[index] for index in range(3)))


def frame_sources(*, split_home: bool = False) -> tuple[str, ...]:
    parts = tuple(part for part, _ in frames(source(), default_commands()))
    if not split_home:
        return parts
    lines = parts[0].splitlines()
    if lines[:2] != ['S0 sync', 'S1 relative']:
        raise ValueError('Portable fixture must begin with explicit synchronous S1 homing')
    body = '\n'.join(lines[2:])
    if not body:
        raise ValueError('Portable first body frame is empty')
    return (body, *parts[1:])


def resolved_coordinate_rows(home) -> list[dict]:
    """Evidence-only typed mapping; execution remains in the existing BCL runtime."""
    registry = default_commands()
    point = tuple(float(value) for value in home)
    voxel = tuple(math.floor(value) for value in point)
    axes = {'point_x': 0, 'point_y': 1, 'point_z': 2}
    rows = []
    for frame_index, (_, program) in enumerate(frames(source(), registry)):
        for operation_index, operation in enumerate(program.operations):
            command = registry.resolve(operation.namespace, operation.opcode)
            values = arguments(operation, command)
            mapped = {}
            for name, kind in command.coordinate_parameters:
                if name not in values or values[name] is None:
                    continue
                if kind == 'voxel':
                    mapped[name] = [int(values[name][axis]) + voxel[axis] for axis in range(3)]
                else:
                    mapped[name] = float(values[name]) + point[axes[kind]]
            if mapped:
                rows.append({'frame': frame_index, 'operation': operation_index,
                             'opcode': operation.opcode, 'coordinates': mapped})
    return rows


def local_placement_targets() -> dict[tuple[int, int, int], str]:
    registry = default_commands(); result = {}
    for _, program in frames(source(), registry):
        for operation in program.operations:
            if operation.opcode != 'I4':
                continue
            values = arguments(operation, registry.resolve(operation.namespace, operation.opcode))
            position = tuple(values['position'])
            if position in result:
                raise ValueError('Duplicate portable placement target')
            result[position] = values['block']
    return result
