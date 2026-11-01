# Deterministic Superflat building benchmark

This is an **opt-in graphical integration benchmark**, not a new building skill.
The execution path remains BCL/1 → compiler/frozen IR → BCLJobs → existing runtime
and skills → authenticated native Minecraft. Test infrastructure lives under
`tests/building/`; no `build_house()` is registered with skills, MCP or BCL.

## Frozen fixture

- Minecraft **26.3**, DataVersion **5023**, owned isolated alpha.4 client.
- Superflat, seed **31052026**, generated structures and bonus chest OFF.
- Survival / **Peaceful**, commands ON for disclosed fixture preparation ONLY.
- Start feet **(2.5, -60, -3.5)**; supplied **128 cobblestone, 32 dirt, one diamond
  pickaxe and one diamond shovel**. No supplied structure or access ramp.
- Noon (overworld clock 6000), clear weather, time/weather advancement OFF,
  mob/trader spawning OFF, random ticks 0. Baseline configuration is independently
  read from the closed 26.3 save, not inferred from command receipts.
- Administrative preparation clears X/Z −16…16, Y −60…−48 and restores the grass
  surface at Y −61. Native UI/commands, inventory and saved configuration are kept
  privately. Preparation is NOT counted as BCL building or Survival progression.

The baseline is a **closed-world full snapshot**, not a seed-only reset. Its
canonical manifest hashes every save file except the volatile `session.lock`,
including inventory/player data, regions, clocks and game rules. Every fresh run
restores and verifies the exact file tree BEFORE loading, then checks native start
position/inventory and obtains a fresh actor binding. Never copy a running world.
A fixture lease prevents concurrent restores. Only the exact dedicated world
`Blockwire Benchmark Superflat` carrying its ownership marker may be replaced;
previous closed worlds are archived, never silently deleted.

## Independently frozen reference

[`reference.json`](../tests/building/fixtures/reference.json) declares origin
**(0, −60, 0)**, footprint X/Z **0…4**, wall heights **−60, −59, −58**, and roof
height **−57**. Material: `minecraft:cobblestone`.

- Walls: **46** including corners and the north-centre lintel.
- Flat roof: **25**, total **71** required solid positions.
- Entrance: **(2, −60, 0)** and **(2, −59, 0)** must be air.
- Interior: X/Z **1…3**, all three wall levels must be air; the north approach
  also stays clear. Native standing/access proof is additionally required.
- The entire cleared 33×33×13 construction volume must contain ONLY those 71
  required blocks and air. Thus abandoned helpers or hidden interior obstructions
  fail. All 1089 grass-floor positions must remain intact.

Each required voxel is `CORRECT`, `INCORRECT`, `MISSING` or `UNKNOWN`. Missing or
unreadable chunk/section evidence stays UNKNOWN, never assumed air/correct.

### Independent verification sources

1. After the last gateway task, fresh **read-only full native navigation** is
   bracketed by actor observations. Require safe supported grounded player inside,
   matching actor/dimension, no known fire/hostiles/hazards, and all nine interior
   cells, doorway and exterior approach connected in the native graph.
2. Save/quit to TitleScreen, seal the closed result snapshot, then read ONLY the
   declared benchmark volume using the bounded read-only Anvil/NBT test decoder.
   All blocks, air spaces, roof, floor and absence of temporary blocks are checked.

The closed-save audit is **test-only privileged inspection**, not an agent API,
not ordinary visible-world knowledge, and not unprepared Survival qualification.
It is not supplied to the LLM. It generates no actions and never counts placement
receipts as world truth. Native access evidence and immutable closed-save identity
are kept together. Literal air checks also reject plants, fluids and partial blocks.

## Test A: actual deterministic source

[`build.bcl`](../tests/building/fixtures/build.bcl) is the complete versioned source:
**231 operations in 29 explicit bounded frames**. `; @frame` is a harness separator,
NOT a new BCL opcode or parser feature. ALL frames compile before any world effect;
the existing 32-operation frame limit is unchanged. Execution stops on failure;
there is no implicit retry, rollback or interrupted-program replay.

