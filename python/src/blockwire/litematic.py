"""Bounded, offline Litematica v6/v7 import. Schematic data is never executed.

This is deliberately independent of the privileged closed-save test readers.
Only gzip NBT, palettes and packed block states are accepted; entities, block
entities and scheduled ticks cannot silently disappear from a compiled build.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import re
import stat
import struct
import zlib

MAX_COMPRESSED = 8 * 1024 * 1024
MAX_NBT = 32 * 1024 * 1024
MAX_NODES = 1_000_000
MAX_DEPTH = 32
MAX_REGIONS = 32
MAX_SIDE = 64
MAX_VOLUME = 262_144
MAX_BLOCKS = 8192
MAX_PALETTE = 4096
ID = re.compile(r"[a-z0-9_.-]+:[a-z0-9_./-]+\Z")
PROPERTY = re.compile(r"[a-z0-9_]+\Z")
VALUE = re.compile(r"[a-z0-9_.-]+\Z")
AIR = frozenset({'minecraft:air', 'minecraft:cave_air', 'minecraft:void_air'})


class SchematicError(ValueError):
    """Invalid, unsupported or over-budget input; no gameplay has occurred."""


def require(condition, reason):
    if not condition:
        raise SchematicError(reason)


@dataclass(frozen=True)
class _Array:
    kind: int
    values: tuple | bytes


@dataclass(frozen=True)
class _List:
    kind: int
    values: tuple


class _NBT:
    def __init__(self, data):
        self.data, self.offset, self.nodes = data, 0, 0

    def take(self, size):
        require(0 <= size <= len(self.data) - self.offset, 'truncated_nbt')
        start = self.offset
        self.offset += size
        return self.data[start:self.offset]

    def number(self, fmt):
        return struct.unpack('>' + fmt, self.take(struct.calcsize('>' + fmt)))[0]

    def charge(self, count=1):
        require(0 <= count <= MAX_NODES - self.nodes, 'nbt_node_budget')
        self.nodes += count

    def string(self):
        raw = self.take(self.number('H'))
        try:
            # Java NBT uses modified UTF-8 (encoded NUL / surrogate pairs).
            # Accept ordinary UTF-8 producers too, but never lone surrogates.
            value = raw.replace(b'\xc0\x80', b'\0').decode('utf-8', 'surrogatepass')
            return value.encode('utf-16-be', 'surrogatepass').decode('utf-16-be')
        except UnicodeError as error:
            raise SchematicError('invalid_nbt_string') from error

    def payload(self, kind, depth=0):
        require(depth <= MAX_DEPTH, 'nbt_depth_budget')
        self.charge()
        if kind in (1, 2, 3, 4, 5, 6):
            value = self.number({1: 'b', 2: 'h', 3: 'i', 4: 'q', 5: 'f', 6: 'd'}[kind])
            require(not isinstance(value, float) or math.isfinite(value), 'nonfinite_nbt')
            return value
        if kind == 8:
            return self.string()
        if kind in (7, 11, 12):
            size = self.number('i')
            self.charge(size)
            width, fmt = {7: (1, 'b'), 11: (4, 'i'), 12: (8, 'q')}[kind]
            data = self.take(size * width)
            values = data if kind == 7 else tuple(v[0] for v in struct.iter_unpack('>' + fmt, data))
            return _Array(kind, values)
        if kind == 9:
            child, size = self.number('B'), self.number('i')
            require(0 <= size <= MAX_NODES - self.nodes, 'nbt_list_budget')
            require(0 <= child <= 12 and (child != 0 or size == 0), 'invalid_nbt_list_type')
            return _List(child, tuple(self.payload(child, depth + 1) for _ in range(size)))
        if kind == 10:
            values = {}
            while True:
                child = self.number('B')
                if child == 0:
                    return values
                name = self.string()
                require(name not in values, 'duplicate_nbt_key')
                values[name] = self.payload(child, depth + 1)
        raise SchematicError('unsupported_nbt_tag')

    def root(self):
        require(self.number('B') == 10, 'nbt_compound_root_required')
        self.string()  # Root label is data, not a path or instruction.
        value = self.payload(10)
        require(self.offset == len(self.data), 'trailing_nbt_data')
        return value


@dataclass(frozen=True)
class BlockState:
    name: str
    properties: tuple[tuple[str, str], ...] = ()

    def json(self):
        return {'id': self.name, 'properties': dict(self.properties)}


@dataclass(frozen=True)
class Voxel:
    position: tuple[int, int, int]
    state: BlockState


@dataclass(frozen=True)
class Schematic:
    sha256: str
    version: int
    data_version: int
    regions: int
    volume: int
    selection_min: tuple[int, int, int]
    selection_max: tuple[int, int, int]
    voxels: tuple[Voxel, ...]


def _integer(value):
    return type(value) is int


def _vector(value):
    require(type(value) is dict and set(value) == {'x', 'y', 'z'}, 'invalid_region_vector')
    result = tuple(value[key] for key in ('x', 'y', 'z'))
    require(all(_integer(n) and -(2**31) <= n < 2**31 for n in result), 'invalid_region_coordinate')
    return result


def _state(value):
    require(type(value) is dict and set(value) <= {'Name', 'Properties'}, 'invalid_palette_state')
    name, props = value.get('Name'), value.get('Properties', {})
    require(type(name) is str and len(name) <= 128 and ID.fullmatch(name), 'invalid_block_id')
    require(type(props) is dict and len(props) <= 32, 'invalid_block_properties')
    for key, item in props.items():
        require(type(key) is str and 1 <= len(key) <= 64 and PROPERTY.fullmatch(key), 'invalid_property_name')
        require(type(item) is str and 1 <= len(item) <= 64 and VALUE.fullmatch(item), 'invalid_property_value')
    require(name not in AIR or not props, 'air_properties_not_supported')
    return BlockState(name, tuple(sorted(props.items())))


def _empty_list(region, key):
    value = region.get(key, _List(0, ()))
    require(isinstance(value, _List), 'invalid_region_' + key)
    require(not value.values, 'unsupported_nonempty_' + key)


def decode_litematic(data: bytes) -> Schematic:
    """Decode one bounded gzip member. No files, network or Minecraft access."""
    require(type(data) is bytes and 0 < len(data) <= MAX_COMPRESSED, 'compressed_size_budget')
    try:
        decoder = zlib.decompressobj(31)
        raw = decoder.decompress(data, MAX_NBT + 1)
        require(len(raw) <= MAX_NBT and not decoder.unconsumed_tail, 'decompressed_size_budget')
        require(decoder.eof and not decoder.unused_data, 'incomplete_or_trailing_gzip')
    except zlib.error as error:
        raise SchematicError('invalid_gzip') from error
    root = _NBT(raw).root()
    require(_integer(root.get('Version')) and root['Version'] in (6, 7), 'unsupported_litematic_version')
    require('SubVersion' not in root or (_integer(root['SubVersion']) and root['SubVersion'] == 0),
            'unsupported_litematic_subversion')
    data_version = root.get('MinecraftDataVersion')
    require(_integer(data_version) and 0 < data_version < 2**31, 'invalid_minecraft_data_version')
    regions = root.get('Regions')
    require(type(regions) is dict and 1 <= len(regions) <= MAX_REGIONS, 'region_count_budget')
    boxes, voxels, volume = [], [], 0
    for region in regions.values():
        require(type(region) is dict, 'invalid_region')
        require(set(region) <= {'Position', 'Size', 'BlockStatePalette', 'BlockStates',
                               'Entities', 'TileEntities', 'PendingBlockTicks', 'PendingFluidTicks'},
                'unsupported_region_field')
        position, size = _vector(region.get('Position')), _vector(region.get('Size'))
        require(all(1 <= abs(n) <= MAX_SIDE for n in size), 'region_size_budget')
        extent = tuple(abs(n) for n in size)
        cells = math.prod(extent)
        volume += cells
        require(volume <= MAX_VOLUME, 'total_volume_budget')
        # Litematica stores packed positions from the MINIMUM corner, including
        # negative-size selections. Negative size does NOT reverse the bit order.
        lower = tuple(p + min(0, n + 1) for p, n in zip(position, size))
        upper = tuple(p + n - 1 for p, n in zip(lower, extent))
        for old_lower, old_upper in boxes:
            require(not all(lower[i] <= old_upper[i] and old_lower[i] <= upper[i] for i in range(3)),
                    'overlapping_regions_not_supported')
        boxes.append((lower, upper))
        span_min = tuple(min(box[0][i] for box in boxes) for i in range(3))
        span_max = tuple(max(box[1][i] for box in boxes) for i in range(3))
        require(all(b - a + 1 <= MAX_SIDE for a, b in zip(span_min, span_max)), 'enclosing_size_budget')
        for key in ('Entities', 'TileEntities', 'PendingBlockTicks', 'PendingFluidTicks'):
            _empty_list(region, key)
        palette_tag = region.get('BlockStatePalette')
        require(isinstance(palette_tag, _List) and palette_tag.kind == 10
                and 1 <= len(palette_tag.values) <= MAX_PALETTE, 'invalid_palette')
        palette = tuple(_state(value) for value in palette_tag.values)
        require(palette[0] == BlockState('minecraft:air'), 'palette_zero_must_be_air')
        words = region.get('BlockStates')
        require(isinstance(words, _Array) and words.kind == 12, 'packed_long_array_required')
        bits = max(2, (len(palette) - 1).bit_length())
        require(len(words.values) == (cells * bits + 63) // 64, 'packed_array_length_mismatch')
        unsigned = tuple(n & ((1 << 64) - 1) for n in words.values)
        for index in range(cells):
            word, shift = divmod(index * bits, 64)
            value = unsigned[word] >> shift
            if shift + bits > 64:
                value |= unsigned[word + 1] << (64 - shift)
            selected = value & ((1 << bits) - 1)
            require(selected < len(palette), 'palette_index_out_of_range')
            state = palette[selected]
            if state.name in AIR:
                continue
            x = index % extent[0]
            z = (index // extent[0]) % extent[2]
            y = index // (extent[0] * extent[2])
            voxels.append(Voxel(tuple(a + b for a, b in zip(lower, (x, y, z))), state))
            require(len(voxels) <= MAX_BLOCKS, 'block_count_budget')
    require(voxels, 'empty_schematic')
    # Metadata counts, labels, descriptions and author text are not trusted.
    return Schematic(hashlib.sha256(data).hexdigest(), root['Version'], data_version,
                     len(regions), volume, span_min, span_max,
                     tuple(sorted(voxels, key=lambda row: (row.position[1], row.position[2], row.position[0]))))


def load_litematic(path: str | Path) -> Schematic:
    """Read one explicitly selected regular file, not a directory scan or save."""
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    try:
        require(not Path(path).is_symlink(), 'schematic_symlink_not_allowed')
        with os.fdopen(os.open(path, flags), 'rb') as stream:
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode), 'regular_schematic_file_required')
            require(0 < info.st_size <= MAX_COMPRESSED, 'compressed_size_budget')
            data = stream.read(MAX_COMPRESSED + 1)
    except OSError as error:
        raise SchematicError('schematic_file_unavailable') from error
    return decode_litematic(data)
