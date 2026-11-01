"""Read explicitly selected vanilla player-statistics JSON; never modify a save.

These are saved counters, NOT live/synchronized observations or scoreboard RPCs.
No automatic world/account discovery, commands, NBT reads or kill inference.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path


MAX_BYTES = 2 * 1024 * 1024
# Report name -> native counter, divisor, unit. Distances stay separate by mode.
CUSTOM = {
    "deaths": ("minecraft:deaths", 1, "count"),
    "mob_kills": ("minecraft:mob_kills", 1, "count"),
    "player_kills": ("minecraft:player_kills", 1, "count"),
    "jumps": ("minecraft:jump", 1, "count"),
    "walked_m": ("minecraft:walk_one_cm", 100, "m"),
    "sprinted_m": ("minecraft:sprint_one_cm", 100, "m"),
    "crouched_m": ("minecraft:crouch_one_cm", 100, "m"),
    "swum_m": ("minecraft:swim_one_cm", 100, "m"),
    "climbed_m": ("minecraft:climb_one_cm", 100, "m"),
    "fallen_m": ("minecraft:fall_one_cm", 100, "m"),
    "elytra_m": ("minecraft:aviate_one_cm", 100, "m"),
    "play_time_seconds": ("minecraft:play_time", 20, "nominal_game_seconds"),
    "damage_taken_hp": ("minecraft:damage_taken", 10, "hp"),
    "damage_dealt_hp": ("minecraft:damage_dealt", 10, "hp"),
}
TOTALS = {"blocks_mined": "minecraft:mined", "items_crafted": "minecraft:crafted",
          "items_picked_up": "minecraft:picked_up"}


@dataclass(frozen=True)
class StatisticsSnapshot:
    counters: dict[str, int]
    content_sha256: str
    saved_mtime_ns: int | None = None


def _counter(value):
    if type(value) is not int or value < 0 or value > 2**63-1:
        raise ValueError("Statistic counters must be nonnegative bounded integers")
    return value


def _object(value):
    if not isinstance(value, dict):
        raise ValueError("Expected a native statistics object")
    return value


def parse_statistics(data: bytes, *, saved_mtime_ns=None) -> StatisticsSnapshot:
    if len(data) > MAX_BYTES:
        raise ValueError("Statistics snapshot exceeds size bound")
    def reject_constant(value):
        raise ValueError("Nonfinite JSON constant")
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate statistics key")
            result[key] = value
        return result
    document = _object(json.loads(data, parse_constant=reject_constant, object_pairs_hook=unique_object))
    if "stats" not in document:
        raise ValueError("Missing native stats object")
    stats = _object(document["stats"])
    custom = _object(stats.get("minecraft:custom", {}))
    # Vanilla omits counters that have never been incremented. This is not the
    # same as an absent/unreadable stats file, which is explicitly unavailable.
    counters = {name: _counter(custom.get(key, 0)) for name, (key, _, _) in CUSTOM.items()}
    for name, key in TOTALS.items():
        counters[name] = _counter(sum(_counter(value) for value in _object(stats.get(key, {})).values()))
    return StatisticsSnapshot(counters, hashlib.sha256(data).hexdigest(), saved_mtime_ns)


def load_statistics(path: str | Path) -> StatisticsSnapshot:
    """Read ONLY the operator-provided file, without finding saves/accounts."""
    with Path(path).open("rb") as source:
        import os
        before = os.fstat(source.fileno())
        data = source.read(MAX_BYTES+1)
        after = os.fstat(source.fileno())
    if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
        raise ValueError("Statistics changed during read; no automatic retry")
    return parse_statistics(data, saved_mtime_ns=after.st_mtime_ns)


def _values(counters):
    return {name: (value if name not in CUSTOM or CUSTOM[name][1] == 1
                   else value / CUSTOM[name][1]) for name, value in counters.items()}


def statistics_report(after: StatisticsSnapshot, before: StatisticsSnapshot | None = None):
    report = {
        "status": "saved_snapshot", "source": "vanilla_player_statistics_json",
        "freshness": "saved_only_not_live_verified",
        "totals": _values(after.counters),
        "units": {**{name: unit for name, (_, _, unit) in CUSTOM.items()}, **{name: "count" for name in TOTALS}},
        "saved_mtime_ns": after.saved_mtime_ns, "content_sha256": after.content_sha256,
        "warning": "Totals may omit unsaved gameplay. Missing native counters mean zero in this snapshot, not proof of zero live events.",
        "run_delta": None,
    }
    if before is not None:
        decreased = [name for name in after.counters if after.counters[name] < before.counters[name]]
        report.update(baseline_sha256=before.content_sha256,
                      snapshots_identical=before.content_sha256 == after.content_sha256,
                      comparison_scope="operator_selected_saved_snapshots_not_verified_run_identity")
        if decreased:
            # Do not silently subtract different/reset worlds or invent negative deaths.
            report.update(delta_status="counter_decreased_or_source_changed", decreased_counters=decreased)
        else:
            report.update(delta_status="saved_snapshot_delta",
                          run_delta=_values({name: value-before.counters[name] for name, value in after.counters.items()}))
    return report


def capture_statistics(path):
    """Nonfatal reporting failure; no invented zero counters or automatic retries."""
    if path is None:
        return None, {"status": "not_configured", "totals": None, "run_delta": None}
    try:
        snapshot = load_statistics(path)
        return snapshot, statistics_report(snapshot)
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        return None, {"status": "unavailable", "totals": None, "run_delta": None,
                      "error_type": type(exc).__name__}
