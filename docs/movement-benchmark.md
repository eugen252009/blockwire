# Deterministic native movement benchmark

This benchmark compares three ways of reaching the same fixed goals in an owned
Minecraft 26.3 client:

1. **Native reference** — ordinary native movement inputs following the declared
   fixture waypoints, without Blockwire planning.
2. **Before** — the preserved, unchanged Blockwire controller from before this
   optimization.
3. **After** — the final shared Blockwire route/motor used by `walk_to` and its
   existing callers.

No LLM is called. No teleport, velocity injection, custom collision, second
movement controller or benchmark-specific gameplay generator is used during a
measured run. Administrative commands only restore and position the owned fixture
before telemetry starts.

## Fixed cohort and acceptance

The closed snapshot identity is
`209d2035d44c6824f3958d924b35147fb250eb61d36f4ff189884e9b0c92f481`.
All canonical cohorts use scenario identity
`5f72a81f82a1ea1a62356a12d2a96a83942bd2eb028e87dba7bda0fa67670eb6`.
There are 49 hardcoded scenarios and 211 retained repetitions across:

- axial, diagonal and combined travel;
- walk/run/sneak modes and sub-block precision;
- 90°/180° turns, a gentle curve, S-curve and zigzag;
- one-block ascent/descent and stair sequences;
- single, repeated and diagonal gaps plus a multi-level platform route;
- construction-like roof access, descent and partial-support recovery.

Every independent cohort restores and validates the same closed snapshot. A run
passes only from the settled tick trace and final native position, not from an
input receipt or the skill's `arrived` claim. Failed repetitions remain in the
denominator.

The reference and Blockwire intentionally have different endpoint contracts:

- native reference: **1.0 block** horizontal radius;
- Blockwire before/after: **0.3 block** horizontal radius.

Consequently endpoint error and path length are not direct parity metrics. Health
loss, settled state, actual inputs and collision/velocity fields come from native
end-of-client-tick telemetry (`native_player_motion_ticks_v1`). No canonical run
lost a telemetry sample.

## Results

| Cohort | Success | Median ticks/run | Total ticks | Full-stop runs | Input changes | Health loss |
|---|---:|---:|---:|---:|---:|---:|
| Native reference (`vanilla-v2`) | **211/211 (100%)** | 58 | 14,945 | 59 | 475 | 0 |
| Unchanged controller (`before-v1`) | **176/211 (83.4%)** | 141 | 34,351 | 1,737 | 5,941 | 0 |
| Optimized controller (`after-v4`) | **211/211 (100%)** | 70 | 18,004 | 185 | 1,903 | 0 |

Against the unchanged controller, the final controller:

- raises observed success by **16.6 percentage points**;
- reduces aggregate game ticks by **47.6%**;
- reduces full-stop runs by **89.3%**;
- reduces input changes by **68.0%**;
- recovers all nine scenarios that previously failed every repetition;
- is faster by median ticks in 36 of the 40 scenarios that already passed in
  both cohorts. Four small tasks are slower: 0.2/0.5-block precision and the two
  Level-1 rise equivalents.

All final Blockwire errors are at most **0.290098 m**, inside the unchanged
0.3000 m rule. All 211 final runs settle, lose no health and retain zero dropped
trace samples.

### Category completion

| Category | Before | After |
|---|---:|---:|
| Building/roof | 8/13 | **13/13** |
| Combined | 14/29 | **29/29** |
| Curves | 8/11 | **11/11** |
| Linear | 60/60 | **60/60** |
| Modes | 30/30 | **30/30** |
| Parkour fixture | 3/15 | **15/15** |
| Precision | 20/20 | **20/20** |
| Turns | 15/15 | **15/15** |
| Vertical | 18/18 | **18/18** |

The nine fully recovered scenarios are the three mixed/negative diagonals,
S-curve, single gap, two gaps, diagonal gap, Level-4 platforms and roof-overhang
recovery.

### Representative medians

| Scenario | Native | Before | After |
|---|---:|---:|---:|
| 2-block axial route | 20 ticks | 42 ticks | **27 ticks** |
| 30-block negative-X route | 150 ticks | 230 ticks | **155 ticks** |
| 90° left turn | 55 ticks | 248 ticks | **59 ticks** |
| S-curve | 109 ticks, 3/3 | 389 ticks, 0/3 | **110 ticks, 3/3** |
| Single gap | 35 ticks, 3/3 | 7 ticks, 0/3 (no progress) | **40 ticks, 3/3** |
| Roof overhang | 88 ticks, 5/5 | 7 ticks, 0/5 | **99 ticks, 5/5** |
| Level-4 platforms | 128 ticks, 3/3 | 99 ticks, 0/3 | **307 ticks, 3/3** |
| Step-X descent | 29 ticks | 132 ticks | **50 ticks** |

The failed controller can appear “fast” where it stops immediately or times out
short of the target; those values are never treated as performance wins.

