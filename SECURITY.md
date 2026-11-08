# Security model

Blockwire gives an authorized program control of a Minecraft player and access
to client-known inventory/world information. Protect the API key and TLS identity.

## Lean machine profile

The opt-in [machine-v1 profile](docs/bcl-machine.md) offers small native inputs,
not the legacy route/search/crafting planners. **Raw pulses are not safe routes or
exact-distance moves**; collision and damage remain native. Health/actor/cancel
checks and at most six-tick input leases bound execution, but do not prevent every
fall, attack or placement mistake. Existing walking/placement safety code is not
relaxed or relabelled as qualification of these primitives.

Reporting is independent, partial and sampled; missing events are not proof that
nothing happened. Wire gaps/overflow and uncertain cleanup fail closed. Interrupt
cancels only owned active/queued work, bypassing audit failure and the action FIFO;
a fresh same-actor native release proof and explicit resume are required before
new actions. Legacy cancel/reset/respawn cannot bypass this barrier. Disconnection
never replays actions or launches replacement model calls.

Combined attack/use primitives conservatively require inventory, mining AND combat
permissions; raw slot clicks require inventory AND crafting permission, since a
native result-slot click can craft. Typed aliases/compositions pass the same whole-
program compiler and persistent input admission as text programs. No alias grants
extra permissions. No remote code loading or executable game text. The separate
[search observation](docs/search.md) adds bounded, actor-fenced native rays outside
the action FIFO, never a movement/harvesting planner or hidden-coordinate query.
A negative result is not proof of absence; geometric rays are not renderer pixels.

Explicit input phases may retain common keys and aim while crouched, but never
extend an individual native lease beyond six ticks. They require movement,
inventory, mining and combat permissions. Asserted slot programs require inventory
and crafting; unconfirmed post-click effects quarantine queued execution. Stack
assertions cover item IDs/counts, not full item components or server transactions.
Recipe reports and model-authored blueprint notes are data, never planners,
executable scripts, permission grants or proof that a structure exists.

## Transport and identity

- Disabled by default. Explicit local config `enabled: true` authorizes startup
  from the main menu; F8 remains the local runtime kill switch.
- Explicit literal IPv4/IPv6 bind; loopback default. Non-loopback binding still
  requires trusted clients and a firewall.
- **Mandatory TLS 1.2/1.3 before HTTP/WebSocket processing. No plaintext listener,
  protocol sniffing/downgrade, or insecure-client option.**
- Each instance generates an independent P-256 EC private key and self-signed
  SHA-256/ECDSA server certificate at first startup, even while control is disabled.
  It persists, expires after ten years and never silently renews/replaces a damaged
  or incomplete existing identity.
- Certificate generation uses bundled Bouncy Castle tooling; TLS uses the JDK's
  provider through Netty. No shell/keytool invocation or JDK-internal API.
- Python uses a dedicated trust store containing only the explicitly selected
  instance certificate. Certificate and hostname verification stay enabled.
  The logical TLS name is `block-bridge.invalid`, independent of the connection IP.
  It is intentionally retained across the Blockwire rename to preserve existing trust.
  Initial remote certificate distribution must use an already trusted channel.
- TLS authenticates the server, not the controller. WebSocket upgrade separately
  requires `Authorization: Bearer <key>`; URL credentials and Origin headers are
  rejected. The API key is sent only after the verified TLS handshake.
- Generated directory permissions: 0700; config, compatibility token, TLS
  identity and certificate files: 0600 on POSIX. On non-POSIX systems protect
  the game directory with user-only ACLs.
- The private PKCS12 identity has an empty store password: filesystem access is
  the security boundary, not a password stored beside the key. Its exported
  certificate contains no private key and may be copied to trusted clients.
- Atomic identity persistence, serialized generation, missing-export recovery
  from the same identity; malformed/mismatched/expired identities fail closed.

## Authority and lifecycle

- One controller, at most eight peers, 8 KiB request/frame limit, 32 queued game
  tasks, two-second queued-request expiry, five-second TLS handshake timeout and
  30-second network read timeout.
- All game access runs on the client thread. Disconnected controllers cannot run
  queued actions. Ownership cleanup precedes reuse; generation checks prevent
  an old endpoint releasing a new endpoint's held input.
- Holds expire by ticks and monotonic deadline. Cleanup requires the game thread
  to advance; no real-time release guarantee during a JVM/OS stall.
