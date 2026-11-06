# Native two-client multiplayer follow-up

This follows the original single-client auto-event dispatcher qualification.
Two genuine Minecraft 26.3 JVMs used separate owned Prism instances, bridge
credentials/ports, actor sessions and BCL state on one isolated **loopback-only**
vanilla server. Prism 11.1.1's supported `--offline NAME` launched the two local
test players; no account/token editing, copied accounts, packet-spoofed player or
external-server authentication bypass was used. This is **not** qualification of
two online-authenticated Microsoft identities. Native chat was correctly unsigned.
Native bridge TLS/hostname/API-key checks remained mandatory and unchanged.

## MP04 — fresh scoped native qualification

**18/18 cases GO in one new frozen runtime/configuration cohort.** This does not
replace the failed historical windows below. [Evidence](evidence/multiplayer-event-qualification.json)
and [source/evidence hashes](evidence/multiplayer-event-qualification-hashes.json)
keep the gates separate:

| Gate | MP04 result |
|---|---|
| Two real clients in one actual server world | GO; distinct native UUIDs/JVMs/game directories/credentials/actors, independent inventory change |
| Ordinary chat A → B | GO; exact delivered text/sender, native callback → BCL, no duplicate |
| Ordinary chat B → A | GO; same checks, actual unsigned offline metadata |
| Player proximity from both perspectives | GO; real BCL walk enter/leave, quiet interval, self-exclusion and geometric distance |
| Exact radius threshold | GO; actual native player at 8.0 enters, at 8.01 leaves; no invented hysteresis |
| Chat while A/B moves | GO both directions; delivery before terminal M0, walk postconditions verified |
| Proximity while A/B moves | GO both directions; each mover receives the peer enter event while its task is active |
| Actor/session/private-task isolation | GO; foreign actor binds and foreign-task cancel/results denied |
| Different subscriptions, unsubscribe/repeated subscribe | GO; chat-only recipient receives chat but no proximity events |
| BCL disconnect/rebind | GO; missed chat is not replayed; new chat is delivered |
| Validated radius/player/sender filters | GO; actual native observations/messages excluded and restored |
| Ordered native bursts | GO; three messages each way, ordered without duplicates |
| Native disconnect/rejoin | GO; same pinned JVM, same player UUID, new actor token and explicit new session |
| Automatic-report backpressure | GO scoped; one real native chat report dropped/counted under reserve pressure; all 52 read-only BCL responses preserved |
| Independent LLM communication | GO; A → B → A through native chat, three real model requests with separate contexts |
| Recording integrity / normal cleanup | GO; three finalized recordings, full framing/CRC, server exit 0, clients/ports/display gone |

The observed listener was `[::ffff:127.0.0.1]:50982`, checked against its owned
server PID/UID/start-time/cwd before client joins. Whitelist/max-players=2,
RCON/query disabled, no public bind/tunnel/forwarding/firewall change. Standard
Prism `--offline NAME` was used; no Microsoft token/profile fabrication or account
copy/editing. Native bridge and BCL TLS/hostname/API-key checks stayed mandatory.
This is **localhost offline-mode qualification**, not two online-authenticated
Microsoft accounts or public-server qualification.

The disposable Survival/Peaceful superflat fixture uses disclosed operator console
teleports for repeatable positions/exact boundary and give/clear of one dirt for
inventory isolation. Those are TEST preparation, not autonomous Survival progress.
Startup reaches a stable title/recovery barrier before native UI server join,
preventing the earlier ReplayMod direct-join/recovery race. Effective Custom/8/5,
30 FPS and Minimized-only throttling were read from both native option screens.

The independent model sample uses the existing selected openai-codex /
gpt-6.1-sol, medium, isolated tool-free contexts. A independently reported its own
pose and asked B what it could observe; B independently described its own pose and
nearby A. A's next normal decision included the native B reply and chose to wait.
No expected answer, broker, shared strategy memory, executable chat or
message-triggered inference was supplied. It is communication, not a Survival GO.

### Bounds and limitations

The 108.96-second case window sampled 108 resource records with no violations or
affinity escape. Mean Minecraft-pool CPU was 25.72%, one-second peak 72.76%; owned
Minecraft/server peak RSS 7.20 GiB, minimum host MemAvailable 47.09 GiB. Observe RPC
p50/p95/p99: 33.37 / 60.03 / 66.74 ms. Affinity remains owned-task placement, not
exclusive reservation. No eight/sixteen-client or long-term capacity claim follows.

