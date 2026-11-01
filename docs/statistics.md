# Saved player statistics and run reports

The Python reporter reads **only an explicitly selected vanilla player-statistics
JSON file**. It never discovers accounts/worlds, reads player NBT/chunks, writes a
save, creates scoreboard objectives, enables commands or connects to Minecraft.
This is a trusted local-host utility, not a new remote file/observation RPC.

An in-game scoreboard/sidebar is **not** created. In the current commands-disabled
Survival world, native saved statistics provide counters without enabling cheats.
Live scoreboard or synchronized client-statistics integration is not implemented.

## Metrics

- Deaths, mob kills, player kills, jumps.
- Walking, sprinting, crouching, swimming, climbing, falling and elytra distance,
  separately in metres (native centimetres divided by 100).
- Play time in nominal game seconds (native ticks divided by 20), not wall time.
- Damage taken/dealt in HP (native tenths of HP divided by 10).
- Totals of blocks mined, items crafted and items picked up, using native counters.

No kill is inferred from an attack receipt, an absent mob, dropped items or player
movement. Coordinate displacement is not substituted for Minecraft's walking stat.
These counters describe the selected player/world and may include manual gameplay.
They do not establish which script, action or particular block caused an event.

## Explicit file selection

Minecraft 26.3 stores the selected world's file under
`<world>/players/stats/<player-uuid>.json`. Older worlds may use
`<world>/stats/<player-uuid>.json`. Select the intended file yourself; the reporter
does not search other profiles, accounts or servers. On multiplayer servers, an
operator-provided export is needed; this utility cannot access remote save files.
Never ship real player statistics, account data or world saves in a bundle.

```sh
# Offline report of one saved snapshot. No game connection or commands.
.venv/bin/python examples/report_statistics.py /explicit/path/player-stats.json

# Compare operator-created before/after copies from the same player/world.
.venv/bin/python examples/report_statistics.py after.json --before before.json

# Include totals and before/after saved-counter differences in a campaign report.
.venv/bin/python examples/end_portal.py --run --no-pause \
  --stats-file /explicit/path/player-stats.json > campaign-report.json
```

The campaign still refuses missing gameplay skills. Statistics collection is
independent of gameplay success; a reporting failure does not fabricate counters
or cause uncertain gameplay commands to be retried. `--stats-file` is optional;
without it the report says `not_configured`, not zero deaths/kills. The offline
`--plan` mode does not read a stats file. The report goes to stdout; the utilities
never overwrite a stats file or attempt to force a save/pause.

## Freshness and comparison limits

**These are saved counters, not synchronized live telemetry.** Minecraft normally
persists them during its own saves. An open or paused world may contain more recent
unsaved events. The reporter does not force a save, unpause, reconnect or issue
`/save-all`. Native save/quit after a completed development trial is one normal
way to persist state, but this is never performed automatically by the reporter.

Every report includes `freshness: saved_only_not_live_verified`, saved modification
time, content hash, units and an explicit warning. `totals` are the values in that
saved snapshot, never a claim about the current live state.

- An omitted counter inside a valid vanilla `stats` object means zero **in that
  snapshot**; vanilla omits unincremented counters.
- A missing/unreadable/malformed file means `unavailable`, `totals: null`, and
  `run_delta: null`, never invented zero deaths or kills.
- Without a baseline, the report only has totals; it cannot reconstruct past runs.
- `run_delta` is a difference of operator-selected saved snapshots, not verified
  run identity. Player/world identity is not present in the JSON itself. Do not
  compare different players/worlds just because their counters increase.
- Identical content is marked `snapshots_identical: true`. A zero delta can mean
  no change **or simply that Minecraft has not saved yet**.
- Any decreasing tracked counter suppresses all deltas and reports
  `counter_decreased_or_source_changed`; resets/source changes are not hidden.
- JSON input is bounded to 2 MiB. Invalid/negative/boolean/nonfinite counters,
  duplicate keys and malformed native objects are rejected. Changes detected
  during a file read fail without an automatic retry. Paths/content are not
  included in reporting error messages.

A future uninterrupted playthrough needs synchronized native observations or
verified save/export checkpoints to establish fresh end-of-run totals. This
implementation intentionally does not claim to solve that requirement yet.

## Scoped integration check

A read-only report of the existing **Blockwire Endportal Survival** saved counters
returned 0 deaths, 0 mob kills, 5.88 m walked, 0.69 m sprinted, 8 m fallen, 5 HP
damage taken, 2 blocks mined and 1 item picked up. These agree with the separately
recorded descent/wood test, but are **saved world totals**, not a reconstructed
per-attempt delta. No game action, save modification, scoreboard command or cheats
change was requested for this statistics check.

See [evidence](evidence/saved-statistics.json), `python/tests/test_statistics.py`
and the reporting integration contract in `test_end_portal_example.py`.
