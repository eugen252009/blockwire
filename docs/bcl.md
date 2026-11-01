# BCL/1 — Blockwire Command Language

Status: development implementation, including modal/event addendum. BCL is an
interface to **existing skills and AgentRuntime**, not a movement/crafting engine
or a Survival progression script. The LLM/caller chooses the program.

## Architecture and authority

```
source → lexer → command registry → strict skill-derived types → immutable IR
       → transactional modal interpreter → one bounded FIFO actor queue
       → existing AgentRuntime / SessionStore / skill executor → Player → native TLS → Minecraft
```

Python/MCP and the optional TLS WebSocket gateway use the same compiler, registry,
modal session interpreter, scheduler and runner. The Java protocol is unchanged.
There is no `eval`, `exec`, Python generation, raw slash-command BCL adapter,
automatic import/install, or alternate physics/inventory implementation.
Trusted host extensions remain **not sandboxed**.

## Grammar (normative)

```ebnf
program  = [ "BCL/1", newline ], { line } ;
line     = whitespace, [ opcode, { whitespace, argument } ], [ comment ], newline ;
opcode   = [ namespace, ":" ], uppercase_letter, integer_opcode ;
argument = value | uppercase_key, [ "=" ], value ;
comment  = ( "#" | ";" ), rest_of_line ;
```

- One command per nonempty line. Blank lines/comments allowed. Header optional,
  unquoted, first noncomment line only; any incompatible version fails closed.
- Core families: M movement, C crafting/resources, I inventory, V view/interact,
  F fighting, S modal settings, E event control/server observations.
- Case-sensitive. Opcodes use one uppercase letter and 0..999, no leading zeroes.
  Keys are single uppercase letters. Namespace is lowercase `[a-z][a-z0-9_.-]{0,63}`.
  Bare `M0` means `core:M0`. Resource IDs are values, **not opcode namespaces**.
- A positional argument number *n* always assigns signature slot *n*, independent
  of named assignments. Named arguments NEVER overwrite values. Thus
  `M0 120 Z30 64` is X=120,Y=64,Z=30, while `M0 X120 64` duplicates X and fails.
  `M0 120 64 30 Ffast` is valid. Unknown keys/excess arguments fail.
- Unquoted uppercase-leading arguments are named; quote a positional string that
  starts with an uppercase key. Examples: `I=...`, `Ffast`, `F="fast"`.
- Strings use JSON double quotes and JSON escapes (`\"`, `\\`, `\n`, `\uXXXX`).
  No single-quote/shell escaping/interpolation. Characters after a closing quote
  without whitespace/comment are invalid. A quoted number is not a numeric literal.
- Integers are signed decimal digits. Floats accept signs, decimal fractions and
  exponents. NaN/infinity, malformed numbers and booleans-as-numbers are rejected.
  Booleans are exactly `true`/`false`. Enum case is exact.
- Resource IDs are lowercase `namespace:path`. Positions/structured values use
  strict JSON, e.g. `M1 P[1,64,3]` or `M1 P="[1, 64, 3]"`.
  Duplicate JSON keys/nonfinite numbers are rejected. Types/limits derive from
  the **existing Pydantic skill fields**, not a copied range table.
- Literal unquoted `null` is valid ONLY for a nullable contract, e.g. `M1 Pnull`.
  `M0 Ynull` is invalid; omitted Y and explicit null are different.
- Bounds: 16384 source characters, 32 operations, 33 tokens/line, 16 parameters
  per signature. No loops, branches, macros or unbounded repetition.

Equivalent movement spellings:

```bcl
M0 120 64 30 fast
M0 X120 Y64 Z30 Ffast
M0 X=120 Y=64 Z=30 F=fast
M0 120 64 30 Ffast
```

Crafting `C0 minecraft:oak_planks 16` means **16 recipe batches**, not 16 output
items. Registry availability is a supported adapter, not a promise that every
resource/mod recipe or current world condition is supported.

## Typed IR and registry

`compile_bcl(source, registry)` returns frozen `Program`/`Operation`/`Binding`
dataclasses. Values are strictly validated and held as immutable canonical JSON;
`to_dict()` emits actual typed JSON values. Each binding has `supplied` plus
`value`: omitted (`supplied:false`) differs from explicit null (`true,null`).
Line/column, stable semantic name, opcode namespace, language version and registry
schema digest are retained. No runtime position/default is guessed by the parser.
Schema drift between compilation/execution fails closed.

