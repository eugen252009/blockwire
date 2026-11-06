import argparse
import json
import sys
from .client import Bridge, Player


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in {'repl', 'run'}:
        from .bcl.cli import main as bcl_main
        return bcl_main(argv)
    parser = argparse.ArgumentParser(description="Blockwire: native-player goals; use repl or run for the BCL terminal.")
    commands = parser.add_subparsers(dest="operation")
    commands.add_parser("repl", help="Interactive BCL terminal (use repl --help for connection options)")
    commands.add_parser("run", help="Execute one complete BCL file (use run FILE --help for options)")
    for operation in ["observe", "inventory", "menu", "stop", "skills"]:
        command = commands.add_parser(operation)
        command.add_argument("--json", action="store_true")
    command = commands.add_parser("command", help="Submit one quoted Minecraft slash command; native permissions apply")
    command.add_argument("command")
    command.add_argument("--json", action="store_true")
    chat = commands.add_parser('chat', help='Send normal Minecraft chat; receipt is not delivery')
    chat.add_argument('message');chat.add_argument('--actor-session', required=True)
    chat.add_argument('--json', action='store_true')
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
    distance = commands.add_parser("estimate_distance", help="Measure currently observed block surfaces only; no X-ray or landing guarantee")
    distance.add_argument("target", nargs="?", default="minecraft:dirt")
    distance.add_argument("--position", type=int, nargs=3, metavar=("X", "Y", "Z"))
    distance.add_argument("--timeout", type=float, default=30)
    search = commands.add_parser("search", help="Targeted read-only sight search; no walking or mining")
    search.add_argument("target", nargs="?", default="logs")
    search.add_argument("--range", type=int, default=64)
    search.add_argument("--cone-degrees", type=int, default=30)
    search.add_argument("--timeout", type=float, default=10.)
    around = commands.add_parser("look_around", help="Read-only 30-degree/10x10 reticle block and distance report")
    around.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args(argv)
    operation = args.operation or "observe"
    if operation == "skills":
        from .skills import default_registry
        print(json.dumps(default_registry(plugins=True).describe(), indent=2))
        return
    with Bridge.from_env() as bridge:
        player = Player(bridge)
        if operation in {"walk_to", "approach", "estimate_distance", "look_around", "search"}:
            if operation == "search":
                result = player.search(args.target, range=args.range, cone_degrees=args.cone_degrees, timeout_seconds=args.timeout)
            elif operation == "look_around":
                result = player.look_around(timeout_seconds=args.timeout)
            elif operation == "walk_to":
                result = player.walk_to(args.x, args.y, args.z, args.sneak, not args.allow_damage,
                                        timeout_seconds=args.timeout)
            elif operation == "estimate_distance":
                result = player.estimate_distance(args.target, position=args.position, timeout_seconds=args.timeout)
            else:
                result = player.approach(args.target, position=args.position, sneak=args.sneak,
                                         avoid_damage=not args.allow_damage, timeout_seconds=args.timeout)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            if result["status"] != "succeeded":
                raise SystemExit(2)
        else:
            if operation == 'chat':result = player.chat(args.message, actor_session=args.actor_session)
            else:result = player.command(args.command) if operation == "command" else getattr(player, operation)()
            print(json.dumps(result, indent=2, ensure_ascii=False) if getattr(args, "json", False) else result["text"])


if __name__ == "__main__":
    raise SystemExit(main())