The pressure test holds only the existing outgoing WebSocket consumer for 1.92 s,
without changing its five-second send deadline, queue64/reserve16 or native limits.
It fills the queue with actual read-only `S2 ?` replies, then sends real ordinary
Minecraft chat from B. Automatic reports drop/count at the reserve while all 52
control responses arrive. **Hard native/socket queue overflow was not forced.**
Far-player observation exclusion passes; exact chunk-unload internals are not
separately instrumented. F8 remains unchanged but was not physically pressed.

All three original MP04 recordings pass ZIP CRC and complete monotonic framing.
A's recording additionally passed a short actual native viewer sample, exited via
`Exit Replay`, then normal Quit. The camera initially lies inside a player; this
is not a complete visual chat/movement audit, and B's two recordings were not
played back. Original bytes/hashes remain unchanged after viewing.

Checks: **684 Python tests**, Gradle check, ten TLS interop checks, **76 isolated
mutations KILLED** (50 BCL, 14 gateway, 12 automatic-event). One targeted real-TLS
simulated-source regression was added. Its first parallel full-suite execution
exposed a test rendezvous race: filling the queue with synchronous SQLite commits
could delay the sender's first tick. The test now establishes the stalled consumer
before filling the queue; assertions and its original 1 s / 2 s limits are unchanged.
The final serial full suite passes; original diagnostics are retained.

No production Java/Python dispatcher, BCL grammar, transport, planner, peer protocol
or movement implementation was changed. Raw data/source/world/recording archives
are private under `build/auto-event-multiplayer/MP04/`; only redacted summaries and
hashes are public. All owned clients, gateways, server and hidden display closed;
control configs disabled. No commit/push/upload/deployment/distribution rebuild.

## Historical MP01–MP03: observed gates without pooling a clean verdict

Private windows are retained under `build/auto-event-multiplayer/MP01..MP03`.
Those historical windows had **no single all-green final cohort** and no long-term
Survival verdict; MP04 above is a separate source/configuration cohort.

- MP01: 11 GO / 3 NO_GO. Both chat directions, both proximity directions,
  chat during verified movement and actor/task isolation were observed. An
  exclusive event-log filename collision broke collection after rebind, and a
  restarted JVM's transient broad affinity correctly triggered the watchdog.
- MP02: 13 GO / 2 NO_GO. Rebind/no-replay, subscription controls, bounded ordered
  bursts, radius/filter and far-scope checks passed along with the earlier gates.
  The harness expected TitleScreen after Disconnect, while native Minecraft
  returned JoinMultiplayerScreen. The subsequent model-chat case consequently
  had a disconnected recipient and failed; it is not counted as model success.
- MP03: 13 GO / 2 NO_GO. Same-JVM native disconnect/rejoin, new actor binding,
  both chat directions, chat during movement, isolation and actual independent
  model communication passed. A failed preflight handshake prevented the intended
  position reset; the two proximity transition cases failed from invalid initial
  fixture positions. These failures remain NO_GO, not retroactively corrected.

The successful MP03 model exchange used three real, separate external-model
requests: A independently described its actual pose/state and asked B what it
observed; B independently reported its own pose/state; A's next normal decision
included the received native reply and chose to wait. No canned response, peer
mailbox, shared model memory or event-triggered extra inference was supplied.
This is a communication sample, not useful Survival progression or autonomy.

## Historical MP01–MP03 closure and recording limitations

The owned server's final recorded exit was **143 / normal_stop=false**. Its cause
was not established; no verified normal shutdown or crash-recovery claim is made.
Both dedicated clients were subsequently absent; their control configs were
explicitly disabled, and native/gateway/server ports were closed when archived.
The actual server level (not a guessed `world/` directory) and available client
recording/log directories were preserved in `closed-archive/`.

One finalized B recording passed ZIP CRC and complete monotonic packet framing.
No finalized A recording was found by that archive pass; retained partial files
are not promoted to complete capture. Playback and two-client recording-completeness
qualification remain separate. All failed windows and initial archive diagnostics
are retained. No movement, dispatcher or secure-transport redesign was made for
these tests. Later host-side feedback work belongs to a separate source cohort.
