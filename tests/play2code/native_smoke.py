#!/usr/bin/env python3
"""Audit/export one real graphical-client Play2Code capture. Does not control Minecraft."""
import argparse
import hashlib
import json
from pathlib import Path

from blockwire.play2code import export_recording, inspect_recording


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture',type=Path)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--output-root',type=Path,help='Export a private copy instead of modifying the sealed capture directory')
    parser.add_argument('--require-movement',action='store_true')
    parser.add_argument('--require-placement',action='store_true')
    parser.add_argument('--require-break',action='store_true')
    args=parser.parse_args()
    before=hashlib.sha256((args.capture/'raw-timeline.jsonl').read_bytes()).hexdigest()
    summary=inspect_recording(args.capture)
    result=export_recording(args.capture,output_root=args.output_root)
    after=hashlib.sha256((args.capture/'raw-timeline.jsonl').read_bytes()).hexdigest()
    exported=Path(result['directory'])
    conversion=json.loads((exported/'conversion.json').read_text())
    kinds=[row['kind'] for row in conversion['generated_operations']]
    checks={
        'raw_timeline_unchanged':before==after,
        'no_remote_controller_interference':summary['no_remote_controller_interference'] is True,
        'bcl_batches_compiled':bool(result['compiler_validation']),
        'replay_not_claimed':result['replay']['attempted'] is False and result['replay']['qualified'] is False,
        'movement_recorded':('movement_checkpoint' in kinds) if args.require_movement else True,
        'placement_recorded':(result['world_mutations']['confirmed_placements']>0) if args.require_placement else True,
        'break_recorded':(result['world_mutations']['confirmed_breaks']>0) if args.require_break else True,
    }
    report={'schema':'blockwire.play2code.native-smoke.v1','status':'PASS' if all(checks.values()) else 'FAIL',
            'capture':str(args.capture),'recording_id':result['recording_id'],'checks':checks,
            'event_counts':summary['event_counts'],'manifest_sha256':result['manifest_sha256'],
            'replay_status':'NOT_RUN','gameplay_scope':'real graphical client capture; no generated-BCL replay'}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(report,indent=2,sort_keys=True))
    if report['status']!='PASS':raise SystemExit(1)


if __name__=='__main__':main()
