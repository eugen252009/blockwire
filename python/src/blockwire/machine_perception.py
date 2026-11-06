"""Lossless, bounded presentation of existing observations; no world reads or plans."""
import math
import re
from types import SimpleNamespace
from .skills.distance import _observed, _vector

_ID = re.compile(r'[a-z0-9_.-]+:[a-z0-9_./-]+\Z')


def describe_scene(scene):
    """Expand already sampled surfaces for model consumers, not the native wire.

    No ranking, target/material selection, hidden cells, paths or reach claims.
    Original encoding, actor identity and sample timestamps remain unchanged.
    """
    if scene.get('visibility', {}).get('profile') != 'sampled_surfaces_v1':
        return dict(scene)
    eye = scene.get('eye_position')
    if not _vector(eye):
        raise ValueError('Finite observed eye position required')
    blocks = []
    for row in _observed(SimpleNamespace(check=lambda: None), scene):
        identifier, position = row['id'], row['position']
        if (len(identifier) > 128 or not _ID.fullmatch(identifier)
                or abs(position[0]) > 29_999_984 or abs(position[2]) > 29_999_984
                or not -2048 <= position[1] <= 2048):
            raise ValueError('Invalid sampled block identity/position')
        center = [v + .5 for v in position]
        distance = math.dist(eye, center)
        if not math.isfinite(distance) or distance > 66:
            raise ValueError('Block exceeds bounded native sight window')
        blocks.append({**row, 'center': center, 'eye_distance_to_center': round(distance, 3)})
    result = {**scene, 'observed_blocks': blocks,
              'interaction_target': scene.get('target'),
              'geometry_notes': (
                  'observed_blocks expands ONLY existing sampled surfaces, in source order, not ranked targets. '
                  'position is the integer voxel; center is its geometric world-space center, not a guaranteed visible hit point. '
                  'Distances do not prove interaction reach or a safe route. Missing cells remain unknown. '
                  'interaction_target is the cached native interaction hit (or null); sight_target is distant sight. '
                  'Snapshots and hits are partial/non-atomic; actions revalidate. turn rotates but never moves the player.')}
    yaw = scene.get('yaw')
    if type(yaw) in (int, float) and math.isfinite(yaw):
        result['yaw_normalized_degrees'] = (yaw + 180) % 360 - 180
    return result


def describe_events(snapshot):
    """Present a copy; never mutate cached events or advance their freshness."""
    result = {**snapshot, 'state': dict(snapshot.get('state', {}))}
    event = result['state'].get('state.scene')
    if event is not None:
        data = event['data']
        result['state']['state.scene'] = {**event, 'data': {**data, 'value': describe_scene(data['value'])}}
    return result
