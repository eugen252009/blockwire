#!/usr/bin/env python3
"""Explicit opt-in owned-client benchmark. Never runs during unittest discovery."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from building.reference import House


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['describe','create','run-a','run-b','recover-probe'])
    p.add_argument('--saves',type=Path)
    p.add_argument('--private',type=Path,default=Path('build/superflat-benchmark/private'))
    p.add_argument('--run-id')
    p.add_argument('--fault',choices=['truncate','lost-ack','cancel'])
    p.add_argument('--from-run',help='Explicit failed probe to reconcile, never automatically replay')
    p.add_argument('--resume-from',help='Explicit deterministic DEBUG continuation, not a fresh trial')
    p.add_argument('--start-frame',type=int,default=0)
    p.add_argument('--authorize-test-client',action='store_true')
    args=p.parse_args()
    if args.action=='describe':print(json.dumps(House().document(),indent=2));return
    if not args.authorize_test_client or args.saves is None:p.error('Explicit --authorize-test-client and --saves required')
    from blockwire import Bridge,Player
    with Bridge.from_env() as bridge:
        player=Player(bridge)
        if args.action=='create':
            from building.fixture import create
            result=create(player,args.saves,args.private)
        else:
            import asyncio
            from building.live import run
            if not args.run_id:p.error('--run-id required')
            if args.action=='recover-probe':
                from building.recovery import recover
                if not args.from_run:p.error('--from-run required')
                result=asyncio.run(recover(player,args))
            else:
                if (args.fault or args.resume_from or args.start_frame) and args.action!='run-a':p.error('Fault/debug options are deterministic only')
                result=asyncio.run(run(player,args))
        print(json.dumps(result,indent=2))

if __name__=='__main__':main()
