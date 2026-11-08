# First deterministic Survival benchmark: wood → stone tools

Program: [`examples/stone_tools_benchmark.py`](../examples/stone_tools_benchmark.py).
This is an explicitly requested **scripted benchmark**, not autonomous LLM play,
a Play2Code replay, or a new planner inside MCP/Fabric. No model calls are made.

**Graphical Minecraft acceptance: NOT RUN.** Contract fixtures simulate observations
and BCL outcomes; they do not prove that this strategy works from an arbitrary
natural spawn. Historical failed wood/gameplay runs remain unchanged.

## Fixed progression

1. Turn to four cardinal views. Retain coarse `look_around` reports and run separate
   bounded native `search("logs", range=64, cone_degrees=90)` observations.
2. Find and collect **eight inventory logs**. Local harvesting uses `C1 N=1 E=true`.
   If no local target has a known standing position, choose an unvisited reachable
   native-mesh waypoint, biased toward observed distant logs. No coordinates come
   from a seed, save, hidden block query or selected/improved spawn. Search hits do
   not prove a route; `M0` rechecks native collision/support throughout movement.
3. Convert the observed wood species to planks, craft one table and eight sticks,
   place/open the table, then craft and equip a **wooden pickaxe**.
4. Dig northward **one descending supported stair step at a time** (`M2 N=1`).
   This is deliberately not a blind vertical shaft through the player's support.
   The existing motor refuses unsupported floors, falling blocks, fluids, hazards
   and unsuitable equipped tools. Record the actual descent and return waypoints.
5. Below the surface waypoint, collect drops from **nine distinct, freshly exposed
   `minecraft:stone` targets**, each with an exact `C2 ... P=[x,y,z]` and a pickaxe.
   Each counted harvest needs both the motor's matching mining-target evidence and
   an additional inventory cobblestone. Mere sightings, disappearance or receipts
   do not count. Stone cleared during descent is extra and is not counted toward
   these nine explicit harvests. Do not mine recorded stair/workstation supports.
6. Return to the last step and **jump-place one reserved plank block per depth
   step** (`I3 ... A=true J=true`) before walking to the preceding waypoint.
   Each ascent requires consumed material, observed landing and verified movement.
   Return means grounded at the recorded surface/workbench approach waypoint—not
   merely an increased Y value, a placement receipt or an arbitrary high spot.
7. Only after that return, reopen the table and craft **one stone pickaxe, one stone
   shovel and one stone sword**. Re-observe all three in inventory and return to
   the grounded surface waypoint before reporting success.

All actions compile/execute through the existing **legacy BCL/1** registry and
`BCLRunner → AgentRuntime → guarded skills → native Minecraft`. The Python program
owns this disclosed progression. It does not widen `machine-v1` or silently switch
an existing MCP configuration. Coarse/dense read-only perception stays separate
from BCL action frames; there is one action per frame with observations between.

The recipe catalogue now includes the vanilla stone shovel (one cobblestone,
two sticks) and sword (two cobblestone, one stick). Native result slots, output
inventory and ingredient consumption remain authoritative; no stacks are created
by the host. These are descriptive recipes, not a core progression planner.

## Material and time envelope

- Eight logs produce 32 planks: four for the table, three for the wooden pickaxe,
  and four for two batches of sticks. **21 planks remain**, at least eight reserved
  before descent. Mixed vanilla wood species are supported explicitly.
- The final three tools cost **six cobblestone and five sticks**. Together with the
  wooden pickaxe, seven of the eight sticks are needed. Return construction uses
  planks, not the cobblestone needed for the tools.
- Default and maximum duration: **1,800 seconds**, optionally reduced with
  `--duration` (10..1800). One deadline covers all stages; no per-stage reset.
- At most **eight descent steps**, **32 exploration moves** within 64 blocks of the
  initial position, and **512 single-operation BCL frames**. Existing native ray,
  result, queue, interaction, skill timeout and short input-lease bounds remain.
- Unknown geometry is not air. Negative searches are not absence proof. Difficult
  canopy starts, steep terrain, occlusion or insufficient exposed stone can stop
  this first benchmark; no rescue, teleport, item grant or alternative hidden plan
  follows a failed frame.

## Prepare and invoke explicitly

Create a **fresh, isolated Survival world** with no bonus chest, supplied items or
other players, using an owned matching Blockwire development instance. Join as the
selected player, enable Blockwire deliberately, and leave gameplay unpaused with
no screen open. Do not share control with another script, MCP host or human.
The program does **not create/select worlds** or resume a paused/stopped campaign.

World freshness and Survival mode are operator attestations: the current scene API
cannot independently certify those properties. The program additionally checks
player UUID, the captured actor/dimension fence, an initially empty inventory and
cursor, clean gameplay, supported grounded geometry and health. `--world-id` is an
audit label, **not** a server/world selection or authenticated save identity.

Offline inspection, without connecting:

```sh
PYTHONPATH=python/src .venv/bin/python examples/stone_tools_benchmark.py --describe
```

Explicit execution, after preparing that fresh world:

```sh
export BLOCKWIRE_CONFIG=/absolute/path/to/owned-instance/minecraft/config/blockwire/settings.json
PYTHONPATH=python/src .venv/bin/python examples/stone_tools_benchmark.py \
  --confirm-fresh-survival-world \
  --player-uuid YOUR_ACTUAL_PLAYER_UUID \
  --world-id fresh-stone-tools-001 \
  --output /mnt/4t/blockwire/benchmarks/stone-tools-001
```

The output directory must **not exist**, even if empty. The selected connection
retains mandatory TLS, per-instance trust, hostname verification and API-key
checks. There is no gateway/server launch, seed selection or credential copying.
The default configured address is still loopback. No Minecraft process is opened
by `--describe` or by importing the example.

## Failure, evidence and acceptance

`SIGINT`/`SIGTERM` request cooperative cancellation, including the active BCL runner
and search. F8 remains the independent native stop. Deadline/cancel checks precede
actions and occur in loops; existing actor-fenced skills own input cleanup. Every
failed BCL frame stops the whole benchmark. No automatic reconnect, replay,
respawn, emergency ascent or repair/closure of a partial crafting grid/cursor.
A stopping player can therefore remain underground; damage avoidance is best
effort, not immunity or a guaranteed escape.

The new private ledger contains exclusive, fsynced intents before dispatch,
per-frame BCL results/SQLite journals, perception samples, descent/mining/return
records and `result.json`. Used ledgers and runtime objects cannot be resumed.
Unknown errors/transport or unconfirmed release remain terminal
`unknown_no_retry`; a successful operation is not itself benchmark success.
Directories contain identities and locations and must not be distributed.

Exit zero requires the script's observed benchmark postconditions. This is
**client-observed evidence**, not native graphical qualification, natural-tree
provenance, server authority, world-save integrity or an independent closed-save
mining/statistics audit. A real benchmark needs an isolated graphical run, source
freeze and independent final inventory/mining/return/cleanup reconciliation before
claiming gameplay success. Current checks: **855 Python tests PASS**, Gradle
`check` PASS, **10 TLS checks PASS**, and **277 isolated mutations killed**
(18 benchmark/recipe, 209 skill and 50 BCL regressions). Tests and implementation evidence are recorded in
[`evidence/stone-tools-benchmark.json`](evidence/stone-tools-benchmark.json).
