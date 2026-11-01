# Blockwire — consolidated development and change history

This document provides a coherent account of **how the currently qualified working
tree evolved**, which technical changes were made, which failed attempts remain
retained, and which claims are supported by real Minecraft evidence.

It does not replace the more narrowly scoped specifications. The authoritative
references remain:

- [Architecture](architecture.md)
- [Protocol](protocol.md)
- [Skills](skills.md)
- [BCL/1](bcl.md)
- [Persistent Projects](projects.md)
- [Superflat benchmark](superflat-building.md)
- [Movement benchmark](movement-benchmark.md)
- [Rotation benchmark](rotation-benchmark.md)
- [machine-readable rotation/regression evidence](evidence/rotation-benchmark.json)

Private certificates, API keys, journals, snapshots, saves, and raw model replies
are **not** part of this documentation and must not be included in a distribution
bundle.

---

## 1. Starting point and unchanged system boundaries

Blockwire continues to use exactly one execution stack:

```text
external model or local program
    -> BCL/1 or typed Python goals
    -> existing registry and skill runtime
    -> Player/Backend
    -> authenticated TLS WebSocket connection
    -> native Minecraft actions
    -> Minecraft physics and observed postconditions
```

Development introduced **no second movement, building, or rotation controller**.
The following boundaries remain unchanged:

- TLS is mandatory; there is no plaintext or trust-all fallback.
- Each instance has a separately trusted certificate identity.
- API-key checks, hostname verification, loopback defaults, and connection bounds
  remain in place.
- F8 or an explicit stop releases native inputs.
- Player and world replacement are fenced with `actor_session`.
- Native Minecraft logic owns movement, collision, damage, jumping, crafting,
  inventory changes, and placement outcomes.
- An RPC receipt is not gameplay success.
- Success requires an observed goal postcondition.
- Uncertain effects are not replayed blindly.
- Cancellation and deadline checks occur before actions and inside long-running
  loops.
- Failed attempts, debug continuations, and recovery probes are not retroactively
  relabelled as fresh successes.

These boundaries guided every subsequent change.

---

## 2. Earlier foundation: native actions, skills, and Survival mechanics

The first development phase established the general actor stack:

- `Player(Backend)` as a small programmable actor API;
- pinned native TLS connectivity;
- bounded observation, inventory, menu, and input operations;
- skill registry, execution, ownership, status, and cooperative cancellation;
- native input leases instead of unbounded key presses;
- conservative visibility, terrain, and hazard observations;
- crafting, equipment, food, mining, placement, and UI fencing with observed
  postconditions.

The Survival and Stone Age attempts were built on that foundation. The retained
real tool-free success `attempt08` used `openai-codex / gpt-6.1-sol` and reached,
after 26 decisions:

- an observed peak of 18 cobblestone;
- a stone pickaxe;
- 20 health;
- `objective_verified: true`.

This success is not evidence of complete unattended Survival. Other attempts and
uninspected artifacts — especially `attempt09` — remain separate and are not
included in that claim.

---

## 3. BCL/1: compiler, typed IR, and gateway

The next phase introduced BCL/1 as a compact but fully validated control language
above the same skills.

### 3.1 Compiler and runtime boundaries

Implemented capabilities include:

- complete frame validation **before** the first effect;
- deterministic compilation into a frozen typed IR;
- command metadata generated declaratively from skill schemas;
- modal session state;
- FIFO jobs and events;
- durable request deduplication;
- separate meanings for `program_verified` and `objective_verified`;
- structured compiler diagnostics without `eval`, `exec`, or implicit execution;
- no rollback promise and no replay of uncertain effects.

`program_verified` confirms only the postconditions of executed BCL operations.
It does **not** automatically confirm the external overall objective.

### 3.2 Gateway hardening

The optional Python gateway additionally gained:

- separate controller and observer roles;
- actor binding through confirmed cleanup;
- bounded queues and visible overflow errors;
- quarantine/reaper logic for delayed cleanup;
- typed lifecycle events E104–E107;
- explicitly fenced respawn;
- responsive status/cancel operations while jobs are running.

