"""Distance to current observed block surfaces only; no world lookup or controls."""
from __future__ import annotations

import math
from pydantic import Field, field_validator
from .core import SkillContext, SkillDefinition, SkillParameters, SkillResult, SkillStop

MAX_SAMPLED_BLOCKS = 337
MAX_CANDIDATES = 354  # Sampled blocks + 16 fresh interactables + fresh sight hit.


class EstimateDistance(SkillParameters):
    target: str = Field(default='minecraft:dirt', min_length=1, max_length=128,
        pattern=r'^(?:[a-z0-9_.-]+:)?[a-z0-9_./-]+$',
        description='Exact block ID. dirt means minecraft:dirt, not grass_block or a translated label.')
    position: list[int] | None = Field(default=None, min_length=3, max_length=3,
        description='Optional exact already-observed block position; filters one current snapshot, never queries this coordinate.')

    @field_validator('position')
    @classmethod
    def bounded_position(cls, value):
        if value is not None and (abs(value[0]) > 29_999_984 or not -2048 <= value[1] <= 2048 or abs(value[2]) > 29_999_984):
            raise ValueError('Block position outside supported world bounds')
        return value


def _vector(value, *, integer=False):
    return (isinstance(value, (list, tuple)) and len(value) == 3
            and all(type(v) is int if integer else type(v) in (int, float) and math.isfinite(v) for v in value))


def _observed(context, scene):
    found = {}
    def add(identifier, position, source):
        if not isinstance(identifier, str) or not _vector(position, integer=True):
            raise SkillStop('blocked', 'invalid_visibility_observation')
        key = tuple(position)
        if key in found and found[key]['id'] != identifier:
            raise SkillStop('blocked', 'inconsistent_visibility_observation')
        entry = found.setdefault(key, {'id': identifier, 'position': list(key), 'sources': []})
        if source not in entry['sources']:
            entry['sources'].append(source)
        if len(found) > MAX_CANDIDATES:
            raise SkillStop('blocked', 'visibility_budget_exceeded')

    # Deliberately DO NOT consume cached renderer `target`: it can be stale.
    hit = scene.get('sight_target')
    if hit:
        add(hit.get('id'), hit.get('position'), 'sight_target')
    rows = scene.get('visible_interactables', [])
    if not isinstance(rows, list) or len(rows) > 16:
        raise SkillStop('blocked', 'invalid_visibility_observation')
    for row in rows:
        context.check()
        add(row.get('id'), row.get('position'), 'visible_interactables')
    blocks = scene.get('visible_blocks')
    if blocks is not None:
        if (blocks.get('encoding') != 'palette_x_runs_v1'
                or not _vector(blocks.get('origin'), integer=True)):
            raise SkillStop('blocked', 'unsupported_surface_encoding')
        palette, origin, runs = blocks.get('palette'), blocks['origin'], blocks.get('runs')
        if not isinstance(palette, list) or not isinstance(runs, list) or len(runs) > MAX_SAMPLED_BLOCKS:
            raise SkillStop('blocked', 'invalid_visibility_observation')
        expanded = 0
        for run in runs:
            context.check()
            if not isinstance(run, list) or len(run) != 5 or any(type(v) is not int for v in run):
                raise SkillStop('blocked', 'invalid_visibility_observation')
            index, dx, dy, dz, length = run
            if not 0 <= index < len(palette) or length < 1:
                raise SkillStop('blocked', 'invalid_visibility_observation')
            expanded += length
            if expanded > MAX_SAMPLED_BLOCKS:
                raise SkillStop('blocked', 'visibility_budget_exceeded')
            for offset in range(length):
                add(palette[index], [origin[0]+dx+offset, origin[1]+dy, origin[2]+dz], 'visible_blocks')
    return list(found.values())


def estimate_distance(context: SkillContext, goal: EstimateDistance) -> SkillResult:
    context.check()
    scene = context.player.observe()  # ONE existing bounded observation; no coordinate RPC.
    context.check()
    if not scene.get('in_world') or not scene.get('alive'):
        raise SkillStop('blocked', 'live_player_required')
    if scene.get('visibility', {}).get('profile') != 'sampled_surfaces_v1':
        raise SkillStop('blocked', 'visibility_observation_required')
    feet, eye = scene.get('position'), scene.get('eye_position')
    if not _vector(feet) or not _vector(eye):
        raise SkillStop('blocked', 'player_position_required')
    identifier = goal.target if ':' in goal.target else 'minecraft:'+goal.target
    candidates = [row for row in _observed(context, scene) if row['id'] == identifier
                  and (goal.position is None or row['position'] == goal.position)]
    if not candidates:
        return SkillResult(status='blocked', reason='target_not_observed',
            text='Unknown: no matching block surface in the current bounded view. No hidden lookup was made.',
            details={'target_id': identifier, 'visibility': 'unknown', 'distance': None,
                     'landing_safety': 'unknown'})
    # These are distances to block centers, NOT invented exact ray hit points.
    selected = min(candidates, key=lambda row: (math.dist(eye, [v+.5 for v in row['position']]), row['position']))
    center = [v+.5 for v in selected['position']]
    horizontal = math.hypot(center[0]-feet[0], center[2]-feet[2])
    context.check()
    return SkillResult(status='succeeded', reason='distance_estimated',
        text='Measured an already observed block by its center. Landing safety remains unknown.',
        details={'target': selected, 'visibility': 'observed_in_current_snapshot',
                 'matching_observed_blocks': len(candidates), 'reference': 'observed_block_center',
                 'eye_distance_blocks': math.dist(eye, center),
                 'feet_distance_blocks': math.dist(feet, center),
                 'horizontal_distance_blocks': horizontal,
                 'vertical_delta_from_feet_blocks': center[1]-feet[1],
                 'landing_safety': 'unknown', 'clear_vertical_path': 'unknown',
                 'target_top_observed': 'unknown',
                 'actor_session': scene.get('actor_session'), 'sampled_at_ms': scene.get('sampled_at_ms'),
                 'partial_visibility': True})


ESTIMATE_DISTANCE = SkillDefinition('estimate_distance',
    'Read-only distance to the nearest currently observed block of an exact registry ID. Optional position '
    'only filters the same snapshot. No X-ray, camera changes, coordinate lookup, hidden terrain or cache. '
    'Report eye/feet/horizontal distance and height separately. No fall-damage or survival calculation; '
    'risk assessment belongs to the caller, and landing/path safety remains unknown.',
    EstimateDistance, estimate_distance, controls_player=False)