The fixture uses actual I1/I4/V2/M0/C2 signatures. It builds corners first, uses a
one-block interior dirt standing aid, constructs its own ten-block external dirt
stair, builds the roof, re-equips after the first 64-block stack, then dismantles
the stair **top down** using exact exposed `C3 ... P` removal targets and explicit
M0 native-proven one-step descents. C3 delegates the existing guarded mining
motor and requires fresh body/head clearance; unlike resource-gathering C2, it
never claims that a removed block's drop was collected. All eleven helpers must be removed before acceptance.

`tools/generate_building_reference.py` regenerates deterministic TEST data only.
The declarative reference supports other bounded odd widths, rectangular depths,
heights and materials. The shipped itinerary is deliberately specific to this
fixture; new roofs/itineraries require separate fixtures and qualification, not a
productive agent house generator.

## Test B: real external model

The same snapshot, inventory, capabilities and independent structural predicate
are used. The tool-free external model receives the natural-language dimensions,
origin, entrance/air/access requirements, BCL discovery/descriptions, its own
persistent plan and fresh native observations/results. It receives **neither the
Test-A source nor the internal 71-coordinate reference list or save contents**.

The model authors its plan and BCL and handles compiler/action feedback. Compiler
rejections are retained as structured, effect-free diagnostics; subsequent V0
responses do not erase the last failed action. Bounds: **60 model calls, 512
persistent operations, 2700 seconds**, plus existing material/stagnation limits.
A model finish or a successful BCL batch is not acceptance. Test B additionally
requires the agent's observed finish, not merely a later physical-world certificate.
Actual programs, replies, diagnoses and corrections are retained privately and
summarized in the scoped evidence. Simulated decisions never count as real trials.

## Activation

```sh
.venv/bin/python tools/superflat_benchmark.py describe  # offline
# Set BLOCKWIRE_CONFIG to the explicitly selected isolated native instance.
# Select existing private gateway certificate/key with BLOCKWIRE_BENCHMARK_CERT
# and BLOCKWIRE_BENCHMARK_KEY (defaults match the owned development test fixture).
.venv/bin/python tools/superflat_benchmark.py create \
  --authorize-test-client --saves /explicit/owned/instance/minecraft/saves
.venv/bin/python tools/superflat_benchmark.py run-a --run-id A-fresh-01 \
  --authorize-test-client --saves /explicit/owned/instance/minecraft/saves
# B requires explicit PI_BIN and usable credentials for the documented provider.
.venv/bin/python tools/superflat_benchmark.py run-b --run-id B-fresh-01 \
  --authorize-test-client --saves /explicit/owned/instance/minecraft/saves
```

Client must be at TitleScreen; do not provide ordinary gameplay input during a run.
F8 remains available. Failed runs retain their worlds, journals and source. A native
world-load receipt can exceed its five-second wait: only fresh read-only state is
then acquired; the click is NEVER replayed. Actor replacement, uncertain effects,
quarantined cleanup or insufficient storage cannot be bypassed to restore a world.
Transport/API credentials, raw journals, saves and model audits stay under ignored
`build/superflat-benchmark/`, never in a bundle or public evidence.

`--resume-from ... --start-frame ...` is explicit deterministic DEBUG continuation,
not a fresh run or automatic retry. Fault-only runs use `--fault truncate`,
`--fault lost-ack`, `--fault cancel`; `recover-probe --from-run ...` reconciles a
COPY of the interrupted journal and issues a new already-observed target request,
never the old intent. Their acceptance means fault handling, NOT a complete house.

## Regression and retained diagnostics

Fast tests cover geometry, full air volume, missing/wrong/unknown targets, roof
holes, blocked entrances, floor damage, extra scaffolds, truncated execution,
actor proof, byte-identical snapshot restoration, ownership, symlinks, parsing
and interrupted project reconstruction. Existing placement tests require actual
fresh idempotence with zero consumption. Isolated mutations target these guards.
Real cancellation/lost-ack/session-recovery probes are reported separately from
these simulations and from complete building attempts.