- Inputs release on unexpected dispatch errors. An explicit, bounded Minecraft
  slash-command RPC uses native client submission and server permission checks.
  It does not grant OP/cheats. No host code/shell execution, file API, direct NBT
  evaluation, remote container opening or creative cloning primitive is exposed.
  Permitted Minecraft commands may nevertheless change NBT, spawn items/entities,
  teleport, destroy terrain, affect players or invoke server/plugin functionality.
  Enabling the endpoint authorizes this expanded player-command authority: only
  grant it to trusted controllers, and approve commands independently of game text.
- Native menu control can create/delete worlds, join servers, change options and
  open native external links. Do not authorize destructive actions casually.
  Chat screens are not controllable. Text values are redacted, but other menu
  labels can contain personal world/server names.
- World/server/item labels are untrusted data, never authorization/instructions.
  No telemetry or implicit model connection is added; Minecraft's usual services remain.
  An optional explicitly configured external LLM client is described below.

The optional Mod Menu screen uses the existing local F8 lifecycle and can save
only the startup `enabled` flag. Opening it never enables control; saving a draft
does not change the running endpoint or start Python/autopilot. It never displays
or rotates credentials. Private config validation and atomic replacement preserve
keys, token and TLS files; stale/missing/symlink settings are rejected. Authorized
native menu automation can operate the same widgets, just like other native menus.
No arbitrary settings/file RPC or new remote authority is added.

## Descriptive skills and trusted extensions

High-level planning runs in the Python host, not as remote code in Minecraft.
Only explicitly selected installed `blockwire.skills` entry points load;
there is no RPC to install/import arbitrary modules. Providers execute ordinary
trusted Python and are **not sandboxed**. Review LLM-generated extensions before
installing/enabling them.

One background job owns the actor. Raw mutating MCP tools reject concurrent
control; observations, status and cancel remain available. Deadlines/cancellation
are cooperative, with native short holds and F8 as separate safeguards. Walking
uses an actor-session fence on every look/drive and always attempts final release.

The [approach](docs/approach.md) skill selects only initially visible interactables;
an optional exact position filters that bounded list, never queries arbitrary
coordinates. It moves/aims with actor-session guards and requires an observed
exact native target before success. It never automatically uses/opens a block or
moves inventory, and does not treat game labels as instructions.

The optional [autopilot](docs/autopilot.md) is an explicitly activated, bounded
Python skill, never a startup/reconnect behavior. Creeper evasion and proximity
defense are independently opt-in. Native attacks fence the actor and expected
crosshair entity before submission; autonomous defense does not establish who
attacked first. Its threat observations remain bounded, incomplete client data.
No safety or explosion-avoidance guarantee is provided.

Extended [visibility](docs/visibility.md) is a fixed-budget, read-only on-demand
observation: 64-block player-eye rays, at most 16 reported interactables, and
compact sampled first-hit surfaces. Native shape queries use a loaded-only getter;
unknown chunks are opaque. Bounded block-entity **position keys**, never values,
custom names, NBT or inventory contents, seed sight tests. No arbitrary coordinate
queries, chunk generation, background world map or increased native reach is added.
Potential visibility is partial, not a renderer or safety guarantee.

The navigation observation exposes at most 81 loaded same-level collision cells,
not arbitrary world/block/NBT queries or new chunk generation. Known hazard/mob
checks are incomplete. `avoid_damage` is never a no-damage/no-death guarantee.

## Standalone controllers

The optional [Python controller](docs/controller.md) is explicitly activated and
bounded, not started from game text or client startup. Only the selected installed
controller entry point loads; directly run scripts are ordinary trusted host
Python, not a remote file/code RPC or sandbox. Callbacks run in the host, never
on the game thread. Queue/subscription bounds, deadlines and cancellation are
cooperative; CPU-blocking/cancellation-ignoring trusted code cannot be killed safely.

One controller owns the actor against local skills/MCP and the native connection
lease. Inside it, compatible walking/eating tasks use one serialized input mixer;
hand/hotbar/control conflicts fail before effects. Child cleanup removes only its
own contribution. Per-key native leases never extend a retained walking deadline
when another task renews use. Actor-session fences include hotbar changes; no
replacement actor is silently rebound. Final cleanup waits for workers/in-flight
RPCs; uncertain disconnection is not automatically retried or reconnected.
No movement/damage/consumption engine, automatic respawn, startup Python loading,
TLS exception or F8 bypass is introduced. Released input is not player safety.

## Optional strategic LLM runtime

The [agent runtime](docs/autonomous-survival.md) is explicitly started in the Python
host. It never obtains a model endpoint/key from ambient agent settings. Its HTTP
adapter uses a selected endpoint, separate model credential, no ambient proxies,
redirects or automatic retries. Remote game-context disclosure requires explicit
opt-in and HTTPS with ordinary certificate verification. Native Minecraft TLS,
per-instance trust, hostname checks and API-key handling are unchanged.

