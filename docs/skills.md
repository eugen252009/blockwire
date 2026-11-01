# Descriptive goals — 0.2 alpha

[Persistent projects](projects.md) combine these existing motors under typed
model-authored goals and independent native observation/reconciliation. No house
progression skill is added. Explicit-support `place_block` can return a fresh
already-correct postcondition without use/consumption; ordinary full-cube planks
share its native verified placement path. Opt-in positioning reports known native
candidate poses separately from current graph reachability, without inventing
scaffolds or a route. `place_at` / BCL I4 selects neighboring observed supports and
faces for one requested voxel and delegates that same motor; it does not choose
what to build. Placement adapters retain a precise centred valid current pose or
request a settled, slightly inset standing pose with a 0.15-block radius; this
prevents a coarse-but-valid walking arrival from leaving the exact support face
occluded.
ordinary walking keeps its 0.3-block default and does not implicitly crouch.
`gather_block(position=..., count=1)` / `C2 ... P` filters ONE already exposed
native target; it does not query hidden coordinates. Terrain harvesting may make
one pickup approach only into fresh safe reachable same-height geometry; success
still requires actual inventory gain, not an arrival receipt. These shared motors
are exercised by the [opt-in building benchmark](superflat-building.md).
`remove_block` / C3 reuses the same guarded mining motor for ONE exposed full
cube, but proves fresh native body/head clearance rather than promising pickup.
C2 remains a resource goal with mandatory inventory gain. Existing actor fences
and cleanup remain.

Behavior is retained in Blockwire; [rename compatibility](rename.md) records the
current packaged smoke. The skill-specific manifest below is the preserved pre-rename baseline.

Low-level inputs remain available. The new layer describes **what to achieve**:

```python
with Bridge.from_env() as connection:
    player = Player(connection)
    result = player.walk_to(12.5, 64, -8.5, sneak=False, avoid_damage=True)
    assert result["status"] == "succeeded", result
```

CLI:
```sh
blockwire skills
blockwire walk_to 12.5 64 -8.5 --timeout 30
# Explicitly less conservative:
blockwire walk_to 12.5 64 -8.5 --allow-damage
```

MCP:
1. `list_skills` — descriptions + strict parameter schemas.
2. `walk_to(...)` or `run_skill("walk_to", {...})` — start a background job.
3. `skill_status(job_id)` — progress and terminal result.
4. `cancel_skill(job_id)` — request cancellation; poll for confirmed terminal cleanup.
   `stop_inputs` also requests cancellation and releases current input.

Raw mutating MCP actions are rejected while a job owns control. Read observations
and status remain available. History retains the newest 20 jobs. Existing input
deadlines and F8 are independent of the Python worker. Extensions are opt-in
trusted host code; see [extensions](extensions.md).

## Estimate distance to an observed block

`player.estimate_distance("minecraft:dirt")`, CLI `blockwire estimate_distance dirt`,
or MCP `estimate_distance` measures a block from one current bounded observation.
It is read-only and never claims/releases movement ownership. An optional exact
position only filters observed candidates; it is not a coordinate lookup. Cached
renderer hits, hidden terrain and old sightings are not accepted. Horizontal
range and height are separate. The tool computes no fall damage or survival
prediction; the caller handles risk reasoning and landing safety remains unknown. See [distance estimation](estimate-distance.md).

## Approach a visible target

`player.approach("chest")`, CLI `blockwire approach chest`, or the MCP `approach`
tool chooses a matching initially visible interactable with a supported local
route, walks beside it, re-observes, aims and checks the exact native crosshair
block before success. Travel primarily faces forward and uses W; A/D is limited
to tiny aligned corrections. An out-of-view target is rechecked at bounded stopped
checkpoints, not by keeping the camera locked onto the chest. On eligible straight
segments the shared [feedback motor](motion.md) holds W during observations and
small steering updates instead of stopping after each update. Camera changes use
one actor-bound native elapsed-time plan (normally 200 ms smoothstep), not Python
8° stepping; turn/drive overlap requires fresh broad lateral support. It never
opens/uses the block or moves items. An optional
strict integer `position=[x,y,z]` selects an exact visible match, not a world query.
See [approach](approach.md) for selection, parameters, status/cancel and limits.
This is Python-only on top of the visibility-capable mod; reload the MCP server.
Isolated graphical acceptance of the new skill remains **NOT RUN**.