Opcode numbers are compact aliases, not implementations. The registry generates
parameter validation, discovery, autocomplete/full JSON metadata and the
[command reference](bcl-reference.md) / [machine schema](bcl-commands.json).
MCP's four generic schemas stay small instead of generating one permanent tool
per opcode. Capability discovery is **not** Minecraft knowledge; recipes/tool
mechanics stay in existing separate catalogues.

## M0 defaults, modes and heights

Signature: `M0 X Y Z F`.

- Absolute mode: omitted X/Z use fresh current coordinates.
- Relative mode: supplied coordinates are offsets from the fresh player position
  **at dispatch of this operation, after all previous queued operations finish**.
  Omitted X/Z mean zero displacement. Explicit relative Y=0 keeps current feet Y.
- Omitted Y always invokes runtime height resolution at the resolved world X/Z.
  Only currently observed, hazard-free cells connected to the current source by
  native stepped navigation edges qualify. Prefer smallest current-height change,
  then shortest native graph path, then Y as deterministic tie-breaker. Never the
  highest surface blindly. Unknown, disconnected or hazardous destination fails
  `UNREACHABLE_TARGET` before driving. Automatic Y is intentionally **local**;
  distant unknown destinations require observation/navigation first or explicit Y.
- Omitted F uses the enqueued S2 snapshot. Explicit normal/fast/sneak applies only
  to this operation. It never changes S2. Maps to the existing shared motor's
  walk/run/sneak; `WalkTo.movement` is additive and defaults to legacy walk.
- Native `terrain=True` full-block one-step geometry, 64-block per-goal bound,
  hazard/damage checks and actor-fenced short leases remain mandatory. No slabs,
  fluid routes, custom jumps, teleportation or safety guarantee.

## Modal settings

All settings are declarative `Setting` definitions in the same registry.

| Opcode | State | Ordered values/default |
|---|---|---|
| S0 | execution_mode | sync → async; default sync |
| S1 | coordinate_mode | absolute → relative; default absolute |
| S2 | movement_mode | normal → fast → sneak; default normal |
| S3 | error_mode | stop → continue; default stop |
| S4 | timeout_seconds | numeric 0.1..120; default 30 |

For every cyclic enum, no argument advances exactly once with modulo wrap,
a value sets idempotently, and `?`/`status` reads identically without mutation.
The generic interpreter handles arbitrary finite enum lengths, not just binary
booleans. S4 requires a numeric value or `?`/`status`; it cannot cycle.
The former **unpublished draft** S0 placeholder for arbitrary settings was never
available; the addendum supersedes it. There are no released BCL clients to migrate.
S6 gamemode is **not registered**: no authorized privilege-preserving BCL skill
adapter exists. It cannot grant creative mode/OP or bypass normal Survival.

Settings/subscriptions are processed in frame ingress order on a staged copy.
Only after **the whole frame compiles** does one SQLite commit publish its state
and request identity. Validation/commit failure leaves modal state unchanged.
A later native action failure does not roll back valid earlier settings/actions.
Each queued action stores an immutable snapshot. Later S commands cannot modify
that action, including its response-wait mode. The last action's captured S0
sets a frame's `execution_mode`; trailing S0 changes affect only future actions.

All Minecraft actions remain **serial FIFO**, even under async. Sync waits for
completion; async returns accepted/task ID and may queue work without waiting.
Control messages/settings/events stay responsive during either. Relative anchors
resolve only when their serial action is actually dispatched, never concurrently.
S3 continue advances past observed nonfatal failures, but never turns them into
success. Final result is failed/`completed_with_errors`. Actor loss, uncertain
transport, unconfirmed cleanup, partial crafting, total deadlines and global
failure/repetition budgets still stop. S4 is per operation, not an override of
the separate bounded total activation deadline (max 1800 seconds).

## Sessions, durability and retries

An explicit session ID binds agent/world namespace, player UUID and current opaque
actor_session. The world label is operator-selected, not a native world fingerprint.
Modal journals use existing private POSIX `SessionStore`/SQLite/file locks.
No modal/subscription state leaks between sessions. A changed actor requires a
new explicit session; there is no implicit rebind, respawn or reconnect.

Request IDs are monotonically increasing positive JSON-safe integers
(1..9007199254740991). Persist the ID/source digest, modal commit and reply summary
atomically. A repeated matching ID returns the cached outcome; a different source
with the same ID fails `REQUEST_CONFLICT`. Keep the newest 128 replies plus a
permanent high-water ID: evicted/older IDs fail `STALE_REQUEST`, **never reexecute**.
This protects non-idempotent cycles as well as physical actions.

