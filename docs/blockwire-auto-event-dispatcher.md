# Subscription-driven automatic event reporting

## Status and qualification

Implemented as an **opt-in native observation source feeding the existing BCL
Event stream**, not an agent broker, new socket, chat relay or shared model memory.

**Current multiplayer follow-up: MP04 passed 18/18 cases in one fresh cohort.**
Two genuine localhost/offline clients independently verified chat both ways,
player proximity, chat/proximity during active BCL movement, actor/task isolation,
subscriptions/filters, rejoin and real LLM communication. Three recordings finalized;
normal cleanup passed. Native-report reserve pressure counted one dropped chat
report while retaining 52 control replies. See the separate
[scoped multiplayer gates](blockwire-multiplayer-qualification.md) and
[MP04 evidence](evidence/multiplayer-event-qualification.json). Hard native/socket
overflow, two online-authenticated accounts and long-term Survival are not claimed.

The table below preserves the **original candidate-004** qualification, not MP04.
Earlier MP01–MP03 failed windows and their unverified exit-143 shutdown also remain
historical evidence; they are not pooled into MP04 or silently rewritten.

| Feature | Implemented | Deterministic / real TLS tests | Real Minecraft |
| --- | --- | --- | --- |
| Normal chat send via vanilla signed client path | Yes | Yes | **PASS: signed self-echo on authenticated client/integrated server** |
| Incoming `player.chat` | Yes | Yes | **PASS**, actual sender and delivered text observed |
| Observable player enter/leave | Yes | Yes, simulated player observations | **Two-player NOT RUN** |
| Observable Monster enter/leave | Yes | Yes | **PASS: Normal-difficulty controlled zombie fixture** |
| Per-session subscriptions / radius | Yes | Yes | **PASS: same-actor observer with smaller radius excluded the zombie** |
| No repeat spam / visibility leave / reentry | Yes | Yes | **PASS: quiet interval, opaque wall, wall removal** |
| Incoming chat during BCL execution | Yes | Yes | **PASS while M0 remained active; walk postcondition verified** |
| Agent observation context | Yes | Yes; no automatic inference | **PASS: actual received event present in bounded context** |
| Burst/backpressure and disconnect behavior | Yes | Real TLS with simulated source | Native overload/disconnect injection NOT RUN |
| Genuine two-client multiplayer chat, both directions | Implemented paths | Not replaced by mocks | **NOT RUN / BLOCKED: only one available authenticated player profile** |

**Original candidate-004 was not full multiplayer qualification.** One installed/
usable profile was available then; no second authenticated identity was supplied. No fake player,
account/credential copy, offline-auth workaround or cross-world relay was used.
Two observer/controller sessions bound to the same native player are explicitly
**not** counted as two Minecraft clients or two player identities.

[Evidence](evidence/auto-event-dispatcher.json) and
[point-in-time hashes](evidence/auto-event-dispatcher-hashes.json) separate actual
native acceptance from simulations and unrun multiplayer cases. Earlier four-agent
campaign worlds, code snapshots, journals, recordings and manifests remain intact.

## Architecture

```text
Fabric incoming-player-chat callback ─┐
                                    ├─ native bounded source
Loaded/visible entity sample (5 ticks)┘          │
                                  existing authenticated native TLS lease
                                               │
                                  optional Bridge receive demultiplexer
                                               │
                                  AutoReporter observation adapters
                                               │
                         existing BCLGateway.publish(Event(...))
                                               │
                             existing session subscriptions / filters
                                               │
                                existing BCLClient.events queue
                                               │
                         bounded EventContext → next normal model decision
```

There is **no LLM polling for messages**. Chat is captured on the actual Fabric
`ClientReceiveMessageEvents.CHAT` callback and wakes the gateway collector on
arrival, not on a reporting timer or after a BCL job finishes. Entity observation
is internal and bounded; only enter/leave transitions reach subscribed clients.
Existing health, position, inventory, task and lifecycle reporting remains on the
existing gateway watcher. No movement, physics, crafting or damage implementation
was replaced. All experimental stateful reuse remains default OFF.

