# Architecture

Persistent project follow-up: [projects](projects.md). `ProjectJournal` reuses
`SessionStore`; a strict model-authored plan is separate from pending BCL intent,
terminal operations, observed blocks/native geometry and independently verified
objective. `ProjectAgent` is an external-model orchestration host over the existing
BCL TLS SDK, never another input controller or construction/progression planner.


```
Python script ─ Player(Backend) ─ Bridge ─ authenticated TLS WebSocket ─ Fabric client
                   │                                             │
                   └ CallableBackend(trusted dispatcher)          ├ main-thread observations
                                                                └ native player actions
MCP host ─ stdio MCP facade ─ same Player API ─ same WebSocket
```

The Python path is the programmable actor API plus the `skills` goal layer; the MCP path gives those operations
names, descriptions and typed schemas suitable for an LLM. They are not separate
combat/control implementations. A custom Python backend may address an entity or
scripted actor **only when its provider supplies a legitimate native integration**.
There is no implicit operator elevation, fake player or server agent in v0.1.

## Movement-to-interaction handoff

[Operation-scoped pose readiness](pose-handoff.md) stays inside the existing
Python worker/motor: accepted M0 position, native settling and exact interaction
readiness are distinct conditions. Trusted child positioning may request stance
and an additional arrival predicate; neither is a BCL opcode or a second input
owner. I3 can refine one already authorized local pose, never replay M0 or change
the supplied recording. Existing actor/transport fences and ordinary cleanup
remain mandatory. All stateful reuse defaults remain off.

## Enforcement boundaries

- **Transport:** Minecraft's existing Netty libraries, no shaded WebSocket server
  dependency. A required JDK TLS handler precedes all HTTP processing. A persistent
  self-signed leaf is generated with bundled Bouncy Castle certificate tooling.
  Configured IP bind (loopback default), authenticated upgrade, origin
  rejection, bounded peers, one channel lease, frame/request bounds, queue limit and expiry.
- **Thread boundary:** Network callbacks enqueue on Minecraft's client executor.
  They never read/write a player or menu directly. Closed/obsolete channels are
  rechecked at execution. Ownership is not released until input cleanup runs.
- **Native actions:** key mappings and immediate or elapsed-time view orientation;
  one actor-bound `RotationController`; native attack/use invokers, native
  container input handling, native respawn. No custom server
  packets, damage logic, stack mutation, physics or per-entity scanning tick.
- **Three narrow client mixins:** an accessor interface for the native attack/use
  methods; an input mixin for the global, remappable kill switch and allowing
  bridge-held native mining without a grabbed desktop mouse; and passive
  Play2Code hooks that observe native block-use/mining dispatch without changing
  its result. They do not cancel or replace ordinary interaction behavior;
  bridge-held attack augmentation remains inactive when no bridge attack is owned.
- **Lifecycle:** local config auto-start at CLIENT_STARTED (works before a world)
  or explicit F8 enable; tick + monotonic input lease; player/level
  identity check; generation-gated endpoint cleanup; global release on screen,
  pause, death, disconnect, stop or unexpected dispatcher exception. Natural key
  lease expiry releases input ownership without cancelling an independent camera
  plan.
- **Menus:** bounded widget traversal and one-use screen snapshots. Events route
  through native screen mouse/key/character/scroll handlers with SDL input conversion.
  No direct `onPress` callback or text-value mutation.
- **Observation:** bounded client data, item components summarized, human text plus
  machine-readable fields. Snapshots are not authoritative server outcomes.
  [Extended sight](visibility.md) samples loaded first-hit block surfaces and
  sight-tests bounded client-known interactable positions on demand. A loaded-only
  block getter makes unknown chunks opaque; palette/X-run compression never fills
  unknown gaps. No inventory contents or server scans are involved.

## Optional local settings GUI