Connection loss cancels that connection's owned queued/running tasks. On restart,
accepted/running journal entries become interrupted, not reconstructed/replayed.
Uncertain or cancelled operations require fresh inspection and an explicitly new
request ID. No automatic rollback, resumption or inference of gameplay success.
Subscriptions persist for the bound session; events missed during disconnection
are not replayed. Reset is explicit, idle-only, restores modal defaults and clears
subscriptions, but retains request dedup history. F8 is not a resettable setting.

## Persistent projects above BCL

[ProjectJournal / ProjectAgent](projects.md) retain model-authored typed plans,
requirements, material counts, running intent and reconciled progress across model
calls/activations. They use this compiler, SDK and existing native runtime; BCL does
not acquire a house generator or another control loop. Plans do not grant authority,
change deadlines or bypass actor/session/dedup fences. Explicit-support I3 can
observe an already correct destination and return `desired_block_already_observed`
without using an item. Ordinary full-cube planks share its existing placement path.
This is postcondition idempotence, not permission to replay uncertain requests.
Append-only `I4 B P C` selects a support/face mechanically for ONE agent-selected
block coordinate and delegates to I3's motor. It never generates a structure or
scaffold sequence and never retries an uncertain use.

## Gateway hardening follow-up

See [gateway/building qualification](gateway-building.md) for the separate current
assessment and [evidence](evidence/gateway-building.json). Historical initial BCL
qualification below remains scoped to its recorded source/artifacts.

A bind may add `"role":"observer"`; omitted role means controller for backwards
compatibility. Only one controlling session per player UUID is admitted, including
its cleanup/quarantine phase. Other controllers receive `ACTOR_BUSY`; pure observers
may inspect/subscribe and change only their own modal state. Observer reads never
claim input control or stop the active controller. Separate native players still
require separate native client endpoints in this alpha.

Session states are connected → cleaning → released. A slow cooperative cleanup
may enter `quarantined_until_cleanup`, but a retained supervised reaper releases it
when the worker actually terminates. A truly stuck trusted Python handler cannot
be killed safely: it stays fenced/quarantined and requires an explicit host restart;
no lock is stolen while a live worker could still perform cleanup. Durable action
IDs/results are not replayed. This fixes the previous permanent binding after a
cleanup that finished later than the disconnect grace period.

Sender/watcher termination (including unexpected cancellation), slow sends and
queue overflow close the socket and cancel owned work rather than leaving a
half-alive connection. Critical lifecycle events bypass optional display filters;
terminal replies/events are never silently dropped. Disconnect/sequence identity
makes lost delivery detectable; persistent request summaries allow inspection,
not replay. Worker `BaseException` is converted to a terminal job result.

Authenticated native `ok=false` replies are `NativeRejected` failures with typed
fault domains, not guessed broken TLS. Missing tools/materials, invalid targets,
full inventory or GUI preconditions remain recoverable. Uncertain transport is
latched closed. Actor loss terminates the affected session without falsely marking
the entire gateway transport broken. Death is an observed lifecycle transition,
not a disconnection; modal queries remain possible while dead.

Optional JSON `{"type":"respawn","request_id":N}` requires controller role and
explicit operator `--allow-respawn`. It uses the existing native respawn operation
with a NEW optional `actor_session` fence, checked atomically before effects.
Rebuild/install the matching mod. Legacy unfenced SDK/raw envelopes remain compatible.
The receipt is submission only. `player.respawned` provides the observed new actor;
the old connection closes normally and the caller must explicitly bind a new
session/token. No pending action, request, material peak or building plan is replayed.

`V2 X Y Z` is a generic bounded camera adapter; `I3 B P F A` adds an optional selected
support face (default up) and opt-in mechanical standing-pose selection (`Atrue`,
default false) from existing safe native cells using the existing walker. They do not choose a structure or build sequence.
Placement still requires current exact native hits, unobstructed reach, actor
fences, player-body exclusion, observed placed block AND one consumed item.
Face failures include actual target/eye/support and geometric face-plane rules.

BCL results now explicitly distinguish `program_verified` from external goal
verification. `objective_verified` is false for a BCL program: executing its commands
cannot attest that a free-text house/Survival goal is complete. This corrects an
unreleased development result-label ambiguity discovered by a real LLM build trial.

## Event family and observations