The native transport extension is **additive, opt-in unsolicited observation
frames on the same existing TLS WebSocket lease**. It is not a second connection
or peer protocol. Native events remain disabled for legacy clients. TLS identity,
certificate/hostname checks, API keys, Origin rejection, one native controller,
queue expiry, ownership cleanup and F8 are preserved. Push publication additionally
requires a successfully completed authenticated WebSocket upgrade, not merely a
pending owner slot.

## Enable and subscribe

The standalone gateway requires explicit opt-in:

```text
blockwire-bcl-gateway --auto-events ...existing TLS/token/state arguments...
```

Or trusted Python host code constructs:

```python
gateway = BCLGateway(player, token, state_directory,
                     native_events=native_bridge,
                     reporting_policy=lambda identity: ReportingPolicy(radius=16))
```

The matching mod must advertise `observe.auto_events_supported=true` and have a
live actor. Unavailable/older providers fail closed rather than advertising fake
chat. `default_commands()` alone still does **not** advertise `player.chat`.
The configured gateway registers these additional server-only events:

| Event | Descriptor | Meaning |
| --- | --- | --- |
| `player.chat` | E108 | Actual incoming player-chat callback |
| `player.nearby.enter` | E109 | Player newly observable within session policy |
| `player.nearby.leave` | E110 | Player no longer in the observed set |
| `entity.hostile.enter` | E111 | Newly observable native `Monster` |
| `entity.hostile.leave` | E112 | Monster no longer in the observed set |
| `reporting.metrics` | E113 | Source/transport/bridge/gateway loss and coalescing counters |

Use the **unchanged** subscription commands:

```bcl
E0 player.chat
E0 player.nearby.enter
E0 player.nearby.leave
E0 entity.hostile.enter
E0 entity.hostile.leave
E0 reporting.metrics
```

`E1 name` removes one subscription, `E2` reports own subscriptions, `E3` clears
them. Names are exact registered events, not wildcard subscriptions. E108–E113
are server event descriptors, **not executable commands**; client attempts to
emit them fail direction checks. There is no new M155-style subscription opcode,
no client `publish` request and no changed BCL action semantics.

## Chat send/receive contract

Outgoing normal chat is exposed through:

- `Player.chat(message, actor_session=...)`;
- `blockwire chat 'Hello' --actor-session ACTOR [--json]`;
- MCP `send_chat(message, actor_session)`.

This invokes native `connection.sendChat`, retaining vanilla signing and server
restrictions. It does not release movement controls or take a second skill lease.
An explicit actor fence, live unpaused non-spectator gameplay and closed GUI are
required. Native sending is limited to one request per second. Maximum 256 UTF-16
units; empty/control/formatting/malformed text and slash-prefixed commands are
rejected. `/command` authority remains separate. A submission receipt is **not**
delivery, server acknowledgement or gameplay success; uncertain sends are never
blindly replayed. The BCL-only historical campaign host was not retrofitted with a
chat opcode or an alternative outbox: use the explicit Python/MCP chat API.

Incoming payloads contain:

```json
{
  "message": "<local-player> Hello from native auto-event fixture",
  "channel": "player_chat",
  "sender_uuid": "<redacted>",
  "sender_name": "<redacted>",
  "received_at_ms": 1234567890,
  "signed": true,
  "actor_session": "<bound native actor>",
  "untrusted_observation": true
}
```

This example is redacted; full native payloads are private evidence. `message` is
the actual delivered Component's plain text, including decoration when supplied,
**not hidden/unfiltered signed content**. Formatting styles are not interpreted as
instructions. Sender fields are included only when Minecraft supplies a profile.
`channel` distinguishes this source from system messages; it does not invent a
public/private channel classification. Distance is optional and only available
for an already observable sender entity. Fully filtered messages are not exposed.
System/game/disguised-message callbacks and historical chat scraping are **not
implemented** and are never mislabeled as player chat.

