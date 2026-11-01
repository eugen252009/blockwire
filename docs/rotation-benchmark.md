# Native time-based camera rotation qualification

This qualification replaces Python's former fixed 8° camera stepping with one
actor-bound native controller driven by elapsed monotonic time. The execution
path remains:

`goal -> existing Python skill/runtime -> native look request -> RotationController -> Minecraft client ticks`

There is no second movement controller, renderer hook, teleport, custom physics,
LLM call or benchmark-only gameplay implementation. Combat camera behavior remains
separate and unchanged.

## Contract

A timed `look` optionally accepts:

- `duration_ms`: strict integer 1…5,000;
- `rotation_profile`: `linear` or `smoothstep`.

Omitting `duration_ms` preserves the legacy immediate `look` operation. Timed
rotation uses `System.nanoTime()`, actual Minecraft client updates, shortest-yaw
interpolation, clamped pitch and an exact equivalent final endpoint. Yaw and pitch
move simultaneously. `smoothstep` is the normal noncombat skill default at 200 ms;
`linear` remains explicitly selectable.

Only one camera plan is active for an actor. Repeating an identical active request
is idempotent. A different request supersedes from the actually applied current
view rather than the old start or target. Explicit stop/F8, authority loss,
player/world replacement, death, pause or a gameplay UI cancels it. Natural
movement-key lease expiry does **not** cancel an independent camera plan. The
controller owns no W/A/S/D, jump, sneak or sprint key.

A scheduling receipt is not completion. Qualification reads terminal rotation
state and end-of-client-tick `MotionTrace` samples.

## Fixed cohort

The owned Minecraft 26.3 snapshot has identity
`209d2035d44c6824f3958d924b35147fb250eb61d36f4ff189884e9b0c92f481`.
The full 50-scenario set has identity
`e51fbdcc599a007ff9e864432511f2adfa00d8088aa764fe4cfef6fbbc59fea5`.
Each full variant runs three retained repetitions per scenario, 150 total, covering:

- 15°, 45°, 90°, 135°, 180° and wrapped 270° yaw requests;
- 100, 200 and 400 ms durations;
- upward/downward pitch, pitch limits and simultaneous yaw/pitch;
- ±179° wraparound and other shortest-arc boundaries;
- walk, sprint, sneak and diagonal movement during rotation;
- cancellation, supersession, idempotent/no-op and three-turn sequences.

Each cohort restores and byte-validates the same closed snapshot. Acceptance uses
an explicit duration tolerance of `max(75 ms, 35% of the request)`, endpoint error
at most 0.25°, stable cancellation, no dropped telemetry and an instant-snap guard:
for a requested arc above 5°, no one tick may consume 80% or more of the arc.
Requested timing is necessarily quantized by real client ticks; no fixed 50 ms
interval is assumed by the implementation.

## Results

| Controller/profile | Endpoint/cancel success | Applicable duration checks | Instant snaps | Dropped samples |
|---|---:|---:|---:|---:|
| Legacy fixed 8° stepping (`legacy-v1`) | 147/150 | 17/141 | 0 | 0 |
| Native linear (`linear-v2`) | **150/150** | **141/141** | **0** | 0 |
| Native smoothstep (`smoothstep-v2`) | **150/150** | **141/141** | **0** | 0 |

The three legacy failures were all `moving_walk_yaw180_200ms`; each timed out with
about 4° remaining. Legacy duration was angle-dependent rather than request-time
dependent: its median measured duration was approximately 999 ms overall and its
median absolute duration error approximately 799 ms.

### Requested-duration groups

These medians include all applicable angles and combined-axis cases in each group.
No-op and cancellation cases are excluded from duration acceptance.

| Profile | Request | Runs | Median measured | Median absolute error | Median maximum tick step |
|---|---:|---:|---:|---:|---:|
| Legacy | 100 ms | 33 | 998.25 ms | 898.25 ms | 8.00° |
| Legacy | 200 ms | 75 | 1098.71 ms | 898.71 ms | 8.00° |
| Legacy | 400 ms | 33 | 998.58 ms | 598.58 ms | 8.00° |
| Linear | 100 ms | 33 | 133.74 ms | 33.74 ms | 43.83° |
| Linear | 200 ms | 75 | 234.98 ms | 34.98 ms | 23.24° |
| Linear | 400 ms | 33 | 417.45 ms | 33.85 ms | 11.55° |
| Smoothstep | 100 ms | 33 | 117.30 ms | 31.69 ms | 58.49° |
| Smoothstep | 200 ms | 75 | 234.91 ms | 34.93 ms | 33.49° |
| Smoothstep | 400 ms | 33 | 385.12 ms | 17.02 ms | 16.45° |

