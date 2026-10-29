# Blockwire Python

Program real-player scripts with `Bridge` + `Player`, or expose descriptive
MCP tools through `blockwire-mcp`. Set `BLOCKWIRE_CONFIG` to the private
instance settings file; the adapter reads its IP, port and API key. Native menu
navigation is available before joining a world when config auto-start is enabled.
See the repository README and docs.

The `blockwire.skills` package adds declarative goals, strict schemas, cooperative
background jobs and explicitly selected provider extensions. `Player.walk_to(...)`
supports loaded flat full-block ground only. `Player.approach(...)` approaches an
initially visible interactable without opening it. Explicit `Player.autopilot(...)`
adds bounded travel and opt-in reactions. Approach/autopilot share forward-facing
feedback movement with short native leases. Use the matching alpha.3 mod for the
new observation/settings features; the SDK is installed separately. Read `docs/skills.md` and
`docs/extensions.md` in the project for safety limits and extension contracts.

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

The Python package does not embed Python into Minecraft. Scripts run outside the
game. `Backend` / `CallableBackend` allow trusted in-process integrations to
reuse the actor API; no server entity or fake-player implementation ships yet.