Duplicate signed callback signatures are suppressed with a 64-entry bounded set.
Identical text with distinct signatures, and distinct unsigned arrivals, are not
incorrectly collapsed. Native sequence numbers deduplicate repeated stream frames.
Order is preserved within the source/connection where the callback/network order
exists; no global cross-player/server ordering is invented.

Messages remain **untrusted observations**. Neither the dispatcher nor the context
adapter parses received BCL as an action or grants command authority. A trust flag
alone is not a guarantee against all model prompt injection; the independent
capability, actor, permission and postcondition checks remain necessary.

## Entity scope and filtering

The native source samples every **five client ticks**, inspecting at most **256
client-rendering entities**, returning at most **16** relevant players/Monsters.
Only alive, non-invisible entities within **24 blocks**, the existing approximate
120-degree view cone and native line of sight qualify. No server entity scan,
unloaded chunk access, hidden player position or threat prediction is added.
`Monster` classification is not a promise that every dangerous/neutral modded
entity is covered or currently attacking.

Trusted host `ReportingPolicy` validates:

- per-session radius **greater than 0 and at most 24 blocks**;
- snapshot minimum interval **0.25–5 seconds**;
- optional immutable player-UUID allowlist (maximum 32);
- existing `ChatFilter` for chat policy.

The default opt-in chat policy is `all`; sender-UUID allowlists or bounded nearby
filters are available. Native chat does **not** invent an agent-ID mention list;
`mentions` filtering cannot match absent mention metadata. Filter configuration
currently belongs to the trusted host, not new BCL subscription arguments.

Payloads include native entity ID/UUID, type, distance and observed position;
player names are present only for players. A leave event means
`reason: no_longer_observed`, with a separately labeled last observation. It can
mean range exit, occlusion, turning away, unloading or despawn; it does not claim
to distinguish those causes. An omitted entity in a **truncated** snapshot is
unknown and does not generate a fabricated leave. Stable entities generate no
repeated reports. No automatic combat or movement is started.

Adapters reuse registered `Event(name,data)`, trusted publication and per-session
policy. Future reliable native categories can add source adapters and registry
entries without changing the BCL parser. Passive/neutral/world/targeting/attack
providers are not speculatively advertised.

## Backpressure, privacy and lifecycle

Bounds remain explicit:

- native chat capture: 2,048 UTF-16 units, at most 10 callbacks/second; oversized
  messages are dropped, never silently truncated into different text;
- native push: 16 KiB frames, at most 32 outstanding writes, writable upgraded
  owner required; Minecraft never waits for network delivery;
- Python native observation queue: 64, with counted low-priority drops; control
  replies are separately demultiplexed and never mistaken for events;
- reporter: at most 20 observation events/second/session and at most 32 tracked
  entities/session, including unknown entries retained after truncated samples;
- existing gateway: 64 outgoing items, with automatic reports refused at 48 to
  reserve 16 slots for lifecycle, responses and task completion;
- existing BCL subscription and client queue bounds remain in force.

`reporting.metrics`, when subscribed, reports cumulative source, native transport,
bridge and gateway drops, rate limiting, snapshot coalescing and bounded tracking
evictions (`tracking_evicted`). Evicting an unknown entry is not reported as a
physical leave. Host code can
also inspect `gateway.auto_events.metrics`. Stage counters can overlap and must
not be summed into a unique packet-loss count. Native transport drops discovered
after scheduling appear in a subsequent frame's counter. If a connection is lost
before that report, counters do not prove complete historical delivery.

Events are **not durable across disconnects**. Subscriptions persist according to
existing session rules; missed observations are not replayed. Actor/world change,
death, F8 and connection termination invalidate the source. Event identity/schema
failure closes the native stream and causes gateway job cleanup, not reconnect or
rebind. A new native actor requires explicit new activation/binding. No stream
history or model context is shared across worlds. Only explicitly selected live
chat may be forwarded into an LLM context; operators must consider its privacy.

