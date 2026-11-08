# Autonomous Survival soak / LLM fuzzing — prerequisite qualification

## Verdict: BLOCKED BEFORE THE EIGHT-HOUR CAMPAIGN

The eight-hour experiment is authorized, but **has not started**. Zero autonomous
soak sessions, model calls, generated tokens or gameplay operations are claimed.
This report is a partial execution of the request, not completion of all fourteen
phases or a long-term-autonomy GO. See [machine evidence](evidence/autonomous-survival-soak.json).

The prerequisite fixes/tests below were executed. Further scheduling/global-budget,
inference-accounting, failure-shutdown and capacity work is still required before
extended play. No uncontrolled daemon, automatic restart or eight-hour extension
was installed. Historical evidence and source freezes remain unchanged.

## 1. Empty BCL: exact failure and fix

The old path was:

```
PI text response → strict JSON → private Decision model → compile_bcl(source)
  → EMPTY_PROGRAM exception → exit before feedback/finish processing
```

In feedback R01, agent 2's decision 26 explicitly contained `source:""`,
`finish:true`, and a final failure-report proposal. The private host compiled the
optional empty field unconditionally. **No BCL frame reached the TLS gateway**;
Minecraft never received an unintended action. The final proposal was preserved
in raw model output but was not submitted. It is not retroactively replayed.

`python/src/blockwire/soak.py` introduces a reusable strict host boundary:

- Full decision/schema/memory/chat/command validation precedes effects.
- Only the compiler's exact `EMPTY_PROGRAM` diagnostic maps to no commands.
  Empty, whitespace, valid-header-only and comment-only output are deterministic.
- Malformed JSON, prose in the command field, invalid headers/opcodes/arguments
  still fail explicitly; invalid multi-command frames do not partly apply settings.
- Feedback-only/observation-only/finish proposals are distinct. Feedback is retained
  even without commands; no empty batch/job/input lease is created.
- No-command decisions never certify gameplay. `NoCommandBudget` bounds repeated
  idle/feedback turns; feedback is not a way to reset that counter.
- Valid multi-command source goes unchanged through the existing compiler/SDK.
- Lost/interrupted receipts are `UNKNOWN_NO_RETRY`; no reconnect/resubmission.
  Known-task cancellation uses only that task on the same lease.

**BCL/1 syntax/compiler/gateway semantics are unchanged**: sending a raw empty BCL
frame directly still returns explicit `EMPTY_PROGRAM`. The fix is in the host,
not an invented no-op opcode, planner or native movement engine.

## 2. Shutdown / recording investigation

The completed feedback R01 server recorded exit 0 and both clients were absent,
but neither recording was finalized. Both active `.mcpr.tmp` directories survived.
Native logs show ReplayMod reporting the **current** recording as partially saved
at startup, then metadata/CRC/final-save writes failing at its original
`replay_recordings/recording/...` staging path. The data had moved to the parent.
ReplayMod's restore GUI bytecode contains that staging move; diagnostics are kept.

The direct `--server` launch overlapped recording startup with recovery handling.
The corrected lifecycle first establishes a stable native TitleScreen with no
active recording, then joins through the normal multiplayer UI. New qualification
instances have independent native credentials/certificates; no account/token store
or old TLS identity was copied. These are two real clients using the previously
authorized supported Prism offline test profiles on a loopback-only vanilla server,
not online-authenticated-account qualification or fabricated network players.

All old incomplete recordings/logs/closed world were archived **without repair or
rewriting**. The original failed verdicts remain failed. A separate old cleanup
bug called nonexistent `hidden.stop()`; new cleanup uses the supported owned-display
stop CLI only after owned games are verified gone.

## 3. Native prerequisite cohorts

These are deterministic regression fixtures, **not LLM gameplay or a soak run**.
Both use Survival/Peaceful flat fixtures without commands or granted inventory.
They do not replace the required natural-world autonomous campaign.

### Q01 — fresh isolated fixture

Two owned hidden graphical JVMs with live Custom / 8 / 5 / 30-FPS settings:

- empty/whitespace/comment/header-only decisions submit no BCL jobs;
- an empty-source finish proposal retains its feedback ticket;
- malformed source rejects; native `V0` + `I0` completes and verifies the program;
- early cancellation and normal finalization pass;
- two finalized `.mcpr` files pass ZIP CRC and complete monotonic packet framing;
- atomically persisted memory is readable; closed player NBT positions match the
  native final observations; vanilla server stop exits 0; clients/ports close.

Inspection correctly found that Q01 cancellation happened **before actor binding**
(`cleanup=not_needed_before_actor_binding`). It is not promoted to held-input
cancellation evidence. Q01 remains immutable.

### Q02 — separate corrected cancellation / closed-world-clone continuation

Q02 uses a closed Q01 world clone, not a fresh-start or source-pooled repetition.
Before each cancel it waits for **native `remote_owned_inputs`** to be nonempty.
Both clients observed `forward`/`left` ownership, then terminal `cancelled`,
`cleanup=released` and subsequent native ticks with no owned or pressed inputs.
Repeated cancellation creates no additional drive/look/action/inventory mutation.
Two further recordings finalize and pass CRC/full packet framing. Memory and closed
player positions match; the server stops normally; both JVMs/endpoints terminate.