## What changed

The architecture remains one execution stack:

`goal -> Python route/motor -> actor-fenced native inputs -> Minecraft physics`

The optimization is generic rather than house- or scenario-specific:

- `MotionTrace` records position, velocity, collisions, grounded state,
  sprint/sneak, health, fall distance, actual inputs and actor/tick identity at
  the end of each client tick.
- The native local mesh emits conservative typed `flat`, `diagonal`, `step` and
  proven `gap_jump` transitions. Same-height diagonals require both corner cells;
  steps use a bounded clearance envelope; gaps require absent middle geometry,
  run-up evidence and broad landing support.
- Routing now prices edges by geometric distance, preserving native discovery
  order for equal-cost routes. This removes equal-edge-count diagonal weaving on
  long axial goals.
- Steering quantizes desired world motion into ordinary W/A/S/D while the view
  turns, holds short native leases across safe feedback cycles and brakes from
  observed horizontal speed.
- One-block steps and proven gaps have separate actor-fenced loops with deadline,
  cancellation, health, progress, vertical and lateral envelopes. A safe observed
  adjacent broad landing may replan; an unknown or missed landing fails closed.
- Every arrival radius waits for `horizontal_speed <= 0.004` and a second native
  position sample stable within 0.005 m. Releasing a key lease is never accepted
  as a gameplay outcome.

BCL syntax and command semantics did not change. Native Minecraft still owns all
movement, collision, fall and damage outcomes.

## Retained progression

The qualification history is preserved rather than overwritten:

- `after-v1`: 208/211; all three `step_x_descend` repetitions settled 0.001635 m
  outside the 0.3 m rule despite skill-level `arrived`.
- `after-v2`: 210/211; one Level-4 platform repetition missed.
- targeted Level-4 follow-up: 3/3.
- `after-v3`: 211/211.
- `after-v4`: 211/211 on the final source, including geometric route costs.

Smoke and debug runs remain separate from qualification.

## Post-rotation unchanged-cohort regression

After replacing Python's fixed 8° camera stepping with the native elapsed-time
controller, the identical fixture/scenario cohort was rerun against the final
integration source as `after-rotation-v4`: **211/211**, 17,908 total ticks,
median 70, 227 full-stop runs, 1,756 input changes, maximum horizontal error
0.290098 m, zero health loss, all runs settled and zero dropped samples. Relative
to historical `after-v4`, aggregate ticks improved 0.5% and input changes improved
7.7%; stops increased because uncertain/narrow lateral support now deliberately
stops and replans before turning. This is a separate regression gate; it does not
rewrite the original native/before/after comparison. See
[rotation-benchmark.md](rotation-benchmark.md).

## Decisions

- **Native reference: GO** — 211/211 at its declared 1.0-block radius.
- **Unchanged controller: NO-GO** — 176/211.
- **Optimized controller: GO** — 211/211 at 0.3 blocks, all final safety,
  mutation, regression and closure gates pass.
- **Strict native performance parity: NO-GO** — the final controller uses 20.5%
  more aggregate ticks than the reference. The largest remaining gap is the
  Level-4 platform route (307 versus 128 median ticks). Native parity is not a
  prerequisite for optimized-controller GO.

This movement GO does **not** retroactively alter construction evidence. Historical
Superflat Test A remains GO and Test B remains NO-GO. A fresh final-source
regression, `A15`, independently passed 71/71 required blocks with 288 executed
operations, 82 verified placement events, zero failed actions and all access,
cleanup and safe-player predicates true in 581.92 seconds.

## Verification and evidence

Historical movement-final local gates:

- 440 Python tests: PASS;
- Gradle contracts/check: PASS, including 18 terrain and 12 motion-trace checks;
- 148 skill, 37 native, 20 controller and 22 building mutations: **227/227
  killed**;
- real Netty/Python TLS interoperability: 10/10 PASS;
- final test client: title screen, world saved and closed.

Machine-readable historical evidence is
[`docs/evidence/movement-benchmark.json`](evidence/movement-benchmark.json).
Post-rotation source hashes, final QA and the separate Rotation/Movement/Building
decisions are in
[`docs/evidence/rotation-benchmark.json`](evidence/rotation-benchmark.json).
Raw CSV/JSON traces, summaries, preserved pre-optimization source, snapshot
manifests and logs remain under the ignored local
`build/movement-benchmark/` tree. The public evidence records hashes and aggregate
set digests; snapshots, credentials and ended worlds are not distributable.

## Limits

This qualifies one deterministic Minecraft 26.3 fixture, not general navigation.
Slabs, fluids, caves, unknown-height long routes and arbitrary non-full-block
terrain remain unsupported. Known-hazard avoidance is best effort, not immunity;
hostile, food-constrained or unattended Survival movement is not qualified. No
release, upload or deployment is authorized by these results.