The gateway is not a second planner. It still compiles and dispatches into the
existing runtime.

---

## 4. Persistent Projects and external planning

`projects.py`, `project_agent.py`, and `project_inspection.py` added persistent
project state. It separates:

- the plan authored by the model;
- outstanding intents;
- terminal operations;
- observed block state;
- native access geometry;
- independent objective verification.

Important safety rules include:

- lost acknowledgements must not force effect replay;
- old observations are not treated as fresh after actor or world replacement;
- model finish is not objective success;
- material arithmetic describes requirements but is not a building or progression
  strategy;
- read-only verification receives no mutation permissions.

Retained results include:

- A01: 56 calls, 40 placements, 43/43 accepted steps;
- A02/A03: no duplicate lost-ack execution, but failed roof descent;
- B03: six logs gathered, 24 planks crafted, and a structure built, followed by
  `OBJECTIVE_INCOMPLETE / no_relevant_progress_budget`;
- B04: operation limit 512;
- B07: 26/26 read-only checks;
- B08: `OBJECTIVE_VERIFIED`.

Each project result remains limited to its own scope.

---

## 5. Deterministic 5×5 Superflat benchmark

### 5.1 Fixture and acceptance

The building benchmark uses a byte-identified Minecraft 26.3 snapshot:

- seed `31052026`;
- origin `(0, -60, 0)`;
- start `[2.5, -60.0, -3.5]`;
- 46 wall blocks;
- 25 roof blocks;
- 71 required cobblestone blocks in total.

Independent acceptance checks:

- every required block;
- incorrect, missing, and unknown states;
- literally clear entrance and interior spaces;
- complete roof;
- intact floor;
- no remaining helper blocks;
- native access;
- a safe final player state.

Every fresh run restores the same closed, byte-verified snapshot. Administrative
commands are used only for fixture preparation and do not count as building work.

### 5.2 Generic corrections during development

The building attempts led to reusable mechanics improvements:

- fresh same-height pickup recovery;
- more precise, stably observed arrival;
- exact `GatherBlock.position` filtering;
- generic `remove_block`/C3;
- complete actor-bracket proof for final access verification;
- checking the full possible 0.15-block placement-arrival interval;
- conservative reach and body margins;
- no house-specific logic and no native house generator.

A01–A10 remain retained calibration failures, including deadline, reach,
inventory, storage, and startup problems.

### 5.3 Frozen decisions

The unchanged-source Test-A cohort A11–A13 passed 3/3:

- 71/71 required blocks;
- 288 executed skills each;
- 82 verified placement events each;
- no failed actions;
- every independent safety and access predicate satisfied.

Therefore **Test A remains GO**.

The real external-model run B01 built 71/71 required blocks but left six helper
blocks and had no valid final native access. It ended with
`no_relevant_progress_budget` and remains a historical **NO-GO**. The later B12 is
the first strict Test-B **GO**. The unchanged-source B12–B14 cohort, however,
passed only 1/3 strictly, so Test-B repeatability remains **NO-GO / not
established**.

F01–F03 and R02 qualify only fault/recovery behavior. They are not complete-house
successes.

---

## 6. Movement optimization and native tick telemetry

### 6.1 Measurement infrastructure

`MotionTrace.java` introduced a bounded ring buffer containing 4096 end-of-client-
tick samples. It records, among other fields:

- position and velocity;
- horizontal speed;
- yaw/pitch;
- collisions and ground state;
- bounding box;
- sprint/sneak/fall/health;
- actual and remotely owned inputs;
- actor, game-time, and monotonic-time identities.

The deterministic movement benchmark contains 49 scenarios and 211 repetitions
covering linear, diagonal, vertical, combined, curved, parkour, roof, and precision
cases.

### 6.2 Controller changes

Generic movement improvements included:

