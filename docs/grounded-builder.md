# Grounded Creative builder — experimental execution candidate

This follows the **compiler-only** milestone in `schematic-compiler.md`. That
milestone, its evidence, source schematic and generated preview are unchanged.
The new candidate supplies an execution path; it is **not a qualified house
builder**. No Minecraft client/world was started for this implementation.
Graphical acceptance, including the supplied 658-state house, is **NOT RUN**.

## Scope and entry point

`python/src/blockwire/grounded_build.py` is an explicitly invoked Python goal
orchestrator. It uses the existing guarded walking motor and native mechanics,
not an LLM, commands, direct world writes, teleportation, flight or schematic
paste. Existing BCL, Play2Code, MCP discovery/authority and Survival placement /
material-consumption contracts are unchanged. This first candidate is an
operator-local CLI/library, **not a newly registered MCP skill or BCL opcode**.

Installed entry point: `blockwire-build`. Offline usage information:

```sh
PYTHONPATH=python/src .venv/bin/python -B -m blockwire.grounded_build --help
```

Execution requires a selected `.litematic`, `--confirm-creative-build`, explicit
`--origin X Y Z`, `--player-uuid`, `--world-id` and **nonexistent** `--output`.
The origin is the minimum occupied corner, not the padded selection origin.
`world-id` is an operator audit label, **not authenticated save identity**.
Neither the old preview origin `(0,0,0)` nor compilation authorizes a build site.
A matching new mod build, an explicitly authorized Creative client/site and
applicable resource/storage/isolation gates are prerequisites for a live test.
The CLI does not install mods, start/select worlds or resume the paused Survival
benchmark. No existing run directory, even an empty one, can be reused.

Scaffolds require **`--allow-scaffolds`**. Default/max scaffold budgets are
128/256; the permitted X/Z margin is 3 blocks by default (1–8). Work is bounded
by 1,024 desired voxels, the work area, 64 blocks from the initial pose, 100,000
working RPC admissions (excluding stop/cleanup), bounded candidate preparation
and navigation loops, and one 10–7,200-second deadline (default 1,800). The
cooperative cleanup reserve is separate; RPC transport timeouts still apply.

## Execution and outcome checks

* Native live UUID, actor session, dimension, Creative mode, no flight/elytra/
  passenger state, compatible data version and health are checked. Every walking
  look/drive retains `actor_session`; its additional `grounded_creative` guard
  restricts movement to ≤8-tick leases, without attack/use. A rising jump is
  refused while airborne or while vanilla's double-tap-flight timer is nonzero.
  No abilities, jump timer, position or physics state is modified directly.
* Material selection uses the native Creative search tab, native character input
  and native slot **SWAP**. The builder reserves an initially empty hotbar slot,
  checks its subsequently owned contents, rejects dirty cursor/crafting grids,
  and verifies a 64-item stack. It never supplies custom stacks, NBT or `/give`.
* Python chooses standing poses and routes from fresh native full-block stepped
  navigation, excludes gap-jump edges, uses ordinary walking/bounded steps, waits
  for a completed same-actor camera plan, then checks native placement prediction.
  Grounded settling checks horizontal velocity; ordinary gravity Y velocity is
  not treated as flight or motion requiring correction.
* Placement is native `useItemOn`, into **loaded literal air**, within the actual
  dimension height/border. Pose/ray/material/prediction tokens are revalidated
  immediately before submission. A receipt is not success. Newer client-tick
  state readbacks must confirm the effect; Creative consumption is not accepted.
* Logs/wood retain axes; stairs retain facing/half; doors are paired placement
  groups with optional native opening. Stair shapes and pane connections are
  verified after neighbors and scaffold removal, rather than silently normalized.
* Temporary **cobblestone** is allowed only outside desired voxels, within the
  authorized area, with a freshly observed reachable full-floor standing cell.
  Each scaffold has a pre-action support/pose plan and an observed placement
  ticket. Cleanup is descending-Y, with fresh routes/rays; only recorded,
  unchanged owned cobblestone can be broken, never the actor's own support.
  Removal needs newer-tick observed air, not a mining receipt. Changed or
  unreachable scaffolds stop the run; there is no emergency rescue/removal.