Large arcs requested over 100 ms necessarily span only a few real client updates,
so their per-tick angular change is large. They still remain elapsed-time plans,
not an immediate orientation snap, and all pass the declared one-tick snap guard.
For ordinary noncombat behavior the default remains 200 ms smoothstep.

### Concurrency and lifecycle

For both new profiles:

- all 36 moving repetitions completed while retaining their movement stream;
- no moving trace contained an internal full-stop run;
- all six cancellation repetitions reached a stable cancelled orientation;
- all six supersession repetitions reached the replacement target;
- all 12 wraparound repetitions followed the short equivalent arc;
- all nine combined-axis repetitions completed;
- endpoint overshoot was zero apart from floating-point noise below `1.5e-14°`.

Linear and smoothstep both qualify. Smoothstep is selected as the default because
its mathematical profile eases to zero slope at each endpoint; linear remains
available when constant angular velocity is desired. The median profile-reference
trajectory RMSE was 0.137° for linear and 0.126° for smoothstep.

A final-source smoothstep smoke (`smoothstep-final-smoke-v3`) covered 100/200/400
ms, moving rotation, wraparound, simultaneous axes, cancellation and supersession:
8/8 endpoint/cancel successes, 7/7 applicable duration checks and zero instant
snaps. Its recorded source hashes match the final motion/client/native rotation
sources.

## Independent regression gates

Rotation is not allowed to stand in for movement or building acceptance.

### Movement: GO

The unchanged 49-scenario, 211-repetition Minecraft 26.3 movement cohort was rerun
as `after-rotation-v4` against the final source:

- **211/211** independently settled successes;
- 17,908 total ticks, median 70;
- 227 full-stop runs and 1,756 input changes;
- maximum horizontal error `0.2900973203315447`, inside 0.3;
- zero health loss, all runs settled and zero dropped samples.

Relative to the historical qualified `after-v4`, total ticks improved 0.5% and
input changes improved 7.7%; full-stop runs increased from 185 to 227 because the
final safety rule stops/replans on uncertain or narrow lateral support instead of
turning and driving concurrently. Correctness and safety remain the gate. The
historical strict native-performance-parity decision remains **NO-GO**.

### Deterministic building: GO

Fresh restored-snapshot run `A19` passed in 342.66 s:

- 71/71 independently verified required blocks;
- 288 executed operations and 82 verified native placement events;
- zero failed actions;
- entrance/interior clear, native interior access true, roof complete, floor
  intact and safe player true.

The final generic fixes do not add a house planner. Concurrent turn/drive is used
only when fresh lateral support is broad enough; otherwise movement stops/replans.
Automatic placement also recentres to a precise known safe pose when an otherwise
valid 0.3-radius arrival would leave the requested support face occluded.

Failed runs remain evidence:

- `A16`: zero-operation startup failure from an expired separate private gateway
  certificate;
- `A17`: partial 48/71 build after a narrow elevated-path fall;
- `A18`: partial 46/71 build after exact support-face acquisition failed from a
  coarse but formally valid arrival pose.

None was resumed or relabelled. `A19` is a fresh regression, not a replacement for
the frozen A11–A13 Test-A cohort. Historical Superflat Test A remains **GO** and
Test B/B01 remains **NO-GO**.

## Verification and evidence

Final gates on the qualified source:

- 455 Python tests: PASS;
- Gradle `check`: PASS, including 39 rotation, 12 motion-trace, 45 controller
  lease/wiring and 18 terrain contract checks;
- real Netty/Python TLS interoperability: 10/10 PASS;
- 155 skill, 46 native, 20 controller and 22 building mutations: **243/243
  killed**;
- installed and built test JAR SHA-256:
  `898c596dffa2ecf29f81f95a30df16d91a0d759f3ced9d3ed35efa7083eeee31`;
- final client observed at Title Screen with no world and no active camera plan,
  then exited through the native Quit Game widget.

The final machine-readable record is
[`evidence/rotation-benchmark.json`](evidence/rotation-benchmark.json). It contains
all separate Rotation/Movement/Building gates, profile aggregates, failure records,
source/artifact hashes and final QA results. Raw retained JSON/CSV traces, ended
world manifests and logs remain under ignored `build/rotation-benchmark/`,
`build/movement-benchmark/after-rotation-v4/` and
`build/superflat-benchmark/A16`…`A19`.

Private certificates, API credentials, snapshots, journals and ended saves are not
distributable. This evidence authorizes no commit, release, upload or production
deployment.

## Limits

This qualifies one owned Minecraft version and deterministic fixture. Tick timing
can vary with client load; the explicit tolerance is part of the claim. Combat
rotation is unchanged and separately scoped. Slabs, fluids, caves, arbitrary
collision shapes, hostile unattended Survival and broad mod-pack compatibility
remain unqualified.