- conservative same-height diagonals;
- typed `flat`, `diagonal`, `step`, and `gap_jump` transitions;
- geometric Dijkstra costs instead of equal edge costs;
- deterministic tie-breaking;
- W/A/S/D quantization with short native leases;
- braking from observed velocity;
- separate bounded step and gap loops;
- proven run-up and landing geometry;
- conservative replanning only from observed-safe landings;
- stable arrival only when `horizontal_speed <= 0.004` and a second sample differs
  by no more than 0.005 m.

### 6.3 Iterative cohorts

Development was not reduced to the final success:

- `after-v1`: 208/211; three retained `step_x_descend` failures;
- `after-v2`: 210/211; one Level-4 platform failure;
- targeted Level-4 follow-up: 3/3;
- `after-v3`: 211/211;
- `after-v4`: 211/211 as the historical final movement cohort.

Compared with the original controller:

- success rate +16.6 percentage points;
- ticks −47.6%;
- full-stop runs −89.3%;
- input changes −68.0%.

Strict native performance parity remained **NO-GO** because Blockwire required
20.5% more ticks overall than the native reference. The Level-4 platform route was
the largest remaining gap.

---

## 7. Migration from fixed 8° steps to native time-based rotation

This section describes the most recent rotation development in detail.

### 7.1 Original problem

Normal non-combat camera movement was previously executed in fixed 8° Python
steps. Actual duration therefore depended primarily on angle and RPC/update rates,
not on the requested time.

Examples from `legacy-v1` at a nominal 200 ms:

- 15° approximately 149 ms;
- 45° approximately 499 ms;
- 90° approximately 999 ms;
- 135° approximately 1399 ms;
- 180° approximately 1899 ms;
- a wrapped 270° target approximately 999 ms along the short arc.

The legacy cohort reached 147/150 endpoints but passed only 17/141 applicable
duration checks. Three moving 180° cases timed out with approximately 4° remaining
error.

### 7.2 Before artifact and benchmark

Before implementation, the old controller was archived and hashed under
`build/rotation-benchmark/private/controller-before/`. A new deterministic
benchmark infrastructure was then added:

- `tests/rotation/reference.py` — 50 fixed scenarios;
- `tests/rotation/metrics.py` — pure trace evaluation;
- `tests/rotation/live.py` — live harness;
- `tools/rotation_benchmark.py` — fixture and run control.

The scenarios cover 100/200/400 ms, yaw, pitch, combined axes, wraparound,
movement, cancellation, supersession, and sequences.

### 7.3 Native implementation

`src/main/java/dev/blockwire/RotationController.java` was added.

The controller:

- holds exactly one plan per actor;
- uses `System.nanoTime()`;
- interpolates on real client ticks;
- supports `linear` and `smoothstep`;
- uses the shortest equivalent yaw arc;
- clamps pitch to the valid range;
- moves yaw and pitch simultaneously;
- sets the exact equivalent target at completion;
- starts a new target from the **actual currently applied** view;
- does not restart identical active targets;
- owns no movement key;
- reports active/completed/cancelled/superseded state and session changes.

### 7.4 Protocol and SDK compatibility

The existing `look` command gained optional fields:

- `duration_ms`: strict integer 1…5000;
- `rotation_profile`: `linear` or `smoothstep`.

When `duration_ms` is omitted, the old immediate `look` behavior remains
unchanged. A profile without a duration is rejected before any effect.

`Player.look(...)` received the same strict validation. Above it,
`rotate_view_timed(...)` performs normal non-combat turns as 200-ms smoothstep by
default and checks the deadline and actor binding before the request.

BCL signatures remain unchanged. V2 internally uses the same generic time-based
rotation and continues to verify observed orientation.

### 7.5 Lifecycle and lease separation

Originally, every input release also caused a global camera cancellation. That was
incorrect for independent movement and camera leases.

`Blockwire.java` therefore separates:

- `releaseInputs()` — releases only native input keys and their leases;
- `release()` — global stop that also cancels the camera plan.

Consequently:

- natural movement-lease expiry does not stop an independent rotation;
- F8, explicit stop, authority loss, actor/world replacement, death, pause, or UI
  replacement still cancel the plan.