The client initializer and native settings screen have no dependency on Mod Menu
classes. A separate `modmenu` entrypoint implements its compile-only API and is
loaded only by an installed Mod Menu. No Mod Menu classes/JAR are bundled.
`LocalSettingsModel` separates read-only status/drafts, explicit runtime toggles
and startup-only persistence. Runtime toggles call the existing F8 lifecycle;
startup saves validate the selected authority and atomically replace only its
startup flag, without touching TLS/token material or current endpoint state.
See [configuration](configuration.md#optional-mod-menu-screen).

## Lean machine boundary

The opt-in [machine-v1 profile](bcl-machine.md) reuses the BCL compiler, journals,
FIFO, native ownership and TLS transport but exposes only small input primitives.
Reporting and interrupt/resume are separate control-plane tasks, not queued BCL
observation/action instructions. The event-fed machine agent and MCP facade offer
strict typed primitives/compositions, with no high-level goal/search/crafting
planner. Separate [search](search.md) perception obtains additional bounded native
rays outside the FIFO; Python pages/validates observations without choosing camera
turns, routes or resources to harvest. `look_around` remains a coarse cached view.
Native physics and internal safety/postcondition reads remain mandatory.
Legacy goal skills below remain available only through the legacy interfaces;
they are not implicitly added to machine-v1. No historical replay is migrated.

## Goal/skill boundary

`SkillRegistry` describes strict schemas; trusted, explicitly enabled provider
entry points register additional goals. `SkillManager` runs one cooperative worker
per actor, with bounded history/progress, status and cancellation. MCP exposes
that same registry and rejects competing raw control while a job runs. See
[extensions](extensions.md) and [skills](skills.md).

The Python-only [approach](approach.md) skill discovers from bounded visible
interactables and plans standing positions from the native navigation mesh, not
from sparse surface samples. It shares a Python [feedback motor](motion.md) with
autopilot: bounded W/A/S/D leases, observed-speed braking, native elapsed-time
shortest-arc rotation, broad-support-only turn/drive overlap and separate native
step/gap loops. It retains actor/session checks and requires
an observed exact native block hit; no opening/use or target-specific Java
controller is needed.

The optional [autopilot](autopilot.md) is another explicitly started Python skill.
One deterministic controller arbitrates creeper evasion, proximity defense,
walk/run/sneak travel and idle monitoring. It reuses the actor/job ownership and
native primitives, not a parallel Java planner. It never auto-starts or reconnects.
Guarded native attacks fence both actor session and expected crosshair entity;
receipts still do not establish a combat outcome.

The walker consumes an explicit on-demand `navigation` mesh (radius 4): at most
81 flat cells, or 405 loaded full-block cells across Y +/-2 when terrain support
is requested. Native code emits conservative typed flat/diagonal/step/proven-gap
edges and motion/collision fields; Python performs geometric-cost receding-horizon
routing and sends short native input leases. End-of-client-tick `MotionTrace`
telemetry is read-only qualification/diagnostic state, not a second controller.
The stack never loads chunks, replaces physics or guarantees safety. Player/world
session tokens fence old observations and every long-running look/drive loop from
replacement actors.

Normal noncombat camera goals use the same native `RotationController`, normally
200 ms smoothstep. It interpolates from the observed current orientation using
`System.nanoTime()` and real client updates, owns no movement key, and exposes
terminal/cancel/supersede state through ordinary observations and tick telemetry.
Omitting timing fields retains the protocol's legacy immediate `look`; combat
camera behavior remains separate and unchanged. See
[rotation qualification](rotation-benchmark.md).

## Strategic LLM runtime boundary

The opt-in [AgentRuntime](autonomous-survival.md) sits above the **same** strict
skill executor and `Player` API. An external `Decider` selects the next goal from
bounded fresh observations; the runtime supplies ownership, compact private SQLite
working memory, typed decision validation, status/cancel and bounded execution.
Recipe data describes native crafting dependencies, not progression policy.
MCP remains discovery/dispatch; the deterministic autopilot is not repurposed as
an LLM planner. No strategy executes inside Fabric.

Native inventory open/close/click now accept optional actor fences while retaining
legacy envelopes. Inventory metadata advertises guarded support, native menu type
and player-index slot mapping. Scene UUIDs bind persistent actor identities. Native
clicks/crafting still own all stack changes; skills require observed inventory and
material postconditions. Partial/uncertain actions are not rolled back or replayed.
No implicit rebind, reconnect or respawn; historical remembered targets are not a
current world map. Windows, complete Survival and long-running operation are not
qualified. See the linked document for activation and remaining acceptance gates.

## BCL/1 interface boundary

[BCL](bcl.md) adds a bounded offline compiler, declarative skill-derived registry
and frozen typed IR. A transactional modal interpreter snapshots settings per
queued operation; the FIFO scheduler invokes **the same AgentRuntime**, strict
skills and native motor. There is no second gameplay controller or progression
planner. `S1 relative` is an ordered runtime homing barrier: it captures one
actor-fenced session home, persists it in the modal journal, and later typed
coordinate parameters resolve from that immutable revision until another S1
transition. Frames/requests never home implicitly. Request IDs prevent replaying
cycles, homes or actions. Private modal journals use SessionStore.

The optional explicitly started Python TLS gateway terminates a separately pinned,
operator-provisioned loopback TLS connection, authenticates its selected token and
forwards compiled operations through the existing native TLS connection. Java's
protocol, identity, F8 and authentication are unchanged. Events use the existing
controller Event data contract and bounded read-only observations. Source/direction
restrictions prevent clients emitting server events. MCP uses the same session/
queue implementation and its existing status/cancel tools. Separate MCP/gateway
hosts must not compete for the sole native controller connection.

## Passive Play2Code boundary

[Play2Code](play2code.md) is a local native observer plus an explicit offline
Python exporter. F9/F10 start/stop a private append-only human-input timeline only
while the remote endpoint is disabled. Interaction mixins observe the existing
native `startDestroyBlock` and `useItemOn` calls; bounded candidate positions are
then checked for stable client-observed state changes. The recorder never owns a
key, camera, hotbar, packet or world mutation, and it performs no background world
scan. Actor/world replacement, death, endpoint activation, remote-owned input,
write limits or shutdown invalidate/stop the capture.

The exporter maps only confirmed evidence to existing M0/I1/I4/C3 contracts and
compiles each ordinary bounded BCL/1 batch with the existing registry. Raw key
and camera timing, airborne motion, unsupported blocks and uncertain interactions
stay explicit unsupported conversions. Generated source is not executed by the
exporter and compilation is not replay qualification. No protocol/MCP/skill/opcode
or second controller is added; replay uses the same guarded runtime and requires a
fresh actor plus independent objective verification. Explicit translation,
reflection and exact quarter-turn derivation happens only in this offline exporter;
it emits concrete ordinary BCL coordinates and never adds a runtime rotation mode.
Recorded M3/M4/M5 paths remain sealed-evidence adapters rather than a second
planner. In particular, an M4 directional sample immediately followed by a hold
sample can be skipped only when both recorded targets are inside the unchanged
arrival radius; otherwise only the already-recorded bounded pulse is available.
No tolerance, retry, synthesized direction or alternate route is introduced.

The experimental `ExecutionOptions` policy belongs to the trusted Python host,
not BCL or Minecraft's wire protocol. It can reuse preparation state only inside
one active `SkillContext`; adapter reuse still obtains fresh inventory and actor
observations, and retained crouch is renewed only after a guarded live observation.
Context closure invalidates both caches before the ordinary cleanup path releases
inputs. It grants no new owner and performs no cross-task lease transfer. All
reuse options remain default-off; current full-replay pilots failed placement-pose
guards, so isolated component successes do not authorize standard activation.
The [baseline-recovery comparison](replay-baseline-recovery.md) reconstructed the
historical runtime byte-for-byte and confirmed a shared-motor contribution to
these failures. An M0 arrival remains distinct from the next I3's admissible pose;
no failed corrective prototype or new arrival-predicate API is part of production.

## Standalone controller boundary

The [async runner](controller.md) executes explicitly supplied local Python or
one explicitly selected installed `blockwire.controllers` entry point. Setup,
nonoverlapping loops, a bounded event queue and standard asyncio tasks live in
the Python host. A single input mixer combines compatible resource owners;
legacy skills execute through an adapter whose stop clears only its own inputs.
The actor remains exclusive against MCP/other skills. Cancellation joins workers
and in-flight requests before ownership reuse, rather than trying to kill threads.

Alpha.4 adds independent lower-only native key leases: food renewal retains the
original movement deadline/tick budget. Actor-fenced hotbar selection and scene
identity close replacement races. These are explicit native authority primitives,
not a Java planner/consumption/physics engine. Transport/F8 bounds are unchanged.
Graphical concurrency acceptance is NOT RUN.

## TLS identity boundary

Each instance owns one private PKCS12 identity and exports only a public certificate.
The Python transport trusts that certificate alone and verifies a fixed logical
service name, so changing bind IP does not require weakening hostname checks.
TLS failure cannot fall back to plaintext or system CA trust. Server authentication
and API-key controller authentication are independent. See [TLS](tls.md).

## Assumptions and non-goals

The local Minecraft process, Fabric, installed mods, OS user and agent host are
trusted. The game thread must run to process/release input. Server rules and
authoritative actions remain outside this client's control. Other mods can alter
native input/combat/container semantics; compatibility must be qualified per pack.

No embedded Python runtime, server-side entity control, arbitrary RPC evaluation,
bundled cloud service or host shell execution. Explicit external LLM adapters are
optional host-side clients, not native telemetry or implicit cloud connections. The explicit [command](commands.md) primitive
submits bounded slash commands through the native client with server permissions;
it does not add a command interpreter or grant operator status. Bounded planning belongs in the
external Python skills layer, not a replacement native movement/combat engine.
The actor API is intentionally small so future providers can implement it without
forcing a transport into their game code.
