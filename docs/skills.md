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