### 7.6 Telemetry and observation

`observe` now includes the state of the current or most recent camera plan.
`MotionTrace` additionally records per tick:

- rotation ID and status;
- target yaw/pitch;
- requested duration;
- profile.

A scheduling receipt explicitly remains **not** endpoint proof.

### 7.7 Migration of normal callers

The old fixed-turn implementation was removed from normal non-combat paths.
Migrated callers include:

- `approaching.py`;
- `excavating.py`;
- `eating.py`;
- `viewing.py`;
- `item_actions.py`;
- `woodcutting.py`;
- `searching.py`;
- normal navigation in `motion.py`.

Stopped visual scans now use at most 17 observations around four native 90°
targets instead of 46 individual 8° steps.

Combat behavior was intentionally not migrated and remains separate.

### 7.8 Tests and mutations

New deterministic contracts include:

- RT01–RT06 in `python/tests/test_rotation.py`;
- RB01–RB05 in `python/tests/test_rotation_benchmark.py`;
- 39 native checks in `RotationContractTest.java`;
- additional continuous-motion contracts;
- mutations for duration, profile, shortest yaw, deadline ordering,
  interpolation, actor fence, exact endpoint, retargeting, lease independence,
  and legacy compatibility.

The simulated players were extended to model elapsed-time interpolation,
retargeting, idempotence, and cancellation. These tests are contracts, not
standalone Minecraft acceptance.

---

## 8. Benchmark and integration corrections during rotation introduction

### 8.1 Analysis errors in the benchmark harness

The first post-change evaluations exposed errors in measurement logic:

- an old `cancelled` plan could be attributed incorrectly to the next run;
- no-op rotations could not receive a normal duration check;
- duration gates had to count only applicable cases.

These were benchmark-evaluation errors, not retroactive relabelling of runs. Raw
data and failed attempts were retained. The canonical cohorts then became:

- `linear-v2`: 150/150, duration 141/141;
- `smoothstep-v2`: 150/150, duration 141/141;
- zero instant snaps and zero lost telemetry samples in both.

Smoothstep remained the 200-ms default because the profile has a mathematically
smoothed slope at the beginning and end. Linear remains explicitly selectable.

### 8.2 Movement regression: `combined_xyz`

An early post-rotation movement run showed failures in `combined_xyz`. The causes
were:

1. temporarily incomplete support observations;
2. W/A/S/D quantization against a stale yaw while a time-based turn was active.

Corrections:

- stop and replan during transient support uncertainty;
- use a fresh actor-fenced view before direction quantization;
- add CM15 and CM16 as regression tests with matching mutations.

`after-rotation-v3` then passed 211/211.

### 8.3 Building regression A16: expired separate gateway certificate

A16 ended before any operation because the private certificate used only by the
benchmark gateway had expired.

A new private benchmark identity was created. This administrative failure was not
relabelled as gameplay failure or success; A16 remains a zero-operation failed
run.

### 8.4 Building regression A17: turning on narrow elevated support

A17 reached 48/71 required blocks and then fell during a combined turn/drive phase
on a narrow elevated route.

The generic correction `_broad_steering_support(...)` permits turn/drive overlap
only when fresh lateral support cells are proven at both the source and forward
areas. Otherwise movement stops and replans.

CM17 and a targeted mutation cover this boundary. A 14/14 safety-smoke cohort
passed afterward.

### 8.5 Building regression A18: formally valid but unfavorable placement pose

A18 reached 46/71 required blocks. A walk ended inside the permitted 0.3-block
radius but was laterally offset enough that no exact support face could be acquired
for the next placement.

The correction in `item_actions.py`:

- accepts an existing auto-position pose only when it is precise enough at the
  known cell center;
- otherwise selects the most centered known-safe placement point;
- retains the 0.15-block placement-arrival radius and the complete reach/body
  interval checks.

A placement contract and mutations for recentering and center preference were
added.

### 8.6 Fresh building success A19

A19 again started from the unchanged closed baseline snapshot and passed:

