# Gateway hardening and autonomous BCL building

**Historical qualification record.** Its original outcomes below are retained.
The later [persistent-project follow-up](projects.md) / [evidence](evidence/persistent-projects.json)
adds an uninterrupted Stage-A success and a real empty-inventory Peaceful-Survival
structure independently verified afterward, with original failed terminal/QA
results kept separately. It does not rewrite the trials described here.

Development follow-up to [BCL/1](bcl.md). Gateway safety, supplied-material building
(Stage A), and empty-inventory Survival building (Stage B) are separate gates.
Historical initial BCL evidence remains unchanged; current facts/hashes are in
[evidence/gateway-building.json](evidence/gateway-building.json).

## Current gate assessment

- **Gateway: GO for the bounded trusted-local, single-native-client profile.**
  No public/multi-tenant, Windows persistent-play or multiple-native-player claim.
- **Building Stage A: CONDITIONAL GO.** Native LLM-generated construction works
  and a recovered shelter has independent acceptance, but uninterrupted fresh-run
  goal completion/reliability is NOT established.
- **Building Stage B: NO-GO.** Regular dirt acquisition and roof repair occurred,
  but no complete accessible shelter was independently established.

Final automated checks: **333 Python tests PASS**, **233 isolated mutations
KILLED** (24 BCL, 14 gateway/building, 128 skills/runtime, 33 native, 20 controller,
14 campaign), Gradle check PASS and native TLS interop **10 PASS**. These are not
substitutes for the separately described graphical-client tests. Initial mutation
harness anchor/test-name failures were retained, corrected and fully rerun; no
product guard was weakened to obtain those results.

## Review and fixes

The earlier concerns were reproducible in the reviewed code:

- A job finishing after disconnect's ten-second wait left its session in `bound`
  with no later release. A retained cleanup reaper now releases late cooperative
  completions automatically. States are connected, cleaning, quarantined-until-
  cleanup, released. A genuinely stuck trusted Python worker cannot be killed or
  safely unlocked in-process; explicit host restart remains the recovery boundary.
- Different controlling WebSocket sessions could serialize work on the same player
  but still interfere across programs. The gateway now reserves one controller per
  player UUID through cleanup. Additional controllers get `ACTOR_BUSY`. Explicit
  observers can inspect/subscribe without claiming/stopping controls. They cannot
  dispatch movement, placement, combat or cancel another connection's tasks.
- Sender/watcher tasks were unsupervised. Failure, unexpected cancellation, send
  deadline or bounded-queue overflow now closes the connection and cancels owned
  work. A stopped consumer cannot leave an apparently usable silent socket.
- Native rejections were classified using a whitelist of strings. Authenticated
  native `ok=false` now raises `NativeRejected` with a typed failure domain.
  Preconditions remain recoverable, actor loss ends its session, actual uncertain
  transport/invariants latch closed. Unknown explicit native operation rejections
  do not masquerade as TLS failure. Legacy `BridgeError` remains compatible.
- A worker `SystemExit` could strand the queue; worker BaseException now becomes a
  terminal result. No physical/native controls are reused until old cleanup ends.
- Death no longer means transport failure. E104 dead, E105 respawned, E106 not in
  world and E107 disconnected are distinct, server-only lifecycle events. Dead
  controllers can still query modal state. Native execution reports PLAYER_DEAD or
  PLAYER_NOT_IN_WORLD rather than a combined ambiguous condition.
- Optional, explicit `--allow-respawn` permits an ordinary native respawn request.
  A new optional native actor_session guard is checked atomically before respawn.
  Old raw/SDK envelopes remain accepted; existing commands/cert identity/F8 are
  unchanged. Submission is NOT proof of recovery. An observed same-UUID respawn
  emits the new actor token, closes the old session normally and requires an
  explicit new binding. Pending work is never replayed.

The live lifecycle fixture deliberately injected `/kill @s` in the owned Stage A
world AFTER a qualified closed-world snapshot was saved. This is **not** a mob,
combat, avoidance or autonomous Survival test. It verified live death detection,
continued dead-player queries, obsolete-token respawn rejection without effects,
authorized fenced respawn, new actor observation and execution in a new explicit
session. Credentials/TLS identity hashes were unchanged on mod installation.

## Event boundaries

