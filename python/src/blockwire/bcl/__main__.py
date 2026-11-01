"""Offline BCL/1 compile and progressive discovery; no Minecraft connection."""
import argparse,json
from pathlib import Path
from . import default_commands,compile_report

def main():
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--compile',metavar='SOURCE');g.add_argument('--file',type=Path)
    g.add_argument('--discover',metavar='QUERY');g.add_argument('--describe',metavar='OPCODE')
    a=p.parse_args();r=default_commands()
    if a.discover is not None:result=r.discover(a.discover,64)
    elif a.describe is not None:result=r.describe(a.describe)
    else:result=compile_report(a.compile if a.compile is not None else a.file.read_text(),r)
    print(json.dumps(result,indent=2,allow_nan=False));return int(isinstance(result,dict) and result.get('ok') is False)
if __name__=='__main__':raise SystemExit(main())