- 71/71 required blocks;
- 288 executed operations;
- 82 verified native placement events;
- zero failed actions;
- every entrance, interior, access, roof, floor, and safe-player predicate;
- 342.66 seconds runtime.

A16–A18 were not resumed or transformed into A19.

### 8.7 Final movement and rotation runs

The following ran against the final production source:

- `after-rotation-v4`: 211/211 movement repetitions;
- 17,908 total ticks, median 70;
- 227 full-stop runs;
- 1,756 input changes;
- maximum horizontal error `0.2900973203315447`;
- no health loss;
- every run settled;
- zero lost trace samples.

A final smoothstep source smoke passed 8/8 with 7/7 applicable duration checks and
zero instant snaps.

---

## 9. Final qualification decisions

| Area | Decision | Basis |
|---|---|---|
| Native time-based rotation | **GO** | Linear 150/150, smoothstep 150/150, duration 141/141 each |
| Movement after rotation | **GO** | unchanged 211-run cohort: 211/211 |
| Fresh deterministic building regression | **GO** | A19: 71/71 and every independent predicate |
| Historical Superflat Test A | **GO** | frozen A11–A13 cohort 3/3 |
| Historical Superflat Test B01 | **NO-GO** | no final cleanup/access acceptance |
| Superflat Test B — demonstrated single run | **GO** | B12: agent recognition plus complete independent acceptance |
| Superflat Test B — unchanged-source repeatability | **NO-GO** | B12–B14: 1/3 strictly accepted; B14 only independently physically complete |
| Strict native movement-performance parity | **NO-GO** | historical tick parity not reached |

The positive gates and the negative repeatability decision do not replace one
another. Rotation success cannot hide movement or building failure; one Test-B GO
does not establish repeatability.

---

## 10. Final QA

The qualified source state passed:

- **455 Python tests: PASS**;
- Gradle `check`: **PASS**;
- native rotation contracts: 39 checks;
- MotionTrace contracts: 12 checks;
- controller lease/wiring contracts: 45 checks;
- terrain contracts: 18 checks;
- real Netty/Python TLS interoperability: **10/10 PASS**;
- skill mutations: 155/155 killed;
- native mutations: 46/46 killed;
- controller mutations: 20/20 killed;
- building mutations: 22/22 killed;
- total: **243/243 killed**.

The qualified test JAR has SHA-256:

```text
898c596dffa2ecf29f81f95a30df16d91a0d759f3ced9d3ed35efa7083eeee31
```

The client was finally observed at the title screen with no loaded world and no
active camera plan, closed through the native `Quit Game` button, and the remaining
waiting launcher wrappers owned by the test were then stopped. Port 8765 was
closed.

The final `ccc index` recorded 281 files and 3597 chunks with no errors.

---

## 11. Important changed files

### Native Java layer

| File | Change |
|---|---|
| `src/main/java/dev/blockwire/RotationController.java` | new actor-bound elapsed-time controller |
| `src/main/java/dev/blockwire/Blockwire.java` | integration, tick call, `releaseInputs()`/global `release()` |
| `src/main/java/dev/blockwire/Protocol.java` | duration and profile validation |
| `src/main/java/dev/blockwire/MotionTrace.java` | rotation metadata per client tick |
| `src/main/java/dev/blockwire/Observations.java` | rotation state in `observe` |
| `src/main/java/dev/blockwire/NavigationView.java` | conservative typed movement geometry |

### Python runtime and skills

| File | Change |
|---|---|
| `python/src/blockwire/client.py` | strict timed `Player.look(...)` |
| `python/src/blockwire/skills/motion.py` | timed rotation, fresh view, support-gated overlap |
| `python/src/blockwire/skills/walking.py` | geometric routes and stable arrival |
| `python/src/blockwire/skills/item_actions.py` | precise placement recentering |
| `python/src/blockwire/skills/approaching.py` | native time-based non-combat turning |
| `python/src/blockwire/skills/viewing.py` | observed final orientation |
| `python/src/blockwire/skills/searching.py` | four native quarter-turn scans |
| `python/src/blockwire/skills/woodcutting.py` | timed scan/aim |
| `python/src/blockwire/skills/excavating.py` | actor-fenced timed aim |
| `python/src/blockwire/skills/eating.py` | timed non-combat view control |

