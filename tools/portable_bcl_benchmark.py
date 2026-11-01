#!/usr/bin/env python3
"""Opt-in BCL/1 relative Test-A portability qualification; private native artifacts only."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python/src'))
sys.path.insert(0, str(ROOT / 'tests'))

from blockwire import Bridge, Player
from building.portable import ORIGINS, PORTABLE_SOURCE_SHA256, frame_sources, source
from building.portable_live import (
    finalize, freeze, run_interfaces, run_mapping, run_origin, run_recovery,
    run_rehome, run_split,
)

NATIVE = {'mapping', 'run-origin', 'split', 'recovery', 'rehome', 'interfaces'}


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['describe', 'freeze', *sorted(NATIVE), 'finalize'])
    p.add_argument('--cohort', default='P01')
    p.add_argument('--run-id')
    p.add_argument('--origin', choices=sorted(ORIGINS))
    p.add_argument('--output', type=Path, default=ROOT / 'build/bcl-portability')
    p.add_argument('--baseline-private', type=Path, default=ROOT / 'build/superflat-benchmark/private')
    p.add_argument('--saves', type=Path)
    p.add_argument('--installed-jar', type=Path)
    p.add_argument('--certificate', type=Path, default=ROOT / 'build/bcl-verification/private/gateway.pem')
    p.add_argument('--private-key', type=Path, default=ROOT / 'build/bcl-verification/private/gateway-key.pem')
    p.add_argument('--authorize-test-client', action='store_true')
    return p


def _validate(args):
    args.tool_path = Path(__file__).resolve()
    if args.action != 'describe' and args.installed_jar is None:
        raise SystemExit('--installed-jar is required so every cohort freezes the exact native mod bytes')
    if args.action in NATIVE:
        if not args.authorize_test_client:
            raise SystemExit('Refusing native execution without --authorize-test-client')
        if args.saves is None:
            raise SystemExit('--saves is required for isolated fixture restore/capture')
        if args.action == 'run-origin' and args.origin is None:
            raise SystemExit('run-origin requires --origin A, B or C')
    return args


async def _native(args):
    with Bridge.from_env() as bridge:
        player = Player(bridge)
        if args.action == 'mapping': result = await run_mapping(player, args)
        elif args.action == 'run-origin': result = await run_origin(player, args)
        elif args.action == 'split': result = await run_split(player, args)
        elif args.action == 'recovery': result = await run_recovery(player, args)
        elif args.action == 'rehome': result = await run_rehome(player, args)
        elif args.action == 'interfaces': result = await run_interfaces(player, args)
        else: raise AssertionError(args.action)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get('passed') else 1


def main(argv=None):
    args = _validate(parser().parse_args(argv))
    if args.action == 'describe':
        print(json.dumps({'schema': 'blockwire.bcl-portability.describe.v1',
                          'portable_bcl_sha256': PORTABLE_SOURCE_SHA256,
                          'portable_bcl_bytes': len(source().encode()),
                          'frames': len(frame_sources()), 'origins': ORIGINS}, indent=2, sort_keys=True))
        return 0
    if args.action == 'freeze':
        print(json.dumps(freeze(args), indent=2, sort_keys=True)); return 0
    if args.action == 'finalize':
        result = finalize(args); print(json.dumps(result, indent=2, sort_keys=True)); return 0 if result.get('passed') else 1
    return asyncio.run(_native(args))


if __name__ == '__main__':
    raise SystemExit(main())
