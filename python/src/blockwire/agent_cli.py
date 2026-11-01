"""Explicit standalone strategic LLM agent; never launched by Minecraft/game text."""
import argparse
import json
import os
import signal

from .agent import AgentRuntime, AgentLimits, SessionStore, SAFE_SKILLS
from .client import Bridge, Player
from .llm import OpenAIJSONDecider
from .mailbox import MailboxDecider
from .recipes import RECIPES
from .skills import default_registry, load_selected_plugins
from .statistics import capture_statistics, statistics_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--describe', action='store_true', help='Offline capability/recipe catalogue; no game/model connection')
    parser.add_argument('--goal')
    parser.add_argument('--agent-id')
    parser.add_argument('--world-id', help='Operator-selected world/server namespace, never inferred from hidden save data')
    parser.add_argument('--player-id', help='Expected native player_uuid from observe')
    parser.add_argument('--state', help='Private per-agent SQLite file; do not share with another active agent')
    model_transport = parser.add_mutually_exclusive_group()
    model_transport.add_argument('--llm-url', help='Explicit full OpenAI-compatible chat/completions URL')
    model_transport.add_argument('--mailbox', help='Private JSON request/reply handoff to an external LLM host')
    parser.add_argument('--model')
    parser.add_argument('--allow-remote-model', action='store_true', help='Authorize sending compact game context/goal to selected HTTPS model service')
    parser.add_argument('--model-key-env', default='BLOCKWIRE_LLM_API_KEY')
    parser.add_argument('--provider', action='append', default=[], help='Explicit installed trusted skill provider')
    parser.add_argument('--allow-skill', action='append', default=[], help='Explicit additional registered skill authority, e.g. fight')
    parser.add_argument('--rebind', action='store_true', help='Explicitly bind the saved session to the current actor after restart; never replay pending effects')
    parser.add_argument('--duration', type=float, default=120.)
    parser.add_argument('--action-timeout', type=float, default=30.)
    parser.add_argument('--model-timeout', type=float, default=20.)
    parser.add_argument('--max-decisions', type=int, default=20)
    parser.add_argument('--pause-on-stop', action='store_true', help='Development only: attempt a native pause after confirmed cleanup')
    parser.add_argument('--stats-file', help='Optional explicitly selected saved player statistics for the final report, not live telemetry')
    args = parser.parse_args(argv)
    registry = default_registry()
    load_selected_plugins(registry, ','.join(args.provider))
    if args.describe:
        print(json.dumps({'skills': registry.describe(), 'recipes': [r.describe() for r in RECIPES.values()],
                          'limits': ['flat full-block navigation', 'no farming/growth/smelting yet',
                                     'no automatic respawn/reconnect', 'not qualified for unattended survival']}, indent=2))
        return 0
    if not all((args.goal, args.agent_id, args.world_id, args.player_id, args.state)):
        parser.error('Explicit goal, agent/world/player IDs and state required')
    if not 1 <= len(args.goal) <= 2048: parser.error('Bounded operator goal required')
    limits = AgentLimits(duration_seconds=args.duration, decision_timeout_seconds=args.model_timeout,
                         action_timeout_seconds=args.action_timeout,
                         max_decisions=args.max_decisions)
    if args.mailbox:
        decider = MailboxDecider(args.mailbox, timeout=args.model_timeout)
    else:
        if not args.llm_url or not args.model: parser.error('Explicit llm-url and model (or mailbox) required')
        decider = OpenAIJSONDecider(args.llm_url, args.model, api_key=os.environ.get(args.model_key_env),
                                   timeout=args.model_timeout, allow_remote=args.allow_remote_model)
    store = SessionStore(args.state, {'agent_id': args.agent_id, 'world_id': args.world_id, 'player_id': args.player_id})
    baseline, _ = capture_statistics(args.stats_file)
    with Bridge.from_env() as bridge:
        player = Player(bridge)
        available = {d['name'] for d in registry.describe()}
        runtime = AgentRuntime(player, decider, store, args.goal, registry=registry,
                               allowed_skills=(SAFE_SKILLS & available) | set(args.allow_skill), allow_rebind=args.rebind,
                               **limits.model_dump())
        previous = signal.signal(signal.SIGINT, lambda *_: runtime.cancel())
        try:
            result = runtime.run()
            if args.pause_on_stop and result.get('cleanup') == 'released' and not runtime.transport_lost:
                s, m = player.observe(), player.menu()
                if s.get('in_world') and s.get('alive') and not m.get('screen_open'):
                    player.open_pause()
            snapshot, metrics = capture_statistics(args.stats_file)
            if snapshot is not None and baseline is not None: metrics = statistics_report(snapshot, baseline)
            result['statistics'] = metrics
            print(json.dumps(result, indent=2))
        finally:
            signal.signal(signal.SIGINT, previous)
    return 0 if result['reason'] == 'planner_finished_unverified' else 2


if __name__ == '__main__':
    raise SystemExit(main())