The model receives bounded identity/goal/game observations/history, not Minecraft
credentials, NBT or host files. Native freeform display labels are omitted; all
world data, notes and model output remain untrusted data. Only strict JSON decisions
for explicitly allowed existing skills can execute. Raw commands, menu events,
respawn, module imports and host code are not exposed to that decision interface.
This does not sandbox malicious trusted host Python/providers or reduce the broader
authority of separately authorized raw native clients.

One activation owns its actor. UUID/session fences, short native leases, bounded
failure/model/action budgets, fresh checks and input cleanup remain mandatory.
An uncertain connection is not reconnected/retried; interrupted pending actions
are never auto-replayed. Partial crafting/cursor state requires explicit recovery.
A planner finish is unverified unless a trusted host checker observes its goal.
Private state/mailbox files contain player identity, locations and goal/history;
protect and exclude them from bundles. The current file-lock runner is POSIX-only.
No autonomous survival, response-time, damage-avoidance or 24/7 guarantee is made.

## Opt-in feedback and input admission

[Feature feedback](docs/feedback.md) stays in the trusted Python host, not the
Minecraft tick or a new transport. Proposals are bounded untrusted data for human
review; there is no model-accessible code/install/permission/budget-reset mechanism.
Fresh native identity checks and existing TLS bindings scope requests. Agent/world
labels remain operator/client labels, not independently authenticated identities.

Private SQLite storage records bounded inputs/admission/outcomes, never auth
headers. Raw MCP menu/command/chat strings are digest-only. BCL source and feature
descriptions may contain sensitive data: do not submit secrets; keep stores out
of Git/bundles. No complete native keyboard/server-outcome audit is claimed.
With opt-in enabled, the default MCP profile denies raw commands/menu/control
conveniences and retains BCL/observation/feedback/cancel/status tools. Durable BCL
reservations and a store-wide aggregate cap survive reconnect and label changes.
Audit/storage exhaustion denies new work but not cleanup/status; F8 is unchanged.
This cannot sandbox separately authorized trusted host Python/raw native clients.
No unattended two-hour/overnight reliability follows from feedback or admission tests.

## Opt-in two-hour subscription profile

[Two-hour scheduling](docs/blockwire-two-hour-sessions.md) is an explicitly selected
trusted-host policy, not an extension of native key leases or a safety waiver.
It has separate immutable gameplay/outer deadlines, shared and per-agent quotas,
and an8192-row bounded model audit; legacy policies retain their2000-row audit
and cannot be upgraded by lowering the new profile to identical numeric quotas.
The persisted two-hour profile discriminator prevents that implicit conversion.
Known terminal goal blocks can lead to cooldown and a fresh model decision, never
an automatic action retry. Repeated unchanged failed frames are rejected before
BCL admission. Unknown receipts, actor replacement, F8 and resource failure still
terminate; no reconnect, rebind, respawn or provider fallback is added. Defaults,
TLS/hostname/key checks, ownership, short input leases and native physics remain.
A prepared host is not authorized automatically; native two-hour reliability is
NOT RUN, and existing eight-hour soak gates are unchanged.

## Passive Play2Code recordings

[Play2Code](docs/play2code.md) is local-only and adds no recorder RPC, MCP authority,
startup controller or input owner. Recording start fails while the native endpoint
is enabled. Enabling it during capture invalidates/stops the capture before the
endpoint starts; remote-owned input, actor/world replacement, death and write
bounds also fail closed. F8 retains its existing endpoint/input-release behavior.
The interaction hooks only correlate native human use/mining with bounded watched
positions and stable client-observed changes; they do not scan the world or claim
server-authoritative confirmation.

Raw captures contain player UUIDs, precise coordinates, inventory item IDs and an
input/action timeline. They are private evidence: POSIX directories/files use
0700/0600, runtime `recordings/` is ignored by Git, and the bundle builder never
copies game directories. Review/redact before sharing. The exporter rejects
symlinks, malformed/duplicate/nonfinite JSON, incomplete/unsafe captures, sequence
changes and bounds; it writes hashed artifacts without overwriting an earlier
export. Generated BCL is compiled but never executed automatically. Replay requires
a fresh authorized actor/fixture and inherits all ordinary TLS, actor, lease,
cancellation and postcondition constraints. Compile success is not gameplay or
objective success.

## BCL/1 modal protocol

[BCL](docs/bcl.md) is data, never generated/evaluated Python or slash commands.
Full-frame static validation and operator permissions precede every modal/native
effect. Existing UUID/session fences, ownership, bounded leases, cancellation and
postconditions remain in AgentRuntime. Continue-on-error cannot bypass fatal
transport/actor/partial-inventory checks or turn failed actions into success.
No S6 gamemode adapter is registered. Extensions remain explicitly trusted host code.

