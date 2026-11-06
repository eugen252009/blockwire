"""Read-only reticle-centred report from bounded native sampled surfaces."""
import math
import re
from types import SimpleNamespace

from .core import SkillDefinition, SkillParameters, SkillResult, SkillStop
from .distance import _observed, _vector


class LookAround(SkillParameters):
    """Fixed 30-degree cone and 10-by-10-block horizontal window; no controls."""


def describe_look_around(scene, check=lambda: None):
    """Filter ONE supplied snapshot. Never invent coordinates or refresh a cache."""
    check()
    if not scene.get('in_world') or not scene.get('alive'):
        raise SkillStop('blocked', 'live_player_required')
    if scene.get('visibility', {}).get('profile') != 'sampled_surfaces_v1':
        raise SkillStop('blocked', 'visibility_observation_required')
    eye = scene.get('eye_position')
    yaw, pitch = scene.get('yaw'), scene.get('pitch')
    if (not _vector(eye) or any(type(v) not in (int, float) or not math.isfinite(v) for v in (yaw, pitch))
            or not -90 <= pitch <= 90):
        raise SkillStop('blocked', 'view_geometry_required')
    details = {'actor_session': scene.get('actor_session'), 'sampled_at_ms': scene.get('sampled_at_ms'),
               'partial_visibility': True, 'cone_degrees': 30, 'horizontal_window_blocks': [10, 10],
               'distance_reference': 'player_eye_to_block_center', 'blocks': [],
               'entities_status': 'unsupported: scene entities lack positions for this spatial filter',
               'unknown_cells': 'unknown, not air', 'interaction_reach_verified': False}
    # `target` is a cached renderer hit. Only the sampled forward ray anchors this report.
    hit = scene.get('sight_target')
    if not hit:
        return SkillResult(status='blocked', reason='crosshair_anchor_not_observed',
            text='No sampled forward block hit; the reticle has no observed world-space anchor.', details=details)
    anchor = hit.get('aim_position')
    position = hit.get('position')
    if (not _vector(anchor) or not _vector(position, integer=True)
            or any(not p-1e-6 <= a <= p+1+1e-6 for a, p in zip(anchor, position))
            or math.dist(eye, anchor) > 64.01):
        raise SkillStop('blocked', 'invalid_crosshair_anchor')
    details['anchor'] = {'position': list(anchor), 'block_position': list(position), 'source': 'sight_target'}
    yaw, pitch = math.radians(yaw % 360), math.radians(pitch)
    forward = [-math.sin(yaw)*math.cos(pitch), -math.sin(pitch), math.cos(yaw)*math.cos(pitch)]
    for row in _observed(SimpleNamespace(check=check), scene):
        check()
        identifier, voxel = row['id'], row['position']
        if (len(identifier) > 128 or not re.fullmatch(r'[a-z0-9_.-]+:[a-z0-9_./-]+', identifier)
                or abs(voxel[0]) > 29_999_984 or abs(voxel[2]) > 29_999_984 or not -2048 <= voxel[1] <= 2048):
            raise SkillStop('blocked', 'invalid_visibility_observation')
        center = [v+.5 for v in voxel]
        delta = [v-e for v, e in zip(center, eye)]
        distance = math.hypot(*delta)
        if not math.isfinite(distance) or distance > 66:
            raise SkillStop('blocked', 'invalid_visibility_observation')
        if distance == 0:
            continue  # No defined angular direction.
        cosine = sum(d*f for d, f in zip(delta, forward))/distance
        if (cosine < math.cos(math.radians(15)) - 1e-12
                or abs(center[0]-anchor[0]) > 5 or abs(center[2]-anchor[2]) > 5):
            continue
        details['blocks'].append({**row, 'center': center, 'distance_blocks': round(distance, 3),
                                  'angle_degrees': round(math.degrees(math.acos(max(-1., min(1., cosine)))), 3)})
    check()
    return SkillResult(status='succeeded', reason='view_reported',
        text='Sampled block centres in a 30-degree cone and a 10x10 X/Z window around the forward hit. '
             'Partial geometric visibility, not exact pixels, interaction reach or a complete map.', details=details)


def look_around(context, goal):
    context.check()
    scene = context.player.observe()
    context.check()
    return describe_look_around(scene, context.check)


LOOK_AROUND = SkillDefinition('look_around',
    'Read-only: report sampled blocks and distances in a 30-degree full cone (+/-15 degrees) '
    'around the crosshair, inside a 10x10-block horizontal X/Z window (+/-5) centred on the '
    'observed forward ray hit. No rotation, movement or hidden lookup. Missing forward hit '
    'returns unknown; entities cannot be spatially filtered by the current scene format.',
    LookAround, look_around, controls_player=False)
