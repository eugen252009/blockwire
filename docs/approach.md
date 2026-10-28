# Approach a visible interactable

`approach` is an explicitly dispatched Python skill, also exposed through MCP and
CLI. It discovers an interactable from the existing bounded visibility snapshot,
walks to a supported standing position **beside**, not inside, the target, aims,
and checks the native interaction target. It **never opens/uses/attacks**, moves
items, changes hotbar or enables autopilot.

## Usage

```python
with Bridge.from_env() as bridge:
    player = Player(bridge)
    result = player.approach("chest")  # minecraft:chest
    # Optional exact selection, only if this block is initially reported visible:
    result = player.approach("minecraft:chest", position=[12, 64, -8], sneak=True)
```

```sh
blockwire approach chest
blockwire approach minecraft:chest --position 12 64 -8 --sneak --timeout 30
```

MCP: `approach(target="chest")` or
`run_skill("approach", {"target":"minecraft:chest"})` returns a background job ID.
Use `skill_status` / `cancel_skill`; `stop_inputs` also requests cancellation and
releases current input. Observations and cancellation remain available; competing
raw mutating tools and jobs are rejected while a job owns control. Direct
synchronous Python callers must provide equivalent exclusivity themselves.

This addition changes **Python only**. With the visibility-capable mod already
installed, no new Minecraft JAR/restart is needed for this skill. Restart/reload
the Python/MCP server (Pi: `/reload`) to discover the new convenience tool/schema.
Older observations without `sampled_surfaces_v1` block before movement.

## Strict parameters

- `target`: exact block registry ID, default `minecraft:chest`. An unqualified ID
  such as `chest` receives the `minecraft:` prefix. This is not translated-name,
  custom-name, category, wildcard or arbitrary code matching; `minecraft:chest`
  does not silently include trapped/ender/modded chests.
- `position`: optional strict list of three integer block coordinates `[x,y,z]`.
  It selects among initially visible matches, not an arbitrary world lookup.
  Hidden or absent positions return `target_not_visible` with no movement.
- `sneak`: strict boolean, default false.
- `avoid_damage`: strict boolean, default true. Like walking, conservative mode
  crouches, excludes known hazards/hostiles/fire and stops on observed health loss.
  With false, crouching follows `sneak` and known hazard cells may be used. Native
  support/collision and lifecycle constraints remain mandatory in either mode.
- `timeout_seconds`: inherited cooperative deadline, 0.1–120, default 30.

Unknown parameters, malformed IDs, booleans as coordinates, nonfinite/coerced
values and unsupported coordinate/deadline bounds fail before game effects.
A valid invocation, including a blocked/cancelled one, always attempts final input
release. Unconfirmed cleanup cannot yield success.

## Selection, motion and success

1. Bracket discovery with native navigation/session observations. Use only
   `visible_interactables`, never compressed surfaces as a traversability map.
2. Order exact-ID matches by current eye-to-reported-aim-point distance, with a
   deterministic position tie-break. Choose the first with a supported **local**
   plan. An exact position override never silently falls back to another target.
3. Search the reachable component of the current bounded collision mesh for a
   standing cell outside the target's X/Z footprint. Its predicted eye is at most
   3 blocks from the reported aim point; this is a conservative planning heuristic,
   **not an assertion about or extension of native reach**. Prefer shortest known
   cardinal paths, then nearest cell centers. Unknown/unsupported cells are not
   invented as standing positions.
4. For distant targets, advance only to a reachable known frontier that is
   strictly closer. Replan from subsequent native meshes. This is not global
   reachability proof: a longer detour can exist even when this local planner
   reports no known approach route. The default selection is therefore nearest
   **locally approachable**, not necessarily the globally nearest reachable chest.
5. Use the shared [feedback motor](motion.md): on supported straight route
   segments keep W held during observations and small steering updates, renewing
   bounded 4–8-tick native leases. Stop for corners/uncertain geometry and final
   positioning, using at most three-tick precision pulses (one tick under 0.35
   blocks from the chosen waypoint). Eight samples without at least 0.01 blocks
   of improvement toward the same waypoint stop as `stuck`, even when moving
   back and forth. Face the route and primarily use W/forward. A/D is allowed only
   for a tiny aligned one-tick correction; no backwards or chest-locked travel.
   Re-observe navigation/visibility before renewal, without a forced look-back.
   If the target is out of view, a bounded checkpoint re-confirms it while stopped
   (see below). A missing/replaced target inside the central view is blocked
   immediately. Never silently switch to another chest. Partial observation/budget
   limits can conservatively block even when the object still exists.
