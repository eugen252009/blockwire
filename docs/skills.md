# Descriptive goals — 0.2 alpha

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

## Approach a visible target

`player.approach("chest")`, CLI `blockwire approach chest`, or the MCP `approach`
tool chooses a matching initially visible interactable with a supported local
route, walks beside it, re-observes, aims and checks the exact native crosshair
block before success. Travel primarily faces forward and uses W; A/D is limited
to tiny aligned corrections. An out-of-view target is rechecked at bounded stopped
checkpoints, not by keeping the camera locked onto the chest. On eligible straight
segments the shared [feedback motor](motion.md) holds W during observations and
small steering updates instead of stopping after each update. It never opens/uses
the block or moves items. An optional
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

## Standalone controllers

SDK a7 with mod alpha.4 adds a small async `setup`/`loop` runner without MCP.
It reuses this walker through a scoped input adapter, so `walk_to` and conservative
native `eat` may coexist. Other skills retain exclusive resource ownership.
It does not remove the MCP/global actor lock. See [controller API and limits](controller.md);
real-client concurrency acceptance is NOT RUN.

## Built-in walk_to contract

Parameters: finite world `x, y, z`; strict booleans `sneak`, `avoid_damage`;
`timeout_seconds` 0.1–120 (default 30). Maximum requested horizontal distance:
64 blocks. Success means a **client-observed** position within 0.3 blocks
horizontally and 0.2 vertically—not an authoritative server acknowledgement.

Supported: cardinal movement on loaded, flat, full-cube ground with standing
headroom; short movement pulses, continuously replanned around known collision
obstacles. No stairs/slabs/uneven terrain, jumping, sprinting, swimming, ladders,
doors, digging, placement, flight, dimension travel or generated/unloaded routes.
Unsupported situations return blocked; they do not teleport or improvise cheats.

The Java `navigation` observation is on demand only:
- At most 81 same-level candidate cells within radius 4, only already loaded chunks.
- Native collision/support checks and swept boxes for cardinal connections.
- No arbitrary world coordinate query, resource search or block/entity NBT.
- Known hazard markers and up to 16 nearby client-known hostile mobs within 8 blocks.
- A player/world identity token; guarded native look/drive rejects an obsolete token.

This is additional bounded collision knowledge, **not a claim about what pixels
are visible**. The mesh is partial, dynamic and client-predicted. A local planner
can report no known route even if a longer global path exists.

## What avoid_damage means

With `avoid_damage=True`, the first walker always uses crouching (even when
`sneak=False`), excludes known hazard cells, refuses nearby known hostiles/fire,
and stops if observed health falls. With it false, crouching follows `sneak` and
known hazard cells may be used; unsupported fluids/terrain remain unsupported.

**It never guarantees no damage or death.** Unknown/modded hazards, projectiles,
server corrections, chunk/terrain changes, latency and incomplete observations
can invalidate assumptions. It is not an invulnerability feature or a replacement
damage engine. Failure, damage, changed actor, loss of grounding, stuck movement,
deadline and cancellation terminate the task and trigger input cleanup.

The native session fence prevents queued old-world look/drive from affecting a
replacement player/world. It does not make terrain snapshots atomic. User-supplied
trusted extensions must preserve that fence and their cooperative cancellation.

## Current evidence / limits

- Deterministic unit fixtures cover routing, obstacles, hazards, holes/unknown
  ground, off-center positions, stuck/timeout/cancel, validation, cleanup and job
  ownership. These are **not Minecraft acceptance**.
- A packaged graphical client in an isolated Creative, Peaceful, structure-free
  superflat test world completed a Python goal and a native hole detour.
- Real TLS/MCP jobs completed arrival, rejected competing raw control, remained
  observable, cancelled and released movement. A stale actor token was rejected.
- The bundled wheel was installed into a fresh environment (not editable source);
  the provider template extracted from the ZIP installed and loaded only with opt-in.
- Survival, natural uneven terrain, two-client dedicated-server walking, projectiles,
  modded hazards, performance budgets and stairs remain **NOT RUN / unsupported**.

See [evidence/skills.json](evidence/skills.json). No Echoes acceptance gate is closed
by this utility test. The test world and private connection material are not
included in the downloadable bundle.