Retained calibration includes: corner occlusion/route timeout; removed helper but
uncollected drop; coarse placement arrival and residual native momentum; depleted
64-item stack; bottom-up removal stranding floating helpers; and a verifier wiring
error using intentionally compact V0 navigation as if it contained full actor/
threat metadata. None is retroactively relabelled an original success. Generic
fixes preserve ordinary 0.3-block upright walking, add settled bounded positioning,
permit one fresh safe same-height pickup approach, and add exact exposed C2 target
filtering without a second mining/placement motor. Over-tight 0.08-block automatic
centering itself produced a retained `stuck` stop in A08. I4 now keeps an already
valid actual pose and otherwise uses a settled 0.15-block radius with a small
in-cell bias away from the destination; all original face/reach/body fences stay.
C3 separates observed removal from drop collection: A07's roof was complete but a
falling dirt drop correctly failed C2. A07-removal-probe finished the same world
with native access and 71/71 proof; it remains a DEBUG continuation, not fresh.
A09 then passed uninterrupted, but A10 stopped with 15/71: the mathematical
standing centre was in range while an allowed arrival offset was 3.019 blocks
away. The fixed sampler now reserves the WHOLE 0.15-block arrival interval:
planned eye reach ≤2.8 and expanded body margins, with small in-cell samples.
A11–A13 form a separately frozen unchanged-source repeat cohort; A09's earlier
success is retained but cannot substitute for this cohort's repetition gate.

A05 retained a fixture-load timeout before building. A06 retained an ENOSPC failure
including an incomplete audit record; after storage recovered its closed world was
sealed separately, with two blocks observed and no uncertain intent replay.
Atomic evidence publication now preserves the previous complete record on failure;
storage availability is checked before effects. No historical evidence was deleted.

## Actual qualification results

**A: GO** for the unchanged-source A11–A13 repeat cohort. **B: GO** for the
first strict accepted real-model run, B12. **B repeatability: NO-GO / not
established**: only B12 passed the unchanged-source B12–B14 cohort; B13 and B14
remain failures under the same acceptance contract.

| Metric | Deterministic A11 / A12 / A13 | Real model B12 |
|---|---|---|
| Strict benchmark acceptance | PASS / PASS / PASS | PASS |
| Required blocks independently correct | 71 / 71 / 71 | 71 |
| Executed skill operations | 288 / 288 / 288 | 336 |
| Project journal operations | not applicable | 354 |
| Verified placement events, including helpers | 82 / 82 / 82 | 77 |
| Failed runtime operations | 0 / 0 / 0 | 3 |
| Compiler rejections | 0 / 0 / 0 | 0 |
| Model calls | 0 / 0 / 0 | 22 |
| Plan geometry revisions | not applicable | 0 |
| Feedback-conditioned decisions | not applicable | 4 |
| Measured total wall seconds | 692.43 / 678.42 / 660.71 | 887.58 |
| Helpers remaining | 0 / 0 / 0 | 0 |
| Final safe reachable interior proof | PASS / PASS / PASS | PASS |
| Agent terminal recognition | not applicable | `OBJECTIVE_VERIFIED` |

Project-journal operations include the persistent project accounting used for the
512-operation bound; executed skill operations are the actually dispatched BCL
operations. Placement events are mechanics metrics, NEVER positive independent
acceptance evidence. Feedback-conditioned decisions measure repair attempts, not
changes of the final geometry.

### B01: interpretation, corrections, and remaining navigation limit

The real tool-free `openai-codex / gpt-6.1-sol`, thinking high, authored its own
plan/programs, built walls from outside, and chose a **southern six-block dirt
stair**, unlike A's western ten-block stair plus interior aid. It independently
completed all 46 walls and 25 roof positions. Its actual decisions are exported in
[the recorded BCL history](evidence/superflat-building-B01.bcl) and in the evidence
JSON, separately from host observation exchanges. That history includes rejected
and partially executed batches and is **NOT replayable**.

One literal `sn\u200beak` (zero-width U+200B) was correctly rejected by the enum
compiler; subsequent source corrected the spelling. This is evidence of compiler
validation and model feedback, not a compiler implementation failure. The model
also recovered missing-wall/support views and the depleted first item stack.

After the roof it became stuck at feet approximately
**(2.500038, −57, 6.007832)**, health 20, `on_ground=true`. Native navigation was
`ready=true` but **`current_center_access=false`**; the height/XZ source cell
`[2,-57,6]` was not a safe mesh node. Repeated native M0/dig attempts returned
`no_known_safe_route`; two attempted support placements were rejected by the
unchanged body exclusion. No raw input, teleport, native save edit or operator
rescue bypassed these fences. It stopped at **`no_relevant_progress_budget`**
with 401 builder operations (403 including the final independent observation),
well before the 512-operation / 60-call / 2700-second ceilings.