6. At an observed standing destination (horizontal tolerance 0.3, same supported
   flat level), release input, aim with the actor-session fence, allow a rendered
   refresh, then poll up to five fresh observations for the exact native block
   ID **and position**, corroborated by a fresh visible-interactable or on-demand
   `sight_target` match. Only that observation, with the same actor/valid standing
   position, permits `succeeded` / `ready_to_interact`. A look/drive receipt or
   geometric proximity alone never establishes success.

Camera transitions and final aiming use steps of at most eight degrees per
command on the shortest yaw arc. Larger turns have no drive input: navigation,
visibility, actor/readiness and cancellation are sampled again before movement
can resume. Camera turn stages are not counted as failed walking pulses. This
bounds command angle changes, not rendered smoothness under arbitrary frame rate,
latency, human mouse input or other mods.

Progress reports `phase` (`walking`, `turning`, `checking_target`, `aiming`), selected `target`, player `position`,
`standing_destination`, `route_is_partial`, `steps`, `control_mode` and
`owned_input_lease`. The last two describe controller intent, not observed native
keys or gameplay success; steps now count feedback updates. Success details identify
which target was selected, the observed native target and final player position.
Then a separate, explicitly authorized interaction may use/open it. Native server
rules, locks and acknowledgements still determine whether any later interaction
succeeds; this skill does not claim an opened GUI or completed item transfer.

## Bounded target checkpoints

Forward-facing travel can legitimately put the selected chest outside the view.
This user-requested policy replaces the earlier requirement to force the camera
back toward it every pulse. Selection remains bound to the same initial ID and
position; no new world-query RPC or hidden-container lookup is introduced.

- A fresh `visible_interactables` entry or on-demand outline `sight_target` match
  confirms the target. A cached renderer `target` alone cannot reset the budget.
- If the target should be inside the central 45-degree view cone but is absent,
  or a different reported block replaces it at the same position, stop immediately.
- While it is outside view, stop and smoothly aim back to its known position
  before another drive once **8 unconfirmed movement updates (including rolling
  renewals)** or **3 seconds since
  confirmation** is reached. The time threshold is checked between actions; native
  requests/network/game stalls can delay wall-clock checks. The update limit is
  the bounded movement budget, not a promise about physical distance under mods.
- Re-observe and validate actor/readiness/cancel during checkpoint turns. Require
  a fresh ID/position confirmation before resuming. Otherwise return `target_lost`.
  No alternative chest is selected and no use/open action is submitted.
- Navigation, hazards, health, actor sessions, short leases and overall deadlines
  remain checked for every movement stage. Camera-only turn stages do not drive.

This trades continuous target-facing visibility for forward travel with bounded
memory. It does not guarantee that a container still exists between snapshots.
Normal flat-ground/cardinal-route and native safety limitations remain unchanged.

## Safety and limits

Flat, loaded, full-block ground only. No stairs, jumps, swimming, opening doors,
digging, sprinting, placement, teleporting, global scanning or chunk generation.
Initial target selection is limited to 64 horizontal blocks; control stops if
observed displacement from activation exceeds 64. Short native pulses or external
changes can overshoot that observation threshold. Slow crouching, latency,
long routes or repeated observations can exceed
the deadline; 64 is a bound, not a promise of completion within 30 seconds.

Every look/drive supplies the observed `actor_session`; lifecycle/cancel/deadline
checks occur before actions and in loops. Screens/pause, death, unsupported
movement, changed actor/level, known unsafe conditions, stuck movement and loss
of a supported route terminate and release. F8 and native input leases remain
independent safeguards. Avoiding damage remains best effort, never immunity.

Scene and navigation RPCs are separate client-predicted snapshots, not an atomic
terrain/server transaction. Bracketing and native execution fences reject an
observed/queued obsolete actor; they do not freeze terrain between observations.
The selected block identity is only registry ID + position: breaking/replacing a
block with the same ID at the same position is not distinguishable without extra
identity data. The skill neither inspects contents nor acts on a container.

## Contracts and evidence

`python/tests/test_approach.py` covers AR01–AR13: distant/frontier approach,
selection and explicit overrides, discovery/unknown terrain, target loss without
retargeting, exact observed native reach, strict validation, actor replacement,
hazards/damage/holes/stuck, deadline/cancel/cleanup, MCP ownership/responsiveness,
Python/CLI dispatch, lifecycle guards, negative/off-center coordinates and schema
boundaries. Fake geometry includes an independent
bounded slab-ray interaction fixture; it is **not Minecraft acceptance**.

Targeted isolated mutations exercise observed success, exact position, visible
selection override, session checks, target loss, movement policy and forbidden
use. Existing walking/autopilot, registry, transport and TLS contracts remain
applicable. Logs go to `build/approach-verification/` without rewriting earlier
qualification manifests. Current [evidence/hashes](evidence/approach.json) record
57 passing Python tests, 18 killed Python skill mutations (seven approach-specific),
Gradle check and ten TLS interop checks passing, plus actual stdio MCP discovery
of 26 tools and the strict approach schema without making Minecraft calls.