- `E0 event.name`: subscribe (idempotent); `E1 event.name`: unsubscribe.
- `E2`: own subscriptions; `E3`: clear own subscriptions.
- E100 `player.position`, E101 `player.health` (health/hunger), E102
  `inventory.changed` (observed counts), E103 `command.completed` (operation status).

Server event definitions are in the same registry but are direction-restricted:
client `E100...` fails `DIRECTION_DENIED`. Client JSON `type:event` is also rejected.
Events use the existing controller `Event(name,data)` data contract, not a second
controller. Read-only sampling is bounded to at most 2 Hz (shared cache), reflects
client-known data only, and never scans hidden blocks or predicts damage. Do not
invent a max-health value when it is absent from native observations.
E104 `player.dead`, E105 `player.respawned`, E106 `player.not_in_world` and E107
`transport.disconnected` are append-only server lifecycle events. Respawn is
recognized only for the same player UUID following death; a foreign UUID is never
silently rebound. Lifecycle transitions do not invent empty inventory observations.
Task completions use actual runner results. Registered trusted host providers may
publish mod events with `await gateway.publish(Event("create:machine.stopped", data))`;
register the namespace/event first. Clients can subscribe but cannot publish.

## Persistent WebSocket framing

The optional explicitly started **Python TLS gateway**, loopback only in this
version, sits before the unchanged native TLS bridge. It is not a replacement
for Java's authentication/transport and adds no Java parser. Use a dedicated
operator-provisioned gateway certificate/private PEM key; **never export/copy the
Minecraft PKCS12 key**. Clients pin exactly the selected gateway public certificate
and verify the existing logical TLS service name `block-bridge.invalid` using the
existing Bridge TLS-context helper. No system trust, plaintext, redirect, Origin
or verification bypass. API key is independently checked after TLS, using a
separately selected private gateway token. Native connection/config remains separate.

One JSON text WebSocket frame carries one source string (single or multiline):

```json
{"type":"bind","language":"BCL/1","session_id":"agent-a-session-1","agent_id":"agent-a","world_id":"owned-world","player_uuid":"UUID","actor_session":"TOKEN"}
{"type":"bcl","request_id":1,"source":"S0 async\nS1 relative\nE0 player.position\nM0 1 0 0"}
{"type":"cancel","request_id":2,"task_id":"bcl:..."}
{"type":"reset","request_id":3}
```

Bind requires a fresh native UUID/session match. Replies have `type:response`,
request/session/connection IDs, status and monotonic **connection-local** sequence.
Task replies additionally have task ID. `accepted` does not mean gameplay success;
terminal `completed` means verified execution. Failures/cancel/interruption carry
structured diagnoses. Async completion arrives on the same socket. `type:progress`
is correlated running progress; `type:event` is a spontaneous subscribed observation,
with event_type/opcode/direction/data, never confused with a request reply.

Bounds: 8 connections, 32 active sessions, 16 queued tasks plus one active actor,
32 subscriptions/session, 64 pending outgoing messages/connection, 32768-byte
frames. Outgoing large task details may be omitted explicitly while preserving
operation statuses. Overflow closes/cancels rather than silently losing terminal
results. Native bridge frames/queue/lease limits are unchanged. A latched uncertain
native transport failure stops all later RPCs; restart the authorized host to
reconnect, never automatically retry.

The gateway owns the sole native connection. Run **either** the normal standalone
MCP host **or** the gateway against that client, not competing separate native
connections. Python in-process integration may use the same coordinator/player.
No externally reachable HTTP listener or settings that weaken TLS are added.

## Python / MCP usage

Human-operated [terminal REPL and file CLI](bcl-terminal.md):
`python -m blockwire.bcl.cli` or `blockwire-bcl` connects to this gateway with
explicit certificate/token and actor binding. `--file program.bcl` sends a whole
frame and waits for terminal completion. The offline compiler below is unchanged.

Offline:

```sh
python -m blockwire.bcl --compile 'M0 X120 Z30 Ffast'
python -m blockwire.bcl --discover navigation
python -m blockwire.bcl --describe S2
python tools/generate_bcl_reference.py
```

Start only with explicitly provisioned private gateway materials:

```sh
BLOCKWIRE_CONFIG=/trusted/native/settings.json python -m blockwire.bcl.gateway \
  --certificate /trusted/bcl/certificate.pem --private-key /trusted/bcl/key.pem \
  --token-file /trusted/bcl/token --state-directory /private/bcl-sessions
```

Reference SDK (other languages need only this framing/TLS protocol, not controllers):