Position/health/inventory are bounded sampled client observations. Terminal replies
and lifecycle events are never silently coalesced: overflow disconnects with a
visible reason. Sequence numbers and connection identities distinguish stream loss;
persistent request summaries support inspection/dedup, not event replay. Display
progress may coalesce in the SDK. Critical lifecycle events bypass display filters.

A local typed `ChatFilter` prepares all/mentions/sender-UUID/nearby routing for a
future trusted native chat source. No chat source is invented or registered here;
`player.chat` remains unavailable. Chat text is data, never control authorization.
TLS, API key checks, loopback defaults, native leases/queue bounds and F8 remain.
This is a trusted-local-controller gateway, not a public multi-tenant service.

## Generic building mechanics (not a build-house command)

`V2 X Y Z` wraps one bounded, actor-fenced native elapsed-time camera turn and
verifies the observed final orientation; BCL syntax is unchanged.
`V0` exposes the already bounded real scene/surface/navigation data to the planner.
`I3 B P F A` extends the existing placement adapter with an optional exact cube face
and optional mechanical positioning (`Atrue`, default false). It uses existing
native reachable cells and the existing walker to face an already observed support;
it does not select what to build. Exact native target/face, short reach, no player
body intersection, held material, observed resulting block AND consumption are
still required. Wrong-face failures include actual target/eye/support geometry.

An important real-planner failure exposed ambiguous success labels. BCL's old
`objective_verified=true` referred only to its supplied subprogram, but the LLM
mistook it for shelter completion. BCL now reports `program_verified` and explicit
`verification_scope`; external `objective_verified` stays false. Only a separate
trusted goal predicate may attest the shelter. Opcodes remain BCL/1 compatible.

## Stage A: supplied-material mechanics

Fixture: real Minecraft 26.3, owned Prism `Blockwire-alpha3-test`, authenticated
nested Xephyr display, superflat seed 1409, Survival / Peaceful, commands ON for
operator fixture provisioning only. Initial spawn `[10.5,-60,-5.5]`; initial
inventory observed empty, then **64 cobblestone explicitly supplied with native
`/give`**. No geometry or BCL house sequence was provided. A closed-world baseline
snapshot and a separately closed qualified snapshot are retained privately.
This is NOT empty-inventory or resource-acquisition Survival qualification.

Planner: actual `openai-codex / gpt-6.1-sol`, medium thinking, installed CLI with
all tools/extensions/MCP/context files disabled. Strict JSON carries model-generated
BCL and its own expected-block manifest. Source compiles before execution and runs
through the real TLS gateway, SessionStore/AgentRuntime and native Minecraft.
There is no `build_house` skill, prepared action list or host-generated house plan.

The model independently chose footprint x9..11/z-5..-3, two-block-high walls at
Y=-60/-59, a full roof at Y=-58 and north-center entrance x10/z-5. The native trail
records 26 actual placements: 23 shell blocks plus three external access blocks;
64→38 cobblestone inventory consumption is consistent with those placements.

Observed failures were retained:

1. A01 placed 20 blocks but stopped with an incomplete roof after misreading batch
   success as full goal success. Independent acceptance rejected it.
2. A02 resumed the same world with that failure feedback, **not an independent
   fresh-world attempt**. The LLM replanned from unreachable/wrong-side supports,
   completed the missing roof, produced its own 23-position manifest and declared
   completion. An independent replay of 43 recorded real `V0` observations verified
   all 14 wall blocks, all nine roof blocks, two-block entrance and native floor/
   headroom/doorway collision edge. No hidden block queries or save/NBT block reads.
3. The private test harness initially discarded intermediate V0 outputs in a batch,
   causing false-negative completion feedback. The collector is fixed to ingest
   every returned observation, not just the final camera pose. The original failed
   records remain intact; independent acceptance uses the complete native record.

`verify_shelter` is a pure optional qualification predicate over the model's
manifest, observed surfaces and native navigation. It generates NO actions/plans.
Unknown blocks, incomplete roof, absent doorway/floor proof and wrong material fail.
It validates the rectangular design actually chosen by this model, not every
possible free-text building. Client observations are not server-atomic truth.

4. A03 repeated from the CLOSED clean baseline with a fresh real model history.
   Forty decisions produced 25 verified placements (23 shell positions and two
   access blocks), including the last missing roof cell on decision 40. All 23
   positions match this model's independently declared footprint/doorway notes.
   It exhausted its budget BEFORE providing a full manifest/accepted finish.
   Physical construction is not an accepted autonomous terminal result.