The closed save confirms **71 correct, zero wrong/missing/unknown required blocks**,
closed roof, clear entrance/interior and intact floor, BUT six scaffold blocks
remain and final safe interior/access proof fails. Original B01 remains incomplete.
This implicates the combination of the model's different route and the common
motor's partial-support/overhang recovery limit, NOT only LLM planning. A's
success does not prove that B's different staircase/timing is supported. No
strategy-specific fix or second planner was added to manufacture a B success.

### Fresh Test-B follow-up B02–B14

Thirteen additional IDs after B01 were started from the same canonical closed
snapshot. B06 failed before a model exchange while the native world list was still
populating; every other ID produced a sealed result snapshot. Every started ID is
retained and none is relabelled after a later source correction.

| Run | Calls / executed ops / failed actions | Independent closed-world result | Terminal result |
|---|---:|---|---|
| B02 | 31 / 459 / 7 | 71/71, zero helpers; no final native access/safe-player proof | `project_operation_budget` |
| B03 | 28 / 339 / 7 | 71/71, zero helpers, native interior access true; safe-player false | agent verified, independent acceptance failed |
| B04 | 40 / 443 / 12 | 71/71, two helpers | `project_operation_budget` |
| B05 | 2 / 4 / 0 | 0/71 | external model command returned nonzero |
| B06 | 0 / 0 / 0 | no measured world result | asynchronous world-list startup failure |
| B07 | 32 / 488 / 7 | 71/71, zero helpers; no final native access/safe-player proof | `project_operation_budget` |
| B08 | 16 / 180 / 3 | 55/71, six helpers | malformed model JSON (`Invalid \\escape`) |
| B09 | 45 / 483 / 7 | 71/71, zero helpers; no final native access/safe-player proof | `project_operation_budget` |
| B10 | 58 / 415 / 18 | 71/71, three helpers | `project_operation_budget` |
| B11 | 36 / 446 / 7 | 71/71, one helper; no final native access/safe-player proof | `project_operation_budget` |
| **B12** | **22 / 336 / 3** | **71/71, zero helpers, access and safe player true** | **`OBJECTIVE_VERIFIED`; strict PASS** |
| B13 | 37 / 425 / 8 | 71/71, zero helpers; no final native access/safe-player proof | `project_operation_budget` |
| B14 | 35 / 457 / 7 | 71/71, zero helpers; every independent physical predicate true | agent remained `OBJECTIVE_INCOMPLETE`; strict FAIL |

B03 shows that project recognition cannot replace the unchanged native safety
predicate. B14 shows the converse: a later independent world certificate cannot
replace required in-run agent recognition. B02, B07, B09, B11 and B13 likewise
show that exact or nearly exact geometry is insufficient without all terminal
predicates.

The failures exposed reusable orchestration defects, corrected between fresh runs:

- bounded inspection follow-ups continue one active `final_sweep` instead of
  discarding still-fresh evidence;
- read-only inspection reserves ordinary BCL budget and restores its caller's
  model-selected origin, including bounded staged returns through observed native
  navigation;
- fixture loading polls asynchronous world-list population before making the
  unique owned-world selection;
- malformed model JSON becomes bounded model feedback rather than a host abort;
- late inspection preserves mandatory `V0`/`I0`, one final model action and the
  independent host audit;
- a successful model program already ending in terminal `V0` plus `I0` satisfies
  the mandatory follow-up instead of consuming it a second time;
- future private audits retain bounded malformed replies and nonzero process exit
  metadata without retaining stderr.

B05's historical process failure cannot be diagnosed more precisely: the adapter
then discarded stderr and did not record the exit code. B08's malformed reply was
also not retained by that older adapter. Those evidence gaps are stated rather
than reconstructed.

B12 is the first genuine strict Test-B **GO**: the model reached
`OBJECTIVE_VERIFIED`, and the independent audit confirmed 71/71, zero helpers,
clear entrance/interior, complete roof, intact floor, native interior access and a
safe player. The exact post-B12 source was frozen with canonical payload SHA-256
`5ffe4a310a083d1932e25b42fa016c8f70b7dd034cb5cdf597a3b46672bd923f`
before B13 and remained byte-identical through B14. Strict repeatability is still
**NO-GO / not established**: B12–B14 produced 1/3 accepted runs. B14 independently
completed the physical objective, so the cohort's independent-objective rate is
2/3, but its missing agent terminal recognition remains a real failure.