```python
from blockwire.bcl.client import BCLClient
async with BCLClient("wss://127.0.0.1:8880/v1", gateway_token, gateway_certificate,
                     session_id="session-1", agent_id="a", world_id="owned-world",
                     player_uuid=uuid, actor_session=actor, timeout=120.) as client:
    await client.send("S0 async\nS1 relative\nS2 sneak\nE0 player.position")
    accepted = await client.send("M0 1 0 0")
    terminal = await client.wait(accepted["task_id"])
    event = await client.events.get()
```

SDK never automatically reconnects/replays. It also exposes cancel/reset and a
bounded/coalesced display-progress queue. Timeout means uncertain outcome, not
permission to retry with a new ID. Inspect/cancel first.

MCP adds only `compile_bcl`, `execute_bcl`, `discover_bcl_commands`,
`describe_bcl_command`; existing tools remain compatible. Execute uses explicit
session_id, monotonic request_id, agent/world/player/actor identities. Settings-only
requests complete immediately; action requests return an ID. Existing
`skill_status` / `cancel_skill` cover BCL jobs; raw mutations are excluded while
BCL work owns/queues the actor. No API accepts arbitrary state-file paths.

## Extensions and compatibility policy

Trusted Python registers `registry.namespace("create", "1")`, then `Command`
Aliases to existing registered skill contracts. Use `skill_parameter(...)` to derive
field adapters/constraints. `register_setting(Setting(...))` generates generic
cycle/set/get metadata, including four-or-more-value enums.
`register_event(name, opcode, namespace="create")` generates server-only event
metadata. Core namespace cannot be overwritten or extended through public extension
registration. Conflicting semantic IDs/opcodes fail. No namespace causes imports.
Supply the explicitly constructed registry to `BCLGateway(...,registry=r)` or
`create_server(bcl_registry=r)`. Installing/enabling host providers is operator work.

BCL/1 opcode meanings and enum order are append-only compatibility contracts;
incompatible changes require a new namespace/version, not silent reassignment.
Unknown extension, version or persisted modal layout fails closed. Existing raw
WebSocket/MCP clients and TLS identity/keybinding constants are unchanged. New
Python-only features need matching development SDK, not a Java transport rewrite.

## Qualification and limits

Current verification: **312 Python tests PASS**, including 41 BCL-specific tests;
**218 isolated mutations killed** (24 BCL, 128 skill/runtime, 32 native, 20
controller, 14 campaign); Gradle check PASS; native TLS interop **10 PASS**.
Nine BCL authenticated-TLS/WebSocket tests use simulated native backends, separately
from the real-client evidence. Native M0 auto-height/explicit fast passed; two real
TLS gateway runs each completed relative sneak travel and async fast return,
delivered ten events and retained health 20/20. The first fixture's unusable
same-height candidate preflight is retained, not counted as a successful run.

Measured warm compiler median: 8.22 ms (100 samples); representative source
17 UTF-8 bytes, framed source 58, equivalent JSON decision 107, internal IR 407.
Four MCP tool schemas: 2187 bytes; full 26-definition registry: 32865 bytes at
measurement. These are **bytes, not exact model tokens/billing**; full metadata
is loaded progressively. See the raw performance record linked in the manifest.

See [scoped evidence](evidence/bcl-live.json). Parser/semantic tests, isolated
mutations, TLS/WebSocket tests with a simulated native backend and actual graphical
Minecraft tests are reported separately. Only movement/auto-height/relative modes,
modal snapshots and event delivery have new BCL-native qualification; registering
crafting/combat adapters does **not** qualify their gameplay through BCL.

Spontaneous subscribed events are delivered by the WebSocket gateway; the MCP
facade offers the same control/discovery/status, not a new MCP push-event transport.
Future chat providers may use the local `ChatFilter` policy (all, explicit agent
mentions, sender UUID allowlist, bounded distance). `player.chat` is NOT registered
without a native provider. Filtering never grants command authority; messages remain
untrusted data, and critical lifecycle events cannot be suppressed by chat filters.
No complete Minecraft wiki, general terrain solver, gamemode mutation, public
multi-tenant server, non-loopback gateway, non-POSIX journal qualification or
exact LLM token billing measurement. Cancellation is cooperative; trusted provider
code that blocks indefinitely can delay cleanup. If disconnect cleanup exceeds
the grace period, it remains quarantined until the late cleanup reaper can safely
release it (or an operator restarts a genuinely stuck host).
Server/world text is untrusted data. Input release and observed outcomes are not
server-authoritative survival guarantees. No publish/tag/upload was performed.
