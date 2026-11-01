# Blockwire Python

Development project API: `blockwire.projects.ProjectJournal` stores strict
model-authored plans and reconciled native evidence in the existing private
SessionStore; `blockwire.project_agent.ProjectAgent` supplies bounded persistent
context over the existing BCL TLS SDK. Start with offline
`python examples/project_agent.py --describe` from the repository root and
[project contracts/limits](../docs/projects.md). BCL I4 mechanically places one
model-selected voxel via observed supports and the existing I3 motor; no house
sequence or additional player controller is introduced.

Program real-player scripts with `Bridge` + `Player`, or expose descriptive
MCP tools through `blockwire-mcp`. Set `BLOCKWIRE_CONFIG` to the private
instance settings file; the adapter reads its IP, port and API key. Native menu
navigation is available before joining a world when config auto-start is enabled.
See the repository README and docs.

BCL/1 adds an offline typed compiler (`python -m blockwire.bcl`), declarative
skill-derived command/setting/event metadata and per-session modal state. The
optional `blockwire.bcl.gateway` exposes an explicitly started, authenticated
loopback TLS WebSocket; `blockwire.bcl.client.BCLClient` is a transport SDK, not a
second controller. MCP adds compile/execute/discovery and reuses existing
status/cancel. See [BCL specification](../docs/bcl.md) and the generated reference.
No gamemode/cheat or automatic reconnect/replay. Gateway TLS material and native
Minecraft connection credentials are separately operator selected.

The `blockwire.skills` package adds declarative goals, strict schemas, cooperative
background jobs and explicitly selected provider extensions. `Player.walk_to(...)`
uses loaded flat full-block ground by default; `terrain=True` opts into bounded
observed full-block diagonals, one-block steps and proven short gaps. General
uneven terrain remains unsupported. `Player.approach(...)` approaches an initially
visible interactable without opening it. Explicit `Player.autopilot(...)` adds
bounded travel and opt-in reactions. These paths share the native-feedback motor, short actor-fenced input leases and
one native elapsed-time camera controller. `Player.look(...)` preserves immediate
behavior when timing is omitted; `duration_ms=1..5000` plus optional
`rotation_profile="linear"|"smoothstep"` schedules a bounded actor-fenced plan.
Scheduling is not completion; observe terminal orientation. Use the matching rebuilt mod for the new
observation/settings features; the SDK is installed separately. Development builds also provide
`blockwire-play2code` to validate/export a sealed passive local-human recording into raw evidence and
ordinary compiling BCL/1 batches; it never starts recording remotely or executes replay. Read
`docs/play2code.md`, `docs/skills.md` and `docs/extensions.md` in the project for limits and contracts.

Development SDK 0.2.0a6 provides `Player.fight(reactions={"zombies":"fight", "creeper":"evade"})`
and the matching MCP `fight` job. See `docs/fight.md`; native hits and limited
observations are not kill/safety guarantees. Alpha.3 mod primitives are sufficient.
The a5/a6 optimization adds bounded `melee_wait_seconds=3` (0 preserves immediate
blocking), one-job knockback/visibility recovery and lower cooldown query overhead.
A6 finished a previously engaged Normal zombie in one native job after recovering
visibility/range gaps (`docs/evidence/fight-visibility-live.json`). Fresh full-health,
group and Hard acceptance remain unverified. Earlier a5 visibility stops are
retained. In the prior a4 test, one Normal zombie died
during a supervised wooden-sword sequence across repeated
melee jobs (`docs/evidence/armed-zombie.json`); this is not autonomous/general
combat acceptance. Earlier unarmed failures remain in `docs/evidence/fight-maps.json`.

SDK **0.2.0a7** also provides standalone `setup(bot)` / `loop(bot)` controllers
and normal `asyncio.TaskGroup` concurrency for walking plus eating. Requires the
**alpha.4 mod** (independent native key leases and guarded hotbar selection).
Run `python examples/controller.py X Y Z --food-slot 8` from the repository,
or explicitly select an installed controller with `blockwire-run NAME`.
See `docs/controller.md`; new concurrency gameplay acceptance is NOT RUN.
No MCP/model is needed; existing synchronous APIs stay available.

The development checkout also exposes `Player.command("/time set day")`,
CLI `blockwire command '/time set day'`, and MCP `run_command`. Requires the
matching rebuilt mod. This is explicit native slash-command submission with server
permissions, not OP/cheats elevation, host shell execution or a success result.
Commands can irreversibly change worlds; no output capture or automatic retry.
See `docs/commands.md`; graphical command acceptance is NOT RUN.

The development checkout adds `blockwire-agent` / `python -m blockwire.agent_cli`:
an explicitly configured external LLM chooses strict existing skills above a
bounded, cancellable per-agent SQLite runtime. Native crafting/equipping/placement
have limited live evidence; full stone progression, food supply and farming do not.
No implicit cloud connection or automatic respawn/reconnect. The new strategic
runner currently uses POSIX file locking; Windows is unsupported for that runner.
See `docs/autonomous-survival.md` for activation, state/identity safety and honest
acceptance gates. It is not a completed/unattended Survival bot.

The Python package does not embed Python into Minecraft. Scripts run outside the
game. `Backend` / `CallableBackend` allow trusted in-process integrations to
reuse the actor API; no server entity or fake-player implementation ships yet.