## Optional autopilot

`autopilot` is an explicitly activated, time-bounded deterministic skill for
walk/run/sneak travel or stationary monitoring, with opt-in proximity defense and
creeper evasion. It uses the same background status/cancel and actor ownership.
See [autopilot](autopilot.md) for strict parameters, precedence and limitations.
It is experimental: graphical combat/evasion acceptance is **NOT RUN**.

## Per-mob fight policy (development SDK 0.2.0a6)

`fight(reactions={"zombies":"fight","creeper":"evade"})` starts one explicit
bounded job; each of zombies/skeletons/spiders/creeper accepts fight/evade/ignore.
`melee_wait_seconds` defaults to 3 (0–5): retain the job without movement for
out-of-reach/other-level or temporarily invisible targets; zero preserves immediate blocking. Native
actor/target/health/equipment gates and cooldown spacing are unchanged.
Evade wins. Use the selected sword/axe; unarmed fighting requires explicit opt-in.
Actor/native-target guards, flat-ground motion, health limits and cancellation
remain mandatory. Observed disappearance is not a confirmed kill. See
[fight](fight.md). A6 recovered visibility/range gaps and finished a previously
engaged Normal zombie in one job ([record](evidence/fight-visibility-live.json)).
This is not fresh full-health/group/Hard acceptance; earlier a5 visibility stops
are [retained](evidence/fight-optimization-live.json). In a prior a4 test,
one Normal zombie died in a supervised wooden-sword sequence
across repeated melee jobs ([evidence](evidence/armed-zombie.json)); this is not
single-job/general combat acceptance. Earlier unarmed failures are
[retained](evidence/fight-maps.json).

## Native resource skills and strategic runtime

The development registry also includes `craft_item`, `equip_item`,
`interact_with_block` (workbench only), restricted `place_block`, local
`gather_block`, and stationary `consume_item`. These reuse native inventory/input
operations, require actor fences and independently observed outcomes. Crafting is
a finite recipe catalogue, not an automatic progression script. Food consumption
requires both hunger gain and fewer food items; it is not food acquisition.

The opt-in [strategic runtime](autonomous-survival.md) lets an external LLM select
these existing skills, with private bounded per-agent memory, durable non-replayed
intents, typed decisions, cancellation and fresh verification. One real mailbox
LLM slice replanned after blocked stone access and crafted/equipped a wooden hoe;
full fresh-world stone/food/farm acceptance and 24/7 operation remain NOT RUN.
See that document for the per-skill evidence table and explicit missing primitives.

## Standalone controllers

SDK a7 with mod alpha.4 adds a small async `setup`/`loop` runner without MCP.
It reuses this walker through a scoped input adapter, so `walk_to` and conservative
native `eat` may coexist. Other skills retain exclusive resource ownership.
It does not remove the MCP/global actor lock. See [controller API and limits](controller.md);
real-client concurrency acceptance is NOT RUN.

## Play2Code is not a skill

[Play2Code](play2code.md) passively records local human input and exports source for
existing BCL skill adapters. It is not registered in `SkillRegistry`, never claims
actor ownership and cannot be started remotely. Replaying exported M0/I1/I4/C3
still invokes these same skill contracts, actor fences, cancellation checks and
observed postconditions; the recording itself grants no authority or success claim.

## BCL/1 adapter and additive movement mode

[BCL/1](bcl.md) compiles compact commands, modal settings and event subscriptions
into the existing guarded runtime/skills. It does not implement a new controller
or hard-code progression. M0 maps normal/fast/sneak to the additive
`WalkTo.movement = walk/run/sneak` field (legacy default remains walk); explicit
`sneak=True` retains precedence. Optional native stepped terrain remains opt-in.
See the new BCL scoped evidence rather than extending historical flat-only claims.

