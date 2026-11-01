# Standalone Python controllers (development SDK a7 / mod alpha.4)

No MCP, LLM, embedded interpreter or custom task language is required. A trusted
local Python program supplies `setup(bot)` (optional, once) and `loop(bot)`.
They may be ordinary functions or async functions. Use standard `asyncio` for
concurrency. Blockwire never starts a script merely because Minecraft starts.

```python
import asyncio
import sys
from blockwire import run_controller

async def setup(bot):
    bot.on("health_changed", health_changed)

async def health_changed(bot, event):
    print(event.data)  # previous/current HP; the cause is unknown

async def loop(bot):
    async with asyncio.TaskGroup() as tasks:
        walk = tasks.create_task(bot.walk_to(12.5, 72, -4.5))
        eat = tasks.create_task(bot.eat(hotbar_slot=8))
    print(walk.result(), eat.result())
    bot.stop()  # Demo: one batch. Omit to run another loop after the cadence wait.

if __name__ == "__main__":
    asyncio.run(run_controller(sys.modules[__name__], duration_seconds=30))
```

**Choose your own known, nearby flat-ground coordinates and food slot.** The
example coordinates are not a destination discovery service. Walking retains
[the existing flat/full-block, 64-block and avoid_damage contracts](skills.md).
Sneaking is explicit; the default blocks on known nearby danger without forcing
crouching. It is not immunity.
Walking while eating is an implemented composition, **not yet real-Minecraft
acceptance**. A [real-client follow-up](evidence/controller-live.json) verified
walking arrival/cancellation, independent lease expiry, hotbar actor fences and
exclusive ownership in the existing Creative/Peaceful fixture. Inventory was empty
and hunger full: **actual food consumption remains unqualified**. `already_full`
is not an eating demonstration. See also [contracts](evidence/controller.json).
Do not run unattended.

## Start explicitly

Build/install the **alpha.4 mod** and SDK **0.2.0a7** in an isolated instance.
Older mods are rejected before setup/gameplay actions: they lack independent
input leases and guarded hotbar selection. Legacy synchronous SDK/MCP inputs
remain compatible with the new mod.

Stop/disconnect an existing MCP bridge before opening a separate standalone
connection: the native endpoint still permits only one controller connection.
Set `BLOCKWIRE_CONFIG` to the selected instance's private settings file; the same
mandatory TLS, per-instance trust, hostname verification and API key apply.
Enable control with the usual local authorization/F8. Join the supervised fixture
manually: this runner does not join worlds, respawn or enable itself.

```sh
pip install -e python
export BLOCKWIRE_CONFIG=/path/to/instance/minecraft/config/blockwire/settings.json
python examples/controller.py 12.5 72 -4.5 --food-slot 8 --duration 30
```

Local programs may pass an explicit `player=Player(backend)` to
`run_controller(script, ...)` or instantiate `Controller(player, ...).run(script)`.
No file/module name from game data is evaluated or imported.

For an **installed** controller package, register the module exposing setup/loop:

```toml
[project.entry-points."blockwire.controllers"]
my_controller = "my_controller"
```

Then explicitly run `blockwire-run my_controller --duration 30 --hz 10`.
Only the selected installed entry point loads; absent/duplicate names fail closed.
There is no startup scan/import, auto-install, remote script loader or mod button
that launches arbitrary host Python. Entry points and directly run scripts are
**trusted, unsandboxed host code** with your OS user's authority. Review them first.

## Small API

- `await bot.walk_to(x, y, z, sneak=False, avoid_damage=True, timeout_seconds=30)`:
  the existing walker, not a second planner. Returns the usual goal-result dict.
- `await bot.eat(hotbar_slot=8, timeout_seconds=8)`: supported food in an explicit
  hotbar slot, not inventory rearrangement. See the conservative limits below.
- `await bot.skill("fight", reactions={...}, ...)`: other built-in skills run
  **exclusively**. They cannot be made concurrent just by removing the old lock.
  This initial runner does not auto-load skill providers or `BLOCKWIRE_SKILLS`.
- `await bot.observe()` / `await bot.inventory()`: read current bounded native data.
- `bot.state`: immutable snapshot of readiness, actor session, position, HP, hunger,
  nearby hostiles and host-monotonic navigation sample time. Capture `state =
  bot.state` for a stable local value; it is not an atomic server snapshot.
- `bot.on(name, callback)`: subscribe a local `(bot, event)` callback.
- `bot.stop()`: request shutdown. Await `run_controller(...)` / `run(...)` for its
  terminal cleanup result. It does not mean the player is safely sheltered.