### Benchmarks and tests

| File/directory | Purpose |
|---|---|
| `tests/rotation/` | reference, live harness, and pure metrics |
| `tools/rotation_benchmark.py` | rotation fixture and live cohorts |
| `tools/report_rotation_benchmark.py` | final separate gates and evidence generation |
| `python/tests/test_rotation.py` | Python rotation contracts |
| `python/tests/test_rotation_benchmark.py` | benchmark/metrics contracts |
| `python/tests/test_continuous_motion.py` | turn/drive, fresh-view, and support regressions |
| `python/tests/test_placement.py` | placement recentering and pose selection |
| `src/contractTest/java/dev/blockwire/RotationContractTest.java` | native lifecycle/interpolation contracts |
| `tests/run_skill_mutations.py` | Python motor/rotation/placement mutations |
| `tests/run_mutations.py` | native rotation and lease mutations |

---

## 12. Retained failures and open areas

The following were intentionally not relabelled as successes:

- the three legacy rotation timeouts;
- every intermediate movement cohort before 211/211;
- A16, A17, and A18;
- B01–B11 plus B13 and B14; several runs had all 71 required blocks physically
  present, and B14 had complete independent world acceptance without correct agent
  terminal recognition;
- debug continuations and recovery probes;
- historical native performance parity.

The following remain outside general qualification:

- slabs, fluids, and arbitrary collision shapes;
- general caves and unknown long-distance routes;
- hostile, food-constrained, or unattended Survival reliability;
- complete Nether/End progression;
- broad modpack compatibility;
- general combat-camera migration;
- 24/7 operation or multi-tenant control.

Damage avoidance remains best effort and is not immunity.

---

## 13. Evidence and artifact map

Public, reviewable documents:

- `docs/rotation-benchmark.md`
- `docs/evidence/rotation-benchmark.json`
- `docs/movement-benchmark.md`
- `docs/evidence/movement-benchmark.json`
- `docs/superflat-building.md`
- `docs/evidence/superflat-building.json`

Important local ignored artifacts:

- `build/rotation-benchmark/legacy-v1/`
- `build/rotation-benchmark/linear-v2/`
- `build/rotation-benchmark/smoothstep-v2/`
- `build/rotation-benchmark/smoothstep-final-smoke-v3/`
- `build/movement-benchmark/after-rotation-v4/`
- `build/superflat-benchmark/A16/` through `A19/`
- `build/superflat-benchmark/B02/` through `B14/`, plus `B06-live.log`
- `build/superflat-benchmark/B12-repeatability-source-freeze.json`
- `build/rotation-benchmark/final-verification/`

SHA-256 of the final public rotation evidence at the time of this documentation:

```text
e3dff08e98f8a8aa97fe0520939b7afb4a13b77d8dad9fc17ba953b2b8b1247c
```

The local raw artifacts intentionally remain outside distributable bundles.

---

## 14. Publication status

The described changes were implemented and qualified locally. The operator then
explicitly authorized a local commit of that state.

The following remain unauthorized and did not occur:

- push;
- tag;
- upload;
- release;
- production deployment.

Any publication or installation outside the explicitly authorized test instance
requires separate approval.

---

## 15. Fresh Test-B follow-up B02–B14

After the authorized base commit `e788f268a2b0503f41e7bc17bd0fc48c2fdca0e3`,
thirteen additional unique Test-B IDs were started. Every run used the same
canonical snapshot
`d61d166e4431e7693907cc0590f1808e2d8f12d62befe3b0a5a64c22b70696a7`.
No started run was resumed, renamed, or reclassified as success after a correction.

### 15.1 Results

- B02: 71/71, no helpers, but no final native access/safe-player proof;
  `project_operation_budget`.
- B03: 71/71 and native interior access, but safe-player false. The journal
  reported `OBJECTIVE_VERIFIED`; independent acceptance remained false.
