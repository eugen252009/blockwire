# Complete-game campaign: scaffold, not a working Survival bot

`examples/end_portal.py` expresses the operator's long-term goal: **defeat the
Ender Dragon and reach the native credits without scripted game pauses**. An
active End portal is now only an intermediate milestone. The filename is retained
for existing invocations.
It does **not** implement autonomous Survival gameplay. None of its eleven required
full Survival stages currently ships with Blockwire. The first local subgoal,
[gather_wood](gather-wood.md), is implemented separately; it does not complete
Overworld preparation. Do not leave it running unattended.

## Current live state

A separate world, **Blockwire Endportal Survival**, was created through the native
Minecraft world-creation menus in the existing isolated test instance:

- Default terrain, random seed, structures enabled, bonus chest disabled.
- Survival, Normal difficulty, commands disabled.
- Observed spawn: `[-18.5, 77, 10.5]`, birch forest, health/hunger 20, empty inventory.
- The world was initially confirmed paused before any gameplay trial. At that
  point no movement, mining or crafting had been performed. Later gameplay is
  recorded separately below; no commands, item spawning or portal creation occurred.

This is world-creation/preflight evidence only, **not end-portal acceptance**.
Local raw records: `build/script-play-verification/world-game-settings.json`,
`world-terrain-settings.json`, `new-survival-world.json`, `new-survival-paused.json`
and `end-portal-preflight.json`. These local files/saves are not distributables.
The loading screen initially outlasted the first pause attempt; the subsequent
`new-survival-paused.json` confirms the actual PauseScreen. An initial read-only
preflight connection failed during the handshake; a later explicit inspection
succeeded. No uncertain mutating action was retried.

## Run the script

```sh
# Offline roadmap: does not connect to Minecraft.
.venv/bin/python examples/end_portal.py --plan

# Read-only inspection of the explicitly selected, already joined instance.
export BLOCKWIRE_CONFIG=/path/to/isolated/minecraft/config/blockwire/settings.json
.venv/bin/python examples/end_portal.py --inspect

# First local subgoal only; resume the supervised world first.
# The script attempts to pause after this one-shot trial.
.venv/bin/python examples/end_portal.py --gather-wood 1 --duration 60

# Optional supervised subgoal without a script-managed final pause:
.venv/bin/python examples/end_portal.py --gather-wood 1 --duration 60 --no-pause

# Full campaign still reports blocked/missing_survival_skills before connection.
.venv/bin/python examples/end_portal.py --run --no-pause
```

There is no automatic unpausing, world joining, world creation, respawn, command
submission, provider installation or transport retry. TLS and existing instance
trust remain mandatory. `--run` is explicit authorization for reviewed providers
to perform native actions; their code is trusted host Python, not sandboxed code.
Providers must not add cheats, teleportation or hidden-world queries.

## Planned skills and observed postconditions

| Required skill (not implemented) | Goal / independent check |
|---|---|
| `survival_prepare_overworld` | Wood → stone → iron, crafting, food; observe iron pickaxe, iron sword, shield and 16 supported food items |
| `survival_enter_nether` | Build/light/enter a native portal; observe Nether dimension |
| `survival_collect_blaze_rods` | In the Nether, navigate a fortress, fight and collect; observe 8 blaze rods |
| `survival_collect_ender_pearls` | In the Nether, obtain pearls through normal gameplay; observe 16 pearls |
| `survival_return_overworld` | Traverse the portal from Nether to Overworld; confirm the changed dimension |
| `survival_craft_eyes` | After returning to the Overworld, native crafting; observe 16 Eyes of Ender |
| `survival_find_stronghold` | Follow thrown eyes, navigate/dig to the portal room; observe a native portal-frame hit within reach |
| `survival_activate_end_portal` | Fill frames; observe a native active End-portal hit within reach |
| `survival_enter_end` | Enter the portal; observe End dimension |
| `survival_defeat_dragon` | Native dragon fight; subsequently reach the active End exit portal |
| `survival_exit_end` | Enter the exit portal; observe the native `WinScreen` credits screen |

Each stage declares an entry and exit dimension, also shown by `--plan`. The
runner checks the actual entry dimension before dispatch and checks the exit
dimension again alongside the inventory/scene postcondition. Inventory items
alone cannot complete a Nether stage in the wrong dimension. Ender-eye crafting
is ordered after the observed return to the Overworld; the Nether is mandatory
before Stronghold/End progression. This is currently stage orchestration, not an
implementation of portal construction, travel, bartering or the other missing
native Survival skills.

