import argparse
import json
from .client import Bridge, Player


def main():
    parser = argparse.ArgumentParser(description="Blockwire: observations and descriptive native-player goals.")
    commands = parser.add_subparsers(dest="operation")
    for operation in ["observe", "inventory", "menu", "stop", "skills"]:
        command = commands.add_parser(operation)
        command.add_argument("--json", action="store_true")
    walk = commands.add_parser("walk_to", help="Walk to a flat-ground world position; no damage immunity")
    for coordinate in ["x", "y", "z"]:
        walk.add_argument(coordinate, type=float)
    walk.add_argument("--sneak", action="store_true")
    walk.add_argument("--allow-damage", action="store_true", help="Disable conservative hazard policy")
    walk.add_argument("--timeout", type=float, default=30)
    approach = commands.add_parser("approach", help="Approach a visible interactable without opening or using it")
    approach.add_argument("target", nargs="?", default="minecraft:chest")
    approach.add_argument("--position", type=int, nargs=3, metavar=("X", "Y", "Z"))
    approach.add_argument("--sneak", action="store_true")
    approach.add_argument("--allow-damage", action="store_true")
    approach.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    operation = args.operation or "observe"
    if operation == "skills":
        from .skills import default_registry
        print(json.dumps(default_registry(plugins=True).describe(), indent=2))
        return
    with Bridge.from_env() as bridge:
        player = Player(bridge)
        if operation in {"walk_to", "approach"}:
            if operation == "walk_to":
                result = player.walk_to(args.x, args.y, args.z, args.sneak, not args.allow_damage,
                                        timeout_seconds=args.timeout)
            else:
                result = player.approach(args.target, position=args.position, sneak=args.sneak,
                                         avoid_damage=not args.allow_damage, timeout_seconds=args.timeout)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            if result["status"] != "succeeded":
                raise SystemExit(2)
        else:
            result = getattr(player, operation)()
            print(json.dumps(result, indent=2, ensure_ascii=False) if getattr(args, "json", False) else result["text"])


if __name__ == "__main__":
    main()
