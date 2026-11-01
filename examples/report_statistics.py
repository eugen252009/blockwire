"""Report explicitly selected saved Minecraft player-statistics JSON; read-only.

python examples/report_statistics.py /path/to/player-stats.json
python examples/report_statistics.py after.json --before before.json

No game connection, world discovery, scoreboard commands or save writes.
Minecraft may not yet have saved the latest events. Inputs must be snapshots of
one player in the intended world; that identity cannot be proven from JSON alone.
"""
import argparse
import json
from blockwire.statistics import capture_statistics, statistics_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("after", help="Explicit vanilla player stats JSON or an operator-created copy")
    parser.add_argument("--before", help="Optional earlier snapshot of the same player's same world")
    args = parser.parse_args(argv)
    before, baseline = capture_statistics(args.before)
    after, report = capture_statistics(args.after)
    if before is not None and after is not None:
        report = statistics_report(after, before)
    elif args.before:
        report["baseline_status"] = baseline["status"]
    print(json.dumps(report, indent=2))
    return 0 if after is not None and (not args.before or before is not None) else 2


if __name__ == "__main__":
    raise SystemExit(main())