These counts are preparation targets, not guarantees of safety or enough supplies.
The first stage alone still needs general terrain navigation, crafting, food and
iron acquisition. The initial local wood attempt stopped on unsupported descent.
In a later live test, explicitly authorized risky native movement descended to
Y69 with five fall damage (survived), followed by separate skill attempts. After a
timeout and an uncollected-drop stop, a follow-up verified **one dark oak log** in
inventory. The last recorded state is paused, alive, health 20, hunger 17. This
is not automatic descent or recovery; see [wood harvesting](gather-wood.md) and
[preserved follow-up evidence](evidence/gather-wood-followup-live.json).
Current flat-ground walking, approach and experimental combat cannot substitute
for arbitrary-terrain traversal, mining, crafting, shelter, dimension travel,
fortress navigation or interpreting thrown Eyes of Ender.

## Extension contract

Only explicitly selected installed providers load:

```sh
.venv/bin/python examples/end_portal.py --run --provider reviewed_survival --duration 120
```

This is an integration interface, **not an available provider or install command**.
Follow [extensions](extensions.md) to implement skills with strict SkillParameters,
actor fences, bounded actions, cancellation, observed outcomes and cleanup. Each
stage must accept `timeout_seconds`; all names/schemas are checked before actions.
A provider's success result is insufficient: the script checks scene/inventory
postconditions again. Only explicit Nether-entry/return and End-entry stages may
accept a new session at the expected changed dimension. Providers must independently guard
player identity and must not respawn or rebind a replacement actor.

An attempt is cooperatively bounded to .1–600 seconds, each stage to at most 120.
This is **not a promise to finish Minecraft in that time**. There is no automatic
retry or checkpoint resume. A real long-running campaign needs verified persistent
checkpoints and resource-aware replanning rather than repeatedly gathering items
already consumed by a later stage. This scaffold stops at the first missing,
blocked, timed-out, cancelled, failed or unverified stage, releases inputs after
execution, and by default attempts a development pause. With `--no-pause`, input
release remains mandatory but the script does not open the pause menu. Cleanup
failure is reported, never hidden.

## Statistics in the report

Use `--stats-file /explicit/path/player-statistics.json` to attach native saved
world totals and saved-snapshot differences to the JSON report, including deaths,
mob kills, walking/sprinting, play time, damage and mining/crafting counts. No
scoreboard commands or cheats are enabled. Missing data stays unknown, and saved
values are **not** guaranteed fresh live counters. See [statistics](statistics.md)
for file selection, units, reset handling and final-report limitations.

## Pause policy and final success

Development attempts may pause on stop (the default). `--no-pause` disables only
this example's script-managed pause, including on blocked/failure/cancel/timeout.
It never disables F8, actor fences, cooperative budgets or expiring native inputs.
It does not resume an existing paused game; no-pause campaign execution rejects a
PauseScreen rather than silently continuing. Pause on lost focus, user menus,
other mods and installed provider behavior are outside this flag. Configure the
client deliberately for supervised trials; no-pause is not a survival guarantee.
Providers must not call `open_pause` during a no-pause playthrough. They are trusted
host Python, not sandboxed by this scaffold.

The eventual acceptance gate is a fresh normal Survival world completed entirely
through Python, with **no game pauses and no manual gameplay intervention**.
Current short cooperative attempt limits remain development bounds, not permission
to extend unattended execution indefinitely. Resource-aware planning, food,
shelter, continuous hazard handling and general terrain navigation still need
implementation before that acceptance test is possible.

End-portal activation, disappearing boss visibility and a provider's `succeeded`
claim cannot complete the campaign. The final check reads the native menu type
independently and requires `WinScreen` after all preceding stages. In the intended
fresh vanilla Survival fixture, an active End exit portal/credits is environmental
completion evidence; this is not a direct boss-death event observation and is not
a general proof for pre-completed/modded worlds or arbitrary servers. The actual
End fight, exit/credits observation, and uninterrupted full playthrough are all
**NOT RUN**. No live gameplay was requested for this goal/pause-policy change.

Tests in `python/tests/test_end_portal_example.py` simulate the contract only.
Passing them does not establish that any Survival stage works in Minecraft.
