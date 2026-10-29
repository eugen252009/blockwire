"""Explicitly select ONE installed, trusted local controller. No discovery-time imports."""
import argparse
import asyncio
from dataclasses import asdict
from importlib.metadata import entry_points
import json

from .controller import ControllerParameters, run_controller


def load_controller(name: str):
    matches = [entry for entry in entry_points(group="blockwire.controllers") if entry.name == name]
    if len(matches) != 1:
        raise ValueError("Controller is absent or ambiguous: " + name)
    script = matches[0].load()
    if not callable(getattr(script, "loop", None)):
        raise ValueError("Selected controller must expose loop(bot)")
    return script


def main():
    parser = argparse.ArgumentParser(description="Run one explicitly selected trusted Python controller, without MCP.")
    parser.add_argument("controller", help="Installed blockwire.controllers entry-point name (executes trusted host Python)")
    parser.add_argument("--duration", type=float, default=60, help="Wall-clock budget, .1–600 seconds (default 60)")
    parser.add_argument("--hz", type=float, default=10, help="Maximum loop cadence, 2–20 Hz (default 10)")
    args = parser.parse_args()
    parameters = ControllerParameters(duration_seconds=args.duration, hz=args.hz)
    script = load_controller(args.controller)
    try:
        result = asyncio.run(run_controller(script, **parameters.model_dump()))
    except KeyboardInterrupt:
        raise SystemExit(130)
    print(json.dumps(asdict(result)))
    if result.status != "stopped":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
