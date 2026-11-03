# Stateful input execution: experiments and grounding follow-up

## Latest follow-up: local grounding cause confirmed, full qualification NO-GO

The native component A/B test confirmed a real edge fall: a one-tick direction
lease also released Sneak while native residual velocity remained. The corrected
motor prepares crouch and gives it an independent bounded lease at an already
validated local edge pose. Direction remains one native tick; ordinary skill
cleanup still releases everything. The original motor lost ground in all four
retained focused trials, while the corrected motor completed all four. These span
visible and hidden-display diagnostics, not a frozen full-replay cohort.

Camera, Sneak and placement-adapter reuse now have independent, default-off
trusted-host controls. Reuse is limited to one active `SkillContext`: inventory and
actor observations stay fresh, context closure invalidates cached intent/adapters,
and no native key is transferred between independent BCL operations. Ordinary
non-sneak actions release retained crouch. A known full-cube crafting table can be
used as a placement support with required crouch; chests and unknown shapes remain
unsupported.

On the hidden display, all five final horizontal-wall ablations placed 5/5 blocks.
The combined trial took 5.066 seconds versus 5.820 seconds for its own baseline,
with one Sneak activation/release instead of five, 12 look requests instead of 20,
and five individually verified uses. This is a **12.95% isolated-scenario result**,
not a full-replay speedup or a repeatability claim. Vertical placement, mixed
movement/placement, interactive support, cancellation and actor invalidation also
passed scoped native checks. The dedicated native edge walk stayed grounded and
used no jump.

Full replay remains **NO-GO**. `GP-90` stopped in batch 13 at 41 blocks with
`recorded_partial_pose_not_safely_reached`. Fresh all-options-off and reuse-enabled
controls subsequently stopped at the same earlier placement boundary; the new
identity pilot stopped there too. The current coarse M0 arrival is not admissible
for that placement, while the recorded target fails the existing robust support
contact bound. Those bounds were not weakened, and no alternative recorded path
was generated. The final nine-case and identity-repeatability cohorts were **not
started** after these functional failures. Standard BCL optimization remains off.

See the [new grounding evidence](evidence/stateful-input-grounding.json) and
[its separate hash manifest](evidence/stateful-input-grounding-hashes.json).
The earlier C01 material below remains a point-in-time record, not the current
implementation description.

## Historical C01 status

**Overall: NO-GO. The requested stateful-input optimization is not complete.**
The performance candidate is **not enabled by `BCLRunner`**. Ordinary execution
still releases inputs at each controlling skill boundary. No native input lease,
placement, movement, camera interpolation, BCL/1 contract or coordinate transform
was changed in the final working implementation.

The experiment implemented trusted-host, explicitly opt-in reuse of a verified
post-action observation for the next deterministic dispatch. It did not reuse that
snapshot to authorize an action: a fresh complete observation still preceded every
native skill, and a fresh verification followed it. This reduced redundant runtime
work, but transformed replays exposed regressions. Faster identity execution alone
is insufficient grounds for default enablement.

Machine-readable results and hashes:

- [Performance evidence](evidence/stateful-input-performance.json)
- [Performance evidence hashes](evidence/stateful-input-performance-hashes.json)

## Baseline and actual bottlenecks

An instrumented, source-frozen baseline ran the unchanged H04/v16 BCL on a fresh
canonical fixture. It completed 20/20 batches, 572 runtime operations and all 71
placement postconditions, followed by native inspection and closed-client save
verification. Runtime was **464.227 seconds**. Both reference and candidate used
the same read-only diagnostic hooks; the historical R33 time of 457.254 seconds is
context, not an interchangeable uninstrumented comparison arm.

The baseline recorded:

- 429 `walk_to` operations, of which **331 required zero movement steps**;
- 6,280 `observe`, 3,376 `navigation`, 2,772 `inventory` and 1,774 `menu` RPCs;
- 778 `stop`, 531 `look`, 512 `drive` and exactly 71 native `use` RPCs;
- approximately 183.814 seconds inside walking skills and 58.376 seconds inside
  placement skills, including their nested RPCs and waits;
- approximately 251.646 seconds in native RPC calls and 187.557 seconds in
  cooperative skill waits.

These are nested measurements, not additive categories. An RPC wall-clock duration
is not a native simulation-tick count. The evidence reports collected native trace
windows and their input transitions separately, with explicit interval-alignment
limitations. Exact per-placement simulation ticks and same-position inter-placement
latency remain unqualified.

The observed overhead is therefore not attributable solely to Sneak toggling.
Native `InputState.set` already avoids changing a key mapping whose state matches
its requested value, and native leases support renewal without a release. The
Python runtime nevertheless performs many full observation cycles and explicit
per-skill stops. Removing those stops without an authorized lifecycle design would
change ownership, not merely eliminate a redundant RPC.

## Candidate C01

The candidate reused only the previous successful action's verified observation
for the following deterministic dispatch. It retained:

- fresh actor/player/resource observations immediately before every skill;
- post-action observations and individual placement outcomes;
- durable pending intent and request deduplication;
- cancellation/deadline checks and final cleanup;
- the existing ordered BCL program and persistent S1 home;
- per-skill release, native short leases and F8 behavior.

It introduced no cached input authorization, new controller, alternative path,
placement retry, success tolerance change or automatic crouching policy.