## Agent decision-loop integration

Use the existing queue, not a new inference trigger:

```python
context = EventContext()
collector = asyncio.create_task(context.collect(bcl_client))
decider = EventAwareDecider(existing_decider, context)
# The existing host calls decider only at its normal bounded decision point.
```

`EventContext` keeps at most 16 observations, exposes at most eight / 16 KiB and
counts old-context coalescing. It is a presentation helper, not durable delivery
or a replacement for authoritative lifecycle/task responses. Cancel/join its
collector during normal shutdown. Runtime safety events retain existing handling;
ordinary chat/proximity messages do not interrupt a task or launch inference.

## Actual evidence and retained failures

The final source/JAR candidate has a prospective runtime map under private
`build/auto-event-dispatcher/attempt-004/`. The real tests used a new authenticated
hidden client, a new command-authorized superflat fixture, Normal difficulty and
controlled NoAI zombie/opaque-wall setup. Administrative setup occurred before
movement measurement; there was no auto-combat, rescue or gameplay planner.

- Signed normal chat self-echo reached the actual BCL subscription with real sender
  identity. Native capture and gateway receipt timestamps were recorded;
  individual local samples are **not a latency SLA or multiplayer benchmark**.
- A zombie produced enter, no repeated enter in the quiet interval, leave after
  an opaque wall and reentry after wall removal. A smaller-radius observer did
  not receive it. This observer is the same native actor, not another player.
- In a separate threat-free case, chat arrived while an actual **M0** task remained
  active. The walk then completed with `program_verified=true`; chat unsubscribe
  excluded a later actual message. The received event was present in the agent
  context. No new model inference was triggered by collection.

An initial fixture setup encountered the native empty-world-list shortcut and
created a separate default world before configuration. That world and the failed
UI assertion were preserved; a distinct configured fixture was subsequently
created. An initial concurrency test correctly returned **known_danger_nearby**
because the controlled zombie was still nearby. This guard rejection remains;
the later case removed the fixture threat **before measurement**, without changing
movement safety or replaying an uncertain action. Intermediate candidate results
are not pooled into final multiplayer acceptance.

The prior Flatpak GL launch issue was avoided with **process-local**
`FLATPAK_GL_DRIVERS=default` for these new owned hidden test launchers. No driver,
account store, global service or user display was repaired/reconfigured.

Regression: **633 Python tests**, Gradle contracts (including new native chat
boundaries and authenticated native push), **TLS 10/10**, **209 skill**, **50 BCL**,
**14 gateway**, **47 Play2Code**, **54 native** and **12 new auto-event isolated
mutations** PASS. Initial mutation runs exposed duplicate anchors: an existing
placement guard occurred twice, and new chat validation duplicated command-check
snippets. Anchors were narrowed to the intended guard; original invalid runs were
retained. No safety assertion was removed or weakened. A cleanup script also
retained an initial permission-denied process-inspection failure before correcting
its handling of inaccessible unrelated processes.

Two-player multiplayer chat/reverse direction and real nearby-player entry/exit
remain **NOT RUN**, blocked by the single available authenticated profile. No
second identity was fabricated or server authentication bypassed. A new full
211-case native movement cohort, physical F8 injection, native event-flood test,
new replay viewer playback and multi-hour autonomy were **NOT RUN**.

A final bounded-memory review added a stress test for arbitrarily long runs of
truncated/crowded snapshots: retained unknown observations are capped at 32,
counted evictions do not fabricate leave events, and the final source was tested
again in a fresh native fixture. That test and two matching mutations pass.

All four new fixture clients saved/quit normally. Five new world saves and their
recordings, including failed setup/pilot evidence, were archived. Own gateways,
ports, inputs, launcher/display workers are closed; controls disabled. Previous
campaign evidence is unchanged. No commit, push, upload, release or deployment;
existing distribution ZIPs were not rebuilt.