## Built-in walk_to contract

Parameters: finite world `x, y, z`; strict booleans `terrain`, `sneak` and
`avoid_damage`; `movement=walk|run|sneak`; `arrival_radius` 0.08–0.3 (default
0.3); `timeout_seconds` 0.1–120 (default 30). Maximum requested horizontal
distance: 64 blocks. Success requires a **client-observed settled** position
inside the requested horizontal radius and 0.2 vertically—not an input receipt or
authoritative server acknowledgement.

Default support remains loaded, flat, full-cube ground with standing headroom.
`terrain=True` opts into bounded observed full-block diagonals, one-block axial
steps and conservatively proven two-cell gap transitions. The shared
[feedback motor](motion.md) uses ordinary W/A/S/D, short actor-fenced leases,
observed-speed braking and separate bounded native step/gap loops. It continuously
replans around known collision obstacles. Slabs, fluids, ladders, doors, digging,
placement, flight, arbitrary collision shapes and generated/unloaded routes remain
unsupported. Unsupported situations return blocked; they do not teleport or
improvise cheats.

The Java `navigation` observation is on demand only:
- Radius 4: at most 81 flat cells, or 405 cells across Y +/-2 with `terrain=True`.
- Native support/headroom/body-sweep checks and typed flat/diagonal/step/gap edges.
- No arbitrary world coordinate query, resource search or block/entity NBT.
- Native velocity/collision/ground state, known hazards and up to 16 nearby
  client-known hostile mobs within 8 blocks.
- A player/world identity token; guarded native look/drive rejects an obsolete token.

This is additional bounded collision knowledge, **not a claim about what pixels
are visible**. The mesh is partial, dynamic and client-predicted. A local planner
can report no known route even if a longer global path exists.

## What avoid_damage means

With `avoid_damage=True`, the walker excludes known hazard cells, refuses nearby
known hostiles/fire, and stops if observed health falls. Sneaking follows `sneak`
independently; crouching is not general damage protection. With `avoid_damage=False`,
known hazard cells may be used; unsupported fluids/terrain remain unsupported.

The fixed Minecraft 26.3 [movement benchmark](movement-benchmark.md) retains 211
repetitions across 49 scenarios. The preserved controller passed 176/211 and the
final controller passed 211/211 at the unchanged 0.3-block Blockwire radius.
This is deterministic fixture qualification, not general Survival acceptance.

**It never guarantees no damage or death.** Unknown/modded hazards, projectiles,
server corrections, chunk/terrain changes, latency and incomplete observations
can invalidate assumptions. It is not an invulnerability feature or a replacement
damage engine. Failure, damage, changed actor, loss of grounding, stuck movement,
deadline and cancellation terminate the task and trigger input cleanup.

The native session fence prevents queued old-world look/drive from affecting a
replacement player/world. It does not make terrain snapshots atomic. User-supplied
trusted extensions must preserve that fence and their cooperative cancellation.

## Current evidence / limits

- Deterministic unit fixtures cover routing, steering, speed braking, stable
  arrival, hazards, unknown ground, steps/gaps, actor replacement,
  stuck/timeout/cancel and cleanup. They are not Minecraft acceptance by themselves.
- The native benchmark uses end-of-client-tick telemetry and independently settled
  endpoint predicates; failed intermediate cohorts remain retained.
- Real TLS/MCP jobs still reject competing raw control, remain observable and
  cancellable, and release movement. Stale actor tokens are rejected.
- The historical movement gates include 440 Python tests, Gradle contracts, ten
  TLS checks and 227/227 killed applicable mutations. The post-rotation 211/211
  movement rerun and fresh 71/71 building regression have separate retained gates
  in [rotation-benchmark.md](rotation-benchmark.md).
- Natural uneven terrain beyond the declared full-block transitions,
  two-client dedicated-server walking, projectiles, hostile Survival and modded
  hazards remain unqualified.

See [movement evidence](evidence/movement-benchmark.json) and the older scoped
[skill evidence](evidence/skills.json). Test worlds, snapshots and private
connection material are not included in distributable bundles.