- B04: 71/71, two helpers; `project_operation_budget`.
- B05: external model process failed on the second request; 0/71.
- B06: startup failure before an exchange because the native world list had not
  finished populating asynchronously.
- B07: 71/71, no helpers, but no final access/safe-player acceptance;
  `project_operation_budget`.
- B08: 55/71 and six helpers; historical termination on an invalid JSON escape.
- B09: 71/71, no helpers, but no final access/safe-player acceptance;
  `project_operation_budget`.
- B10: 71/71, three helpers; `project_operation_budget`.
- B11: 71/71, one helper, no final access/safe-player acceptance;
  `project_operation_budget`.
- **B12: first strict GO** — 22 model calls, 336 executed operations, 3 failed
  actions, 77 placement events, 71/71, no helpers, native interior access, safe
  player, and correct agent recognition:
  `OBJECTIVE_VERIFIED / trusted_project_postcondition`.
- B13: 71/71 and no helpers, but outside with no final interior-access or
  safe-player proof; `project_operation_budget`.
- B14: 71/71, no helpers, and every independent physical predicate true, but agent
  terminal state `OBJECTIVE_INCOMPLETE / project_operation_budget`. Therefore
  `passed:false` remains correct.

Together with B01, there are fourteen started fresh Test-B IDs, thirteen
result-producing model runs, and **one accepted success, B12**. Demonstrated Test-B
capability is therefore **GO**. Unchanged-source repeatability remains
**NO-GO / not established**.

### 15.2 Source freeze and repeatability

Immediately after B12, the relevant source state was durably frozen before B13:

- artifact: `build/superflat-benchmark/B12-repeatability-source-freeze.json`;
- canonical payload SHA-256:
  `5ffe4a310a083d1932e25b42fa016c8f70b7dd034cb5cdf597a3b46672bd923f`;
- base commit: `e788f268a2b0503f41e7bc17bd0fc48c2fdca0e3`;
- every listed file remained byte-identical through B14.

The fixed B12–B14 cohort produced:

- strict acceptance including agent terminal recognition: **1/3**;
- independent physical objective acceptance: **2/3** (B12 and B14);
- no reproduction of B12's strict success in B13 or B14.

B14 is not promoted to success: independent world truth does not replace required
correct agent recognition. Conversely, B03 remains a failure despite its agent
recognition because independent safety acceptance failed.

### 15.3 Generic corrections

The corrections remained independent of the house itinerary:

- active `final_sweep` evidence survives bounded inspection follow-ups;
- read-only inspection reserves BCL budget and restores the model-selected origin
  through observed native navigation, including bounded intermediate targets;
- fixture loading waits boundedly for asynchronous world-list population;
- malformed model JSON becomes model feedback instead of a host abort;
- mandatory follow-up, one final model action, and the independent host audit are
  reserved before the operation limit;
- a model program already ending successfully with `V0` and `I0` is reused as the
  mandatory follow-up rather than duplicated;
- future private audits preserve bounded malformed replies and the numeric exit
  code of a failed model process, still without stderr.

The exact cause of B05 can no longer be reconstructed: the adapter at that time
discarded stderr and did not store the exit code. Likewise, B08's raw malformed
reply was not stored. These gaps remain documented as gaps.

### 15.4 Follow-up QA and shutdown

The current, still uncommitted follow-up state passed:

- **466 Python tests: PASS**;
- project mutations: **38/38 killed**;
- building mutations: **23/23 killed**;
- skill mutations: **157/157 killed**;
- `ccc index`: **281 files, 3665 chunks, zero errors**.

Gradle and TLS interoperability were **not rerun** for these Python/test-harness-
only changes. Earlier Java/TLS results remain historical evidence and are not
presented as a new run.

The client was closed from the title screen through the native `Quit Game` button.
Minecraft, launcher, and benchmark processes were absent afterward; ports 8879
and 8765 were closed. No commit, push, tag, upload, release, or deployment was
authorized or performed for this follow-up.