### V01 — representative actual viewer playback

Q02 A's recording was loaded and played in the actual native Replay Viewer, then
exited via its native `Exit Replay` menu. Screenshots/scene/menu/PID proofs are
private. This is a short beginning sample (camera initially inside a player),
not a visual audit of every movement or every replay. An initial known menu-overlay
rejection was handled by waiting for the ready title, not gameplay replay.
Viewer JVM/control/display were then closed normally.

Native sources, decisions, input telemetry, memory, closed worlds, four finalized
recordings, logs and checksums are under
`build/autonomous-survival/soak-001/prerequisite-archive/`. Old R01 partials remain
under `phase1/previous-R01-closed/`. Nothing from those worlds is fed to a model.

## 4. What remains blocked

| Gate | Result |
|---|---|
| Empty/whitespace/malformed/valid boundary | PASS: contracts + two native cohorts |
| Normal shutdown, world/memory persistence | PASS in the stated normal/known-cancel scope |
| Actual held-input cancellation / repeat cleanup | PASS Q02 |
| TLS / gateway / qualified BCL regression | PASS |
| Replay finalization | 4/4 prerequisite recordings integrity PASS |
| Actual viewer playback | One representative Q02 A sample PASS; others NOT RUN |
| Full native disconnect/process-failure/failure-budget shutdown matrix | **Incomplete**; contracts are not native crash qualification |
| Fresh negative actor-isolation / UNKNOWN fault injection for soak | **Not fully qualified**; historical/contract evidence not pooled |
| Current maximal-capacity resource ramp | **NOT RUN** |
| Global model token/cost reservation and metering | **BLOCKED / not implemented in current text adapter** |
| Eight-hour autonomous gameplay / recovery / stability | **NOT RUN** |

The selected existing backend remains openai-codex / gpt-6.1-sol. Its local model
catalog advertises a 128K max output. `CommandJSONDecider` bounds captured JSON bytes
**after the process returns**; that is not a generated/thinking-token or cost cap.
The existing text interface does not retain provider token usage. A durable global
ledger, pre-request reservations, bounded inference queue and verified worker
failure cleanup are needed before the extended campaign. No new paid provider was
introduced and no inference was needed for these prerequisite fixtures.

CPU topology was freshly inspected: Ryzen 5800X SMT pairs (0,8)..(7,15), Minecraft
pool 1–6/9–14, orchestration 7/15, OS spare 0/8. These are owned-task affinities,
not reservations. No kernel thread/service was pinned. Historical five-client
headroom, six-client functional evidence and four-agent campaigns remain separate.
Two short fixture clients with verified settings are **not** a fresh maximal-safe
concurrency qualification. Recording overhead, queue wait, token rate and long-run
resource maxima are unmeasured here, never fabricated as zeros.

`campaign_blockers` / `require_campaign_ready` fail closed on missing, partial or
non-PASS gates. `SessionLifecycle` persists explicit states and refuses COMPLETED
without all finalization proofs or after an unknown outcome. Existing files require
explicit reconciliation; there is no implicit resume/replay. These are building
blocks, not a fully wired eight-hour supervisor/CLI. Remaining phases were not
silently declared implemented.

## 5. Failure corpus and engineering priorities

`failure-corpus-private.jsonl` preserves context/artifact-specific forensic incidents:
optional empty source, replay staging/recovery, missing display-cleanup helper and
Q01's insufficient cancellation fixture. Missing observation fields are null,
not invented. Incidents reference immutable artifacts/source snapshots and hashes;
they are not merged solely by error text and not counted as new soak failures.
No confirmed new Blockwire movement/physics defect is claimed from these incidents.
Retained R01 mining/navigation failures still need independent technical diagnosis.

Priorities:

1. Implement and qualify selected-model token/cost accounting and hard global
   reservations; bound worker trees and inference queue. Unknown usage stops work.
2. Complete the native fault-shutdown matrix, including disconnected/failed
   processes and quarantine; never force-kill an unverified save or resume unknown work.
3. Requalify current effective-8/5 resource capacity, RPC/tick tails and recording
   overhead before choosing parallelism; do not infer eight/sixteen capacity.
4. Wire bounded 30-decision / 300-operation / 30-minute sessions with verified
   persistence/replay continuation into the approved **eight-hour maximum**.
5. Diagnose `mining_not_observed` and terrain-reachability incidents from native
   preconditions/side effects, rather than implementing every LLM proposal blindly.

Checks: **683 Python tests**, Gradle check, **10 TLS interop checks** and **78
applicable isolated mutations** (50 BCL + 14 gateway + 14 soak), all PASS/KILLED.
Regression tests: `python/tests/test_soak.py`; isolated guards:
`tests/run_soak_mutations.py`. The initial uncertain-cancel mutation was equivalent
because a second safety guard reclassified it; the final mutation genuinely bypasses
that guard and is killed. Original diagnostics remain preserved.

No commit, push, upload, release, deployment or distribution rebuild was performed.
Stateful Input optimizations, native TLS/identity, actor fences, ownership, native
leases, collision/damage/crafting, F8 and historical evidence remain unchanged.