A01 used 19 model replies, recovered A02 40; fresh A03 40. Thus the two fresh
activations have **0/2 accepted uninterrupted terminal successes**; do not report
recovered native acceptance as a fresh-run success rate. One recovered Stage A
world has the complete independent native shell/doorway certificate. A03's full
placement ledger is additional mechanics evidence, not a second acceptance.

A separate live cancellation probe deliberately replayed one A03-generated BCL
program **only as a fault test**. It waited for actual `acting`, cancelled, observed
`cancelled` with cleanup released and unchanged inventory after settling. This is
not a new autonomous construction run. The saved A03 structure was retained.

Optional mechanical positioning (`I3 Atrue`) has isolated regression/mutation
coverage but was NOT additionally qualified in this graphical building sequence;
actual LLM placements used the ordinary exact-face placement path.

## Stage B: regular resources

Separate new natural Survival world, empty inventory, commands/bonus chest OFF.
No materials, tools or workbench may be supplied. The goal remains the same; the
LLM receives existing resource/crafting/mining contracts and chooses prerequisites.
Only explicit observed completion can pass this independent gate. Stage A's
materials, operator death fixture and copied snapshots cannot qualify Stage B.

Actual fixture: **Blockwire BCL Building B01**, natural Default seed 2, Survival /
Normal, respawn radius 0 set in the creation rules, commands OFF, bonus chest OFF,
empty inventory verified before action; CLOSED empty-world baseline retained.
No `/give`, creative inventory, teleportation or hidden world reads were used.

The model chose soil acquisition and an earth-integrated dugout rather than a
freestanding supplied-cobblestone house. B01 used 17 model replies, mined ordinary
dirt and placed a roof block. A test-harness whitelist incorrectly rejected its
naturally observed stone/grass floor/wall manifest; the rectangular-only criterion
also did not fit its actual chosen earth design. Both limitations were corrected
WITHOUT weakening the required walls/roof/native standing and entrance proof.
The separate pure `verify_usable_shelter` predicate permits natural full-cube walls,
a model-declared observed roof, three closed sides and an actual reachable native
entrance edge; a real construction receipt is independently required. Unknown
surfaces never become proof. Clear accumulated observations after mining: removed
blocks must not survive as stale goal evidence.

B02 explicitly resumed the SAME natural world (not a new fresh attempt), with
30 further real model replies. It repaired the previously removed roof: two total
verified placement events, **one unique roof position** `[-35,64,1]`. Final inventory
was 11 naturally obtained dirt, health 20. Repeated observation, excavation and
entry tests did not establish the complete walls/roof/reachable-entrance predicate.
Result: `incomplete / decision_budget`; independent acceptance remains false.
No success was inferred from batch receipts or the model's partial manifest.

Creation/menu and one startup TLS timing failure were retained separately; neither
provided gameplay materials or counted as a successful model attempt. This is one
fresh regular-resource world with a software-fix resume, not two independent trials.
The world was saved/closed afterward; the client was left at TitleScreen.
Tools, scalable resource planning and recovery-efficient autonomous construction
remain unqualified. Hand-dug dirt is a genuine native resource, not proof of
stone/tool progression, food safety or general unattended Survival.

## Reproduction / limits

- Review the exact generated BCL/model requests/replies and native outputs under
  the private evidence directory named in the manifest. Those are audit artifacts,
  not a house template to replay as a fake planner.
- Restore only the explicitly selected CLOSED test-world snapshot. Never copy a
  running world or inspect hidden blocks to manufacture verification.
- Use current SDK/mod together for fenced respawn. Gateway starts explicitly with
  private TLS key/cert/token, optional `--allow-respawn`, loopback listener and a
  private state directory. Keep all saves, credentials and raw journals out of a
  distributable; use the allowlisted bundle builder.
- Reconnect with the same session/request identity for dedup; use a NEW session ID
  and observed token after actual player replacement. Do not steal quarantined locks.
- Trusted noncooperative Python still requires host restart. Modded geometry,
  multi-native-player gameplay, public deployment and general autonomous Survival
  are not established by a supplied-material shelter or simulated TLS tests.
- No push, tag, upload, release or production deployment is authorized/performed.
