#!/usr/bin/env python3
"""Explicit opt-in deterministic native movement benchmark; never runs in unit discovery."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from movement.reference import document

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['describe','create','run'])
    parser.add_argument('--saves',type=Path);parser.add_argument('--private',type=Path,default=Path('build/movement-benchmark/private'))
    parser.add_argument('--run-id');parser.add_argument('--variant',choices=['vanilla','before','after'])
    parser.add_argument('--scenario',action='append',default=[]);parser.add_argument('--repeats',type=int)
    parser.add_argument('--authorize-test-client',action='store_true');args=parser.parse_args()
    if args.action=='describe':print(json.dumps(document(),indent=2));return
    if not args.authorize_test_client or args.saves is None:parser.error('Explicit --authorize-test-client and --saves required')
    from blockwire import Bridge,Player
    with Bridge.from_env() as bridge:
        player=Player(bridge)
        if args.action=='create':
            from movement.fixture import create;result=create(player,args.saves,args.private)
        else:
            if not args.run_id or not args.variant:parser.error('--run-id and --variant required')
            if args.repeats is not None and not 1<=args.repeats<=10:parser.error('--repeats must be 1..10')
            from movement.live import run;result=run(player,args)
        print(json.dumps(result,indent=2))

if __name__=='__main__':main()
