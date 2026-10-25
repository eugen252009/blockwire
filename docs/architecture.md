# Architecture

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

## Enforcement boundaries

- **Transport:** Minecraft's existing Netty libraries, no shaded WebSocket server
  dependency. A required JDK TLS handler precedes all HTTP processing. A persistent
  self-signed leaf is generated with bundled Bouncy Castle certificate tooling.
  Configured IP bind (loopback default), authenticated upgrade, origin
  rejection, bounded peers, one channel lease, frame/request bounds, queue limit and expiry.
- **Thread boundary:** Network callbacks enqueue on Minecraft's client executor.
  They never read/write a player or menu directly. Closed/obsolete channels are
  rechecked at execution. Ownership is not released until input cleanup runs.
- **Native actions:** key mappings and view orientation; native attack/use
  invokers, native container input handling, native respawn. No custom server
  packets, damage logic, stack mutation, physics or per-entity scanning tick.
- **Two narrow client mixins:** an accessor interface for the native attack/use
  methods; an input mixin for the global, remappable kill switch and allowing
  bridge-held native mining without a grabbed desktop mouse. Ordinary input
  behavior is unchanged when no bridge attack is held.
- **Lifecycle:** local config auto-start at CLIENT_STARTED (works before a world)
  or explicit F8 enable; tick + monotonic input lease; player/level
  identity check; generation-gated endpoint cleanup; release on screen, pause,
  death, disconnect, stop or unexpected dispatcher exception.
- **Menus:** bounded widget traversal and one-use screen snapshots. Events route
  through native screen mouse/key/character/scroll handlers with SDL input conversion.
  No direct `onPress` callback or text-value mutation.
- **Observation:** bounded client data, item components summarized, human text plus
  machine-readable fields. Snapshots are not authoritative server outcomes.

## Goal/skill boundary

`SkillRegistry` describes strict schemas; trusted, explicitly enabled provider
entry points register additional goals. `SkillManager` runs one cooperative worker
per actor, with bounded history/progress, status and cancellation. MCP exposes
that same registry and rejects competing raw control while a job runs. See
[extensions](extensions.md) and [skills](skills.md).

The first walker consumes an explicit on-demand `navigation` mesh (radius 4,
81 loaded flat full-block cells), uses native collision edges and short guarded
look/drive operations. It never loads chunks, changes physics or guarantees safety.
Player/world session tokens fence old observations from replacement actors.

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
cloud service or general portal to commands. Bounded planning belongs in the
external Python skills layer, not a replacement native movement/combat engine.
The actor API is intentionally small so future providers can implement it without
forcing a transport into their game code.
