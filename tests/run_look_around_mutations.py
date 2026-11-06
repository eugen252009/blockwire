#!/usr/bin/env python3
"""Isolated read-only perception mutations; no model or Minecraft connection."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ('cone', 'math.cos(math.radians(15))', 'math.cos(math.radians(30))', 'test_cone_window_distances_and_no_input_ownership'),
    ('x_window', 'abs(center[0]-anchor[0]) > 5', 'False', 'test_window_is_reticle_centred_not_player_centred'),
    ('z_window', 'abs(center[2]-anchor[2]) > 5', 'False', 'test_cone_window_distances_and_no_input_ownership'),
    ('cached_hit', "hit = scene.get('sight_target')", "hit = scene.get('target')", 'test_no_hit_never_uses_renderer_cache_or_invents_air_anchor'),
    ('yaw', '-math.sin(yaw)*math.cos(pitch)', 'math.sin(yaw)*math.cos(pitch)', 'test_pitch_yaw_and_wrapped_yaw'),
    ('pitch', '-math.sin(pitch)', 'math.sin(pitch)', 'test_pitch_yaw_and_wrapped_yaw'),
    ('ownership', 'controls_player=False', 'controls_player=True', 'test_cone_window_distances_and_no_input_ownership'),
]


def main():
    failures = []
    for name, before, after, test in CASES:
        with tempfile.TemporaryDirectory(prefix='blockwire-look-around-') as directory:
            path = Path(directory)
            shutil.copytree(ROOT/'python/src', path/'src', ignore=shutil.ignore_patterns('__pycache__'))
            file = path/'src/blockwire/skills/looking.py'
            source = file.read_text(); assert source.count(before) == 1, name
            mutated = source.replace(before, after); compile(mutated, str(file), 'exec'); file.write_text(mutated)
            env = {**os.environ, 'PYTHONPATH': str(path/'src')+os.pathsep+str(ROOT/'python/tests')}
            result = subprocess.run([sys.executable, '-m', 'unittest', 'test_look_around.LookAroundContracts.'+test],
                                    cwd=directory, env=env, capture_output=True, text=True, timeout=30)
            killed = result.returncode != 0 and 'FAIL: '+test in result.stderr
            print(name, 'KILLED' if killed else 'NOT_KILLED', flush=True)
            if not killed:
                failures.append(name); print(result.stdout+result.stderr)
    return bool(failures)


if __name__ == '__main__':sys.exit(main())