The source was frozen **before** all native candidate runs:

`a913f5f73324b1510c0b1807785f2ccaea29d7bbc32aedf51869b5e1950546b9`

### Unchanged-source native results

| Run | Scenario | Result | Complete batches | Correct blocks | Seconds |
|---|---|---|---:|---:|---:|
| PERF-01 | Identity | GO | 20/20 | 71/71 | 412.279 |
| PERF-02 | Identity | GO | 20/20 | 71/71 | 411.481 |
| PERF-03 | Identity | GO | 20/20 | 71/71 | 413.064 |
| PERF-04 | Identity | GO | 20/20 | 71/71 | 411.595 |
| PERF-90 | 90 degrees | **NO-GO** | 4/20 | 7/71 | 70.802 |
| PERF-180 | 180 degrees | GO | 20/20 | 71/71 | 421.523 |
| PERF-270 | 270 degrees | **NO-GO** | 4/20 | 7/71 | 73.105 |
| PERF-X01 | Translation | GO | 20/20 | 71/71 | 418.312 |
| PERF-X03 | Reflection | **NO-GO** | 4/20 | 7/71 | 71.800 |

Every successful run had zero failed actions/retries, exact structure and air-volume
acceptance, a complete roof, clear entrance, accessible interior and safe player,
plus independent native and post-exit save checks. Failed runs retained their
actual worlds and verdicts. Each stopped on its first failed operation with no
rescue or action retry.

Mean identity duration was **412.105 seconds**, an **11.228% reduction** against
the instrumented baseline. The three confirmation identity runs passed 3/3; the
full candidate cohort passed only **6/9**. Neither figure can replace the other.

The three regressions each stopped in batch 4 during placement repositioning with
`not_grounded`, before the eighth placement. Native observations show loss of
grounding, not a transformation mismatch. The precise causal role of stance lease
expiry, residual motion and earlier positional differences remains **UNCONFIRMED**.
It would be incorrect to declare a confirmed Sneak fix from this evidence alone.

## Disposition and safety boundary

The candidate was removed from the BCL default path. Observation reuse remains an
explicit trusted-host `AgentRuntime` experiment, defaulting to `False`; it is not a
BCL opcode, setting, exported skill parameter or automatic replay optimization.
Ordinary BCL execution uses the previous observation/cleanup lifecycle.

A draft within-skill Sneak-lease prototype was also tested locally. It did not pass
the targeted simulated suite and was removed before native testing or qualification.
Its failing test log is retained privately. No unqualified movement change remains.

A separate default-restored source freeze then passed fresh 90-degree and identity
replays (`SAFE-90`, `SAFE-ID`), each at 20/20, 572 operations, 71/71 blocks and zero
failed actions/retries, with native and closed-save verification. These two checks
are scoped restoration evidence, not a new full rotation-repeatability cohort.

## Automated checks and retained failures

Final verification passed:

- 558 Python tests in the final serial full-suite run;
- Gradle `check`;
- 50/50 BCL mutations, 184/184 skill mutations and 47/47 Play2Code mutations;
- ten real TLS interoperability checks.

Three focused contracts cover dispatch-read reduction, actor replacement before
entering a second skill, and cancellation before another effect. A targeted mutation
removing the fresh pre-action observation is killed; input cleanup remains ordinary
shared cleanup rather than a new input-ownership layer.

Earlier failures remain visible:

- B01: world-load control timeout before BCL, no performance measurement;
- B02: diagnostic transport loss after two batches/four placement events; outcome
  remains UNKNOWN, not a successful or resumed baseline;
- B03: fresh successful reference with bounded 128-sample telemetry polling;
- C01: three native transformation regressions as listed above;
- the discarded local Sneak prototype's targeted-test failures;
- one parallel full Python suite failure in terminal reply correlation. The final
  serial full suite passed without weakening the test.

Diagnostic transport failures are terminal: the corrected profiler does not hide
them, reconnect or retry the gameplay action.

## Remaining work / independent decisions

| Gate | Decision |
|---|---|
| H04 identity performance | GO **only for experimental C01 identity** |
| H04 identity confirmation repeatability | GO, 3/3 |
| Full transformed replay regression | **NO-GO, 6/9 overall** |
| Stateful native input reuse | NOT IMPLEMENTED |
| Continuous Sneak walking qualification | NOT NEWLY QUALIFIED |
| Consecutive-placement efficiency | NOT ESTABLISHED |
| New held-input F8/cancel/actor/session scenarios | NOT RUN |
| Default enablement / release | **NO-GO** |
| H05 / human generalization | PENDING |

The isolated vertical/horizontal wall, interactive-support, mixed-sequence and
held-input lifecycle scenarios A-G have not been completed. In particular,
interactive support placement is not made supported by this experiment. Camera
interpolation and placement support contracts remain unchanged. No human-speed
parity or general reliability claim is made.

Further work must first isolate the grounding regression, establish a causal test,
and define safe within-context stance retention. Preserving keys across independent
skill/task boundaries is not permitted merely to improve throughput. Any corrected
implementation needs another prospective source freeze and independent native
requalification; C01 cannot be relabelled.

Raw recordings, traces, actor identities, journals, credentials and saves remain
private under ignored `build/stateful-input-performance/`. No commit, push, tag,
upload, release or deployment was performed. Isolated clients were closed and
control endpoints disabled after the native runs.