* Success requires all positive target states, all owned scaffolds absent, a
  grounded return to the initial pose, and same-actor newer-tick release evidence
  with all-false inputs and no remotely owned controls. These are sequential
  **client-known** checks, not an atomic server/save certificate.

## Native boundary: `creative`, profile `grounded_creative_v1`

`Player.creative(action, actor_session=..., **parameters)` validates an exact
request schema. Every native request requires the actor token and grounded,
settled Creative player. Supported actions:

| Action | Additional fields | Meaning |
|---|---|---|
| `probe` | none | Native player-eye interaction ray, capped at three blocks; selected hit/destination must be loaded; full state and conditional placement prediction. |
| `material` | `item`, `slot`, `expected_item`, `expected_count` | Native Creative catalog selection with asserted prior slot contents. |
| `place` | `token`, `position` | One predicted normal placement; door upper space must also be air. |
| `remember` | `token`, `position` | Watch one currently ray-hit block; does not confer removal ownership. |
| `check` | `ticket` | Read only the previously admitted one/two positions, loaded and within 64 blocks. |
| `toggle` | `token`, `position`, `open` | Native interaction with a ray-hit spruce door. |
| `remove` | `ticket`, `token`, `position` | Native Creative break of a recorded owned cobblestone placement. |

Tokens bind pose/ray/state, and placement additionally binds material/prediction.
Watch tickets are bounded to 4,096 per actor/connection, reset on disconnect/F8
or actor/world replacement; ordinary control release does not erase them.
`check` explicitly reports `visual_observation:false` and
`source:explicit_client_known_watch_v1`: these observations may be occluded and
are **not** an expansion of coarse look/search visibility. There is no arbitrary
coordinate scan, block-entity contents, save reading or remote world mutation.
Native removal provenance is the controller's accepted placement attempt plus
Python air-before/effect-after checks, not independent multiplayer attribution.

## Failure, evidence and limits

The run directory is private (0700), files 0600. Parent/directory entries and
intents are fsynced before effects. `plan.json` remains a compiler specification
with `execution_ready:false`, not an executable uploaded plan. The runner
recompiles the selected schematic itself. `journal.jsonl` records admissions,
observations and scaffold plans; `result.json` is finalized by a hashed
`FINISHED.json`. Missing finalization is not success or permission to resume.

Cancellation/deadlines are checked before actions and in loops. No further
construction or scaffold removal is attempted after cancellation. Owned controls
are released and checked even after ordinary failures; a lost transport is
latched, the original Bridge socket is pinned, and cleanup cannot reconnect.
Unverified effects, interrupted RPCs or unconfirmed release retain
`unknown_no_retry`. Failed placements are not retried. Read-only inspection of
other candidate poses **before** placement is not uncertain-action replay.
Unknown outcomes can leave uncounted changes; `known_owned_scaffolds_remaining`
is not a claim that no other uncertain scaffold exists.

The access heuristic is conservative and incomplete. It does not synthesize a
complete certified scaffold/return schedule for arbitrary geometry, walk on all
partial shapes, clear source-air interiors, replace occupied cells, repair
mistakes, restore an old world, or guarantee recovery/access from every site.
Previously present multi-block doors can stop on incomplete pair evidence.
Strict version/state/geometry checks may stop a partially completed structure.
Scaffolds may remain on cancellation, deadline, unsafe access or uncertainty.

Contracts use a small independent voxel fixture with **mocked walking, Creative
GUI and placement**, plus native parser/state/policy and explicitly labelled
static wiring/API-signature checks. They do not execute GUI mixins or qualify
native flight avoidance, stair/door placement, scaffold routes, complete-house
success or performance. See `evidence/grounded-builder.json` for checks and scope.