## Live failure and centering correction

The first operator-authorized real-client attempt **FAILED**: movement oscillated
around the starting cell center instead of advancing. The job was cancelled,
cleanup reported `released`, health remained unchanged, and no use/open/inventory
action was requested. This was a user-world smoke, not an isolated acceptance run.

The original fixtures assumed a fixed pulse displacement and detected only tiny
frame-to-frame movement as stuck. A faster-displacement fixture reproduced
alternation between X=0.36 and 0.646 until timeout. Exact real-client movement
attributes/coasting were not measured, so that fixture is a counterexample to the
controller assumption, not a measurement of the installed game physics.

The shared motor now uses single-tick near-waypoint pulses and checks actual
improvement toward each waypoint, not displacement alone. AR14 covers faster
motion convergence; AR15 covers bounded release on persistent oscillation.
At that correction, the component suite passed 59 tests and killed 20 Python mutations,
including reverting each correction. See [motion evidence](evidence/approach-motion.json).
After MCP reload, a second operator-authorized live attempt **PASSED for one
visible chest**: 24 motion pulses, `ready_to_interact`, exact selected/native block
match, cleanup released, health 20→20 and no open menu or use/inventory request.
See [scoped live smoke](evidence/approach-live-smoke.json). **Isolated graphical
acceptance remains NOT RUN.** No arrival guarantee or broader qualification is
inferred from this single user-world smoke; the failed attempt remains recorded.

## Earlier target-facing camera experiment

The same operator smoke confirmed arrival but exposed poor camera behavior:
looking along movement and then directly back at the chest on every pulse caused
rapid alternating rotations. Arrival PASS does not qualify camera quality.

That experiment kept a target-facing camera and used normal eight-way native keys
to retain the intended world-space direction, instead of alternating the camera.
Turns/final aim are subdivided into eight-degree commands; pure turn stages do
not drive and re-sample actor/readiness/visibility before continuing. Default
forward-facing autopilot behavior is unchanged. No Java/input-vector/physics
replacement or new RPC was added.

AR16 checks native-key direction algebra, allowed keys and target-facing bounds;
AR17 checks bounded camera commands and absence of per-pulse turn-back on a
multi-axis route; AR18 checks actor change/cancel during a turn before any drive.
AR19 checks shortest-arc turns across ±180 and unwrapped native yaw observations.
The fake movement model independently handles native-style forward/back/strafe
normalization; these tests are not graphical proof. Component checks: 63 Python
tests and 25 killed skill mutations, including five camera-specific regressions.
After MCP reload, one operator live retest reached and aimed at the selected
chest in 23 motion pulses, confirmed the exact native target, released input,
kept health at 20 and did not open a menu or use inventory. Sparse sampled yaw
changed from about 89° through 45° to 25°; no frame capture was taken, so camera
quality still awaits operator feedback. This does not qualify pixel smoothness.
See [camera component evidence](evidence/approach-facing.json) and the
[scoped live retest](evidence/approach-facing-live.json). Isolated graphical
acceptance remains NOT RUN.

## Forward-facing revision before continuous leases

The operator found the camera smoother but requested forward-facing W travel
instead of A/S/D-heavy chest-facing movement. The current revision removes that
mode, retains bounded eight-degree alignment turns, uses W for route segments,
and restricts A/D to tiny one-tick lateral corrections. Exact final aiming remains
separate. The default autopilot behavior is unchanged.

AR16/AR17 retain direction/allowed-key and bounded-turn/no-per-pulse-look-back
contracts, updated for the explicitly requested policy. AR20–AR25 additionally
cover out-of-view checkpoint travel, bounded missing-target stops, W-only visible
straight routes, actor/cancel guards at checkpoints, the time threshold and stale
renderer-target rejection. The changed target-visibility timing is intentional
and bounded; input/session/hazard/cleanup guarantees are not relaxed.

Component checks at that revision: 69 Python tests and 31 killed skill mutations, plus
Gradle check and TLS interoperability. Implementation itself requested no live
movement. A later operator-authorized live test observed forward-aligned travel
(yaw about 90°, pitch 0°), then **BLOCKED** on `known_danger_nearby` after 8 motion
pulses. Cleanup released, health stayed 20, and no chest/use/inventory operation
was requested. The exact danger source was not identified. This is partial-route
evidence, not arrival success or camera-quality qualification; isolated graphical
acceptance remains NOT RUN. See [component evidence](evidence/approach-forward.json)
and the [scoped live result](evidence/approach-forward-live.json).
