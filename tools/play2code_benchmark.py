#!/usr/bin/env python3
"""Prepare (but never execute) the owner-only Play2Code 71-block house benchmark."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from building.reference import House

FIXTURE_IDENTITY = 'd61d166e4431e7693907cc0590f1808e2d8f12d62befe3b0a5a64c22b70696a7'
SCHEMA = 'blockwire.play2code.superflat-benchmark.v1'


def plan(run_id: str):
    if not re.fullmatch(r'H[0-9]{2,4}', run_id):
        raise ValueError('Human run ID must match HNN (for example H01)')
    house = House()
    return {
        'schema': SCHEMA,
        'run_id': run_id,
        'status': 'PENDING_OWNER_MANUAL_BUILD',
        'human_baseline_recorded': False,
        'recording_exported': False,
        'replay_attempted': False,
        'independent_acceptance_run': False,
        'fixture': {
            'id': 'blockwire-superflat-building-v1',
            'snapshot_identity': FIXTURE_IDENTITY,
            'minecraft': '26.3',
            'start_feet': [2.5, -60.0, -3.5],
        },
        'objective': {
            'reference_id': house.document()['id'],
            'reference_digest': house.digest(),
            'expected_blocks': len(house.blocks()),
            'walls': 46,
            'roof': 25,
            'origin': list(house.origin),
            'material': house.material,
            'reference_path': 'tests/building/fixtures/reference.json',
        },
        'required_execution': [
            'Restore and verify the canonical owned closed snapshot before the owner starts.',
            'Disable the Blockwire endpoint with F8; Play2Code refuses to start while it is enabled.',
            'The owner presses F9 and manually builds the complete house with ordinary keyboard/mouse input.',
            'The owner presses F10 and waits for the bounded mutation-confirmation drain.',
            'Export the sealed native recording with blockwire-play2code; generated BCL must compile.',
            'Restore a fresh canonical snapshot before any replay. Never replay in the human baseline world.',
            'Run the unchanged independent native/access plus closed-save acceptance after replay.',
        ],
        'prohibited_shortcuts': [
            'Test-A BCL/source or coordinate itinerary as human input',
            'LLM-generated build actions as the human baseline',
            'remote controller input during recording',
            'commands, teleport, creative/admin rescue, hidden generator, or manual artifact editing',
            'claiming compile success as replay or objective success',
        ],
        'note': 'Preparation creates metadata only. It does not restore/load a world, start recording, build, export, replay, or verify acceptance.',
    }


def prepare(root: Path, run_id: str):
    target = root / run_id
    if target.exists() or target.is_symlink():
        raise ValueError('Run directory already exists')
    target.mkdir(parents=True)
    if os.name == 'posix':
        target.chmod(0o700)
    path = target / 'status.json'
    data = (json.dumps(plan(run_id), indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    fd, temporary_name = tempfile.mkstemp(prefix='.status.', suffix='.partial', dir=target)
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
        if temporary.exists():temporary.unlink()
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['describe', 'prepare'])
    parser.add_argument('--run-id', default='H01')
    parser.add_argument('--root', type=Path, default=Path('build/play2code-benchmark'))
    args = parser.parse_args(argv)
    if args.action == 'describe':
        print(json.dumps(plan(args.run_id), indent=2, sort_keys=True));return
    path = prepare(args.root, args.run_id)
    print(json.dumps({'status': 'PENDING_OWNER_MANUAL_BUILD', 'path': str(path)}, indent=2))


if __name__ == '__main__':
    main()