The opt-in loopback WebSocket gateway requires TLS >=1.2, an explicitly provisioned
private gateway key/certificate and a private selected gateway token. The terminal
client rejects symlink/non-regular token files and POSIX permissions broader than
0600. It does not export the Minecraft PKCS12 key. Clients reuse pinned-certificate/
hostname checking; no plaintext/system-trust fallback. The native authenticated
TLS transport remains unchanged. Authoritative events cannot be submitted by
clients. Session-owned subscriptions, queue/frame bounds and persistent monotonic
request dedup isolate agents and prevent accidental replay of non-idempotent cycles,
S1 homing or gameplay actions. A relative home is captured only by the serial
actor-fenced runtime and is bound to the session's world/player/actor identity and
dimension; reconnect does not silently re-home or transfer it. Lost connections
cancel their work; uncertain native transport latches closed until host restart.
Keep private modal/action journals, gateway keys/tokens and raw game evidence out
of bundles. Do not expose this development gateway publicly.

## Persistent project host

`ProjectJournal`/`ProjectAgent` add trusted-host persistence and model context above
BCL, not native authority. The model supplies strict bounded data/source only;
world namespace, state/audit paths, model argv and fixed acceptance policy remain
operator-selected. Journals reuse private POSIX locks/SQLite. Native world/save
identity is NOT inferred: the operator must select the correct owned world before
an explicit resumed actor bind. No hidden save/NBT inspection is added.

Pending intent commits before effects. New activation discards old proof and never
replays uncertain work. Final objective acceptance requires independent fresh world
observations and native floor/headroom/access, not model finish or BCL receipts.
Read-only idempotent placement does not use an item. Existing Native actor fences,
TLS, F8, ownership and queue bounds remain. Persistent operation/model/resource
request caps cannot be reset by model plan revisions. See [projects](docs/projects.md).

## Opt-in closed-save building benchmark

`tests/building/` is privileged TEST infrastructure, not a skill, MCP capability or
agent observation API. It may read the explicitly owned CLOSED benchmark save's
bounded declared voxels to verify blocks AND literal air independently of receipts.
It never edits NBT, supplies hidden save contents to the model, or qualifies this
as unprepared Survival knowledge. Closed snapshot manifests include inventory and
world state; ownership markers, TitleScreen guards and an exclusive fixture lease
protect restoration. Never select a productive world or distribute saves/journals.
Fixture administrative commands are disclosed and separate from both BCL builders.
Unknown cells, uncertain effects or quarantined workers cannot certify completion.
See [benchmark conditions](docs/superflat-building.md).

## Gateway lifecycle hardening follow-up

The gateway reserves one controller per player UUID, including old cleanup; pure
observers do not obtain an input lease. It supervises sender/watcher failures,
bounded send deadlines and queue overflow, and retains a reaper for cleanup that
finishes after disconnect grace. Never force-release a genuinely stuck trusted
Python handler: quarantine plus explicit authorized host restart is the safe boundary.

Authenticated native rejections now carry typed fault domains; recoverable does
NOT mean an action can be blindly retried or rolled back. Death/not-in-world do
not invalidate TLS. Critical actor loss ends its session; uncertain transport or
backend invariants latch closed. Optional explicit gateway respawn requires an
operator permission and a matching new native actor fence; replacement requires
new explicit binding. Critical events cannot be suppressed by a chat/display filter.
No native chat source or game-mode/cheat adapter is invented.

BCL program success is explicitly not the external building/Survival objective.
Supplied-material building evidence and regular-resource building are separate;
see [gateway/building qualification](docs/gateway-building.md).

## Boundaries and rotation

TLS does not sandbox malicious processes running as your OS user, administrators,
modified mods, compromised agent hosts or compromised Minecraft. Those actors may
read keys or act inside the process. TLS is not comprehensive Internet DoS
protection; do not treat this alpha as a hardened public service.

Rotate the API key by stopping Minecraft and replacing `mcp_api_key` in the private
config. Deleting the compatibility token alone does not rotate it.

Certificate rotation is a separate, explicit operation: stop Minecraft, archive
the old identity privately if needed, remove its TLS directory, relaunch, and
re-enroll the new public certificate on every client through a trusted channel.
Never automatically accept a replacement fetched from the endpoint. See
[docs/tls.md](docs/tls.md). Do not include private identities, credentials, game
directories or account data in reports.

A real private vulnerability-reporting contact must be selected before publication;
no hosted project/contact URL has been invented.
