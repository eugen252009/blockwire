# Optional algorithmic autopilot — experimental

Autopilot is a deterministic Python state machine, not a model or an embedded
Minecraft AI. It is registered as a skill but **never starts automatically**.
Selecting the skill explicitly activates one bounded job. Minecraft and the
Python/MCP host must both remain running; no autonomous behavior survives host
shutdown/reconnect. There is no persistent enable flag.

```
Minecraft bounded observations -> Python behavior controller <- API <- MCP/Python
Minecraft native player inputs <- existing authenticated TLS API <- controller
```

The same SkillManager owns travel and reactive behavior; there are no competing
movement/combat workers. F8 remains an independent local endpoint stop. TLS,
authentication, native physics and existing input leases are unchanged.

## Activate

MCP convenience tool (also available as `run_skill("autopilot", parameters)`):

```json
{
  "destination": {"x": 12.5, "y": 64.0, "z": -8.5},
  "movement": "run",
  "combat": "defend",
  "evade_creepers": true,
  "duration_seconds": 20.0,
  "timeout_seconds": 30.0
}
```

`autopilot` returns a background job ID. `skill_status(job_id)` exposes current
`behavior`, position and selected policies. `cancel_skill(job_id)` disables it
cooperatively; poll until terminal status confirms cleanup before taking control.
`stop_inputs` requests cancellation and releases current held input. Do not assume
that a cancellation request alone has stopped an already in-flight native action.

Python synchronous convenience:

```python
with Bridge.from_env() as bridge:
    player = Player(bridge)
    result = player.autopilot(
        destination={"x": 12.5, "y": 64.0, "z": -8.5},
        movement="run", combat="defend", evade_creepers=True,
    )
```

For background Python activation/cancellation, use the public `SkillManager`:

```python
from blockwire.skills import SkillManager, default_registry

jobs = SkillManager(default_registry(), player)
job = jobs.start("autopilot", {"evade_creepers": True})
print(jobs.status(job["id"]))
jobs.cancel(job["id"])  # Poll until terminal before closing the connection.
```

Synchronous/direct Python callers must coordinate exclusive control themselves;
MCP rejects raw mutating tools and additional jobs while a job owns the actor.

## Parameters and behavior contract

- `destination`: optional strict `{x,y,z}` world position, same flat level,
  at most 64 horizontal blocks from activation. Omit for stationary monitoring;
  it does not wander, but selected reactions may move the player.
- `movement`: `walk` (default), `run`, or `sneak`. Native sprint eligibility,
  hunger and game rules still apply; run requests sprint, not a guaranteed speed.
  Final waypoint centering slows to sneak in every mode. Ordinary travel uses the
  shared [feedback motor](motion.md): hold W during observations/small steering
  on known straight segments with 4–8-tick native leases; stop for larger turns,
  short/uncertain routes and precise arrival. Creeper evasion retains unstaged
  camera alignment and short pulses rather than gradual travel turns.
- `combat`: `off` (default) or `defend`. Defense means **proximity defense**, not
  proof of who attacked: it faces a visible client-known Monster within 3 blocks
  and submits a native attack only if the refreshed crosshair matches. No pursuit,
  player targeting, equipment selection, ranged combat or creeper attacks. Attack
  attempts are spaced at least 0.6 seconds; native cooldowns still apply.
- `evade_creepers`: strict boolean, default false. Any reported creeper has
  priority over defense/travel. Choose a hazard-free connected cardinal neighbor
  whose center increases distance from every reported hostile. Revalidate each
  pulse; refuse a recentering waypoint that approaches a reported hostile. If no
  supported escape is known, return blocked rather than walking blindly backward.
  Evasion requests running even if ordinary travel uses walk/sneak. After reported
  threats disappear, normal travel/idle resumes.
- `duration_seconds`: 0.1–120, default 20. Caps activity. Without a destination,
  completion means only that the monitoring period elapsed, **not that fighting
  succeeded or the player was safe**. An uncompleted destination returns timed_out.
- Inherited `timeout_seconds`: 0.1–120, default 30, cooperative overall deadline.
  The earlier duration/deadline wins. No automatic renewal or retries.

Known hostiles that cannot be handled by the selected policies block the job.
Health loss/fire, unsupported geometry, loss of grounding, screens/pause, stuck
movement, actor replacement and transport errors terminate control. Activity is
also bounded to 64 blocks from activation, including evasion. Native look/drive
always carry `actor_session`; guarded attacks additionally check the expected
native crosshair entity, current world membership, line of sight and a 3-block
range on the game thread before submitting input. Cleanup always attempts release;
unconfirmed final release cannot yield success.

## Limits and qualification

Only loaded flat full-block geometry is supported. No jumping, stairs, swimming,
chunk generation or global threat-aware route planning. A persistent threat may
prevent arrival or cause repeated evade/travel transitions until the active period
ends. Off-center positions, multiple threats or narrow terrain can block evasion.
The nearest 16 client-known Monsters within 8 blocks are an incomplete threat
model: no projectile prediction, fuse prediction, modded hazard completeness or
no-damage/no-death guarantee. Python/network/render latency can be too slow to
escape an explosion. Do not use this as an unattended safety system.

The mod and SDK must both be updated: old observations without `threat_profile`
are rejected before control. No transport downgrade or extra trust enrollment is
introduced. The existing `walk_to` planner and conservative movement policy are
unchanged; navigation now supplies typed, nearest-hostile details.

Deterministic tests in `python/tests/test_autopilot.py` cover AP01–AP12: explicit
activation, movement/arrival/detours, priority/resumption, escape geometry/hazards,
defense target selection/rate, strict validation, lifecycle/cleanup, cancellation,
argument preservation, MCP ownership/status/cancel, unsupported observations,
and late native actor/target rejection without automatic retry.
Native protocol target guards have Java contracts. Targeted isolated Python and
Java mutations exercise opt-in, identity, hazards and movement selection.

Original autopilot feature verification (historical; current motor checks are in
[motion.md](motion.md)): Replay scope remains limited to the listed components.

| Check | Result |
|---|---|
| Python unit contracts (including mocked MCP facade) | PASS: 43 tests |
| `./gradlew check --rerun-tasks` | PASS: 67 transport/protocol + 19 TLS checks |
| Isolated Python / Java mutations | 11 / 8 KILLED |
| Real Netty-to-Python TLS interoperability | PASS: 10 checks |

Logs are local under `build/autopilot-verification/`; they contain no live game
acceptance. Reproduce with the commands in [verification](verification.md), plus
`tests/run_skill_mutations.py` and `PYTHONPATH=python/src .venv/bin/python tests/tls_interop.py`.
Set `BLOCKWIRE_VERIFICATION_DIR` to a new local evidence directory when rerunning
mutation/TLS checks; use the MCP-enabled Python environment for facade coverage.

**Live graphical Minecraft autopilot/combat/creeper acceptance: NOT RUN.**
Planner fixtures and mocked MCP tests are not gameplay evidence. Existing walking
and TLS evidence is historical/scoped; it does not qualify these new behaviors.