`loop` invocations never overlap. `hz` (2–20, default 10) sets a minimum cadence
wait **after** each invocation, not a real-time scheduling guarantee. The input/state
watchdog runs at least 10 Hz independently of a slower user-loop cadence. Awaiting
walk/eat in a TaskGroup allows the monitor and callbacks to continue. Use Python
variables/state machines for planning; there is no custom scheduler/priority DSL.
A blocked skill returns a result, not an exception: inspect `status` and `reason`.
A `TaskGroup` still cancels siblings on ordinary Python exceptions.

## Compatible actions and ownership

| Action | Owned resources |
|---|---|
| `walk_to` | movement and yaw |
| `eat` | main hand, hotbar and pitch |
| Other built-in `skill(...)` | all control resources |

Conflicts raise `ResourceBusy` **before input changes**, rather than secretly
queueing/retrying. Await or explicitly cancel/join the competing task first.
Walk/eat use a single serialized input writer. Child completion/cancellation
removes only that child's buttons; it never calls a global native stop. Eating
looks upward while walking retains movement yaw. Ending eating restores the
walking/default pitch. Never concurrently bypass this API with raw `Player` or
backend mutation; trusted host Python is not a sandbox.

The controller claims the entire actor against synchronous skills and MCP jobs
sharing the backend. MCP still has one exclusive job, responsive status/cancel,
and raw-control rejection. `stop_inputs` also requests cancellation of a shared
local owner. A separate process is excluded by the existing native TLS channel
lease. Ownership is retained until registered tasks, skill workers and in-flight
RPCs finish; cancellation cannot safely kill arbitrary Python threads.

Native per-key tick/monotonic leases are at most **8 ticks / 400 ms** per runtime
write. A new walking pulse renews movement; food/heartbeat writes **retain** its
original native deadline/tick budget instead of stretching it. Food's use key can
renew independently. Python stalls therefore cannot turn a short walking pulse
into a food-length hold. F8, disconnect, death, screen/pause and actor/world
replacement still release native inputs. Every look/drive/hotbar mutation is
actor-fenced; the controller never silently rebinds to a replacement actor.

## Eating limits and outcomes

Supported registry IDs: bread, apple, baked_potato, cooked_beef, cooked_porkchop,
cooked_chicken, cooked_mutton, cooked_rabbit, cooked_cod, cooked_salmon (all vanilla
`minecraft:` IDs). Other foods/modded components are not qualified. Offhand must
be empty. The upward native crosshair must be clear, and the selected/held item
must still match. Eating may block under a ceiling. These snapshot checks are
conservative, **not atomic interaction isolation** against a changing world.

Success requires observed hunger gain **and** a reduced/disappeared food stack;
`already_full` requires observed hunger 20. A use receipt alone never succeeds.
Latency may allow multiple items to be consumed. Normal completion restores the
original slot if the selected slot still matches; cancellation/deadline/session
loss does **not** force a hotbar restoration. Only owned inputs are released.
The native game owns consumption, slowdown, collision, damage and server outcome.

## Events, cancellation and failure

Events: `ready`, `health_changed`, `skill_finished`, `death`, `actor_changed`,
`disconnected`, `stopped`. Health changes report only old/new values, never an
invented damage cause. Actor/death events from a native rejection may have unknown
new token/HP (`None`); no hidden query/rebind is attempted.

Callbacks execute serially in the Python host, never on Minecraft's thread. At
most 32 subscriptions and 32 pending ordinary events are allowed. Overflow or a
callback error stops the runner. Async callback waits have a configurable deadline
(default 2 s, .05–10 s). Keep callbacks short; put long goals in `loop`. Terminal
notifications are delivered after cleanup is attempted; they cannot start actions.
Pending ordinary notifications may be discarded at shutdown.

The total activation has an explicit .1–600 s cooperative budget (default 60).
Task cancellation, death, not-ready navigation (including unsupported grounding),
screen/pause, changed actor, disconnect and deadline stop the runner and join owned
actions before final native release. A connection failure is never automatically
retried/reconnected: outcome may be unknown. Cleanup is reported `not_confirmed`
when release cannot be confirmed, never as success. `ControllerResult.status`
describes the runner, **not** successful gameplay goals; inspect each skill result.

CPU-blocking or cancellation-ignoring trusted code cannot be forcibly preempted.
Native leases/F8 remain independent safeguards; game-thread/OS stalls prevent a
hard real-time release guarantee. **Released controls are not safety or survival.**
Arrange supervision and an explicit handoff/save-and-exit policy for real trials.
No automatic respawn, save/exit, shelter building, terrain expansion or unattended
survival is implemented. The contract-phase checks did not resume gameplay; the
later scoped native smoke saved/quit after each active trial and ended at TitleScreen.