### Fault and recovery qualifications

Fresh isolated fault runs independently rejected incomplete states: F01 truncated
program **4/71**; F02 lost acknowledgement **4/71**; F03 cancellation **0/71**.
Cancellation was observed during acting and terminated `cancelled` with cleanup
`released`. R02 restored F02's closed world, rebound the new actor, reconciled a
COPY of its durable pending journal without replay, and sent a NEW request for a
freshly observed existing block: `desired_block_already_observed`, unchanged
inventory, original journal unchanged. This is fault/idempotence PASS, not a house
success or autonomous construction replay.

### Denominators and regression

Four fresh construction runs ultimately passed (A09 and A11–A13); only A11–A13
qualify the frozen final implementation's **3/3 consecutive repeat gate**. Across
all calibration versions there were 12 fresh construction starts, eight incomplete
(including A06 storage failure), plus A05's separate zero-building startup failure.
Debug continuations are separate: A07-removal-probe completed a saved failed world,
while the earlier A04 continuations retain their original failures. Do NOT report
all historical attempts as a 100% end-to-end success rate. Test B now has fourteen
started fresh IDs B01–B14: thirteen result-producing real-model runs and B06's
retained pre-exchange startup failure, with **one strict accepted run, B12**. The
unchanged-source B12–B14 assessment cohort is 1/3 for strict acceptance and 2/3
for the independent physical objective. This remains one fixed owned snapshot and
model configuration, not a multi-seed or provider reliability study.

Final automated checks for the frozen A11–A13/B01 assessment: **424 Python tests
PASS; 298 isolated mutations killed** (142 skills, 29 projects, 22 benchmark,
24 BCL, 14 gateway, 33 native, 20 controller, 14 campaign), Gradle check PASS,
native TLS interop **10 PASS**. Tests are simulations/contracts unless explicitly
listed above as native runs. Historical invalid mutation/harness attempts,
original failures and incomplete storage artifacts remain private and are not
silently replaced by successful facts.

Affected-scope qualification through B14: **466 Python tests PASS**; project
mutations **38/38 killed**; building mutations **23/23 killed**; skill mutations
**157/157 killed**. Final `ccc index`: **281 files, 3665 chunks, zero errors**.
Gradle and TLS interop were **NOT RUN** for this Python/test-harness-only follow-up;
the earlier qualified Java/TLS results remain historical evidence, not a newly
rerun claim. The client was closed through the native `Quit Game` widget; Minecraft,
launcher and benchmark processes were absent and ports 8879/8765 were closed.

### Post-rotation deterministic regression

Timed camera integration was checked independently of the later Test-B qualification.
Three fresh failures remain retained: A16 stopped before operations because the
separate private gateway certificate had expired; A17 reached 48/71 then fell
while turning/driving on a narrow elevated route; A18 reached 46/71 then could
not acquire an exact support face from a coarse but formally valid arrival pose.
The generic motor now overlaps turning and driving only on freshly proven broad
lateral support, and automatic placement recentres to the most centred known safe
pose when the current pose is not precise enough. No house-specific planner or
native generator was added.

Fresh restored-snapshot A19 then passed: **71/71**, 288 executed operations,
82 verified native placement events, zero failed actions and all entrance,
interior, native access, roof, floor and safe-player predicates true in 342.66 s.
A16–A18 were not resumed or relabelled. A19 is a regression, not a new Test-A
repeat cohort and not a Test-B rerun. Separate timed-rotation, 211/211 movement
and A19 gates are in [rotation-benchmark.md](rotation-benchmark.md) and
[evidence/rotation-benchmark.json](evidence/rotation-benchmark.json).

See [machine-readable scoped results](evidence/superflat-building.json). Fresh
trials, debug continuations, startup/storage failures, read-only QA and injected
faults have separate denominators. Report submitted BCL operations separately from
completed skill operations and verified placement events. Wall-clock runtime
includes model deliberation for B; native key-pulse counts and model token costs
are not claimed. One frozen seed/snapshot is not new-world, hostile-Survival,
24/7, general terrain or multi-tenant qualification.
