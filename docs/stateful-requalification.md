# Stateful execution requalification after replay recovery

## Resumed continuation

The [native continuation](stateful-requalification-resume.md) resolves the original
Prism blocker and REPL test race, completes new micro/full/identity tests and final
603-test QA. It retains a premeasurement setup failure and a terminal reflected
transport UNKNOWN; no optimized 9/9 or stable full-program speedup is claimed.
Defaults remain off. The checkpoint/results below and their hashes are historical,
not rewritten by that continuation; see the separate resume evidence/hash map.

## Disposition (original stopped checkpoint)

**Recovery baseline remains GO. Optimization activation remains NO-GO / off.**
The recovery work was explicitly authorized for a local commit and recorded as
`1d5fcbeeca847a86b1716dbf6968762d6fce3ec1`. No push occurred. Subsequent performance
work is uncommitted. Production Python/native execution is unchanged from that
checkpoint; existing independent trusted-host options were measured, not enabled
in the default BCL path.

The recovered [pose-handoff qualification](pose-handoff.md) already completed its
final QA: 597 Python tests, Gradle, 209/50/47 mutations, TLS 10/10, S05 9/9 with
four independent identities, and native movement 211/211. Its 171-file public and
21,182-artifact private manifests were reverified before the commit. Those results
were reused as verified evidence, not rerun or relabelled as optimization success.

See [new evidence](evidence/stateful-requalification.json) and the separate
[current-state hashes](evidence/stateful-requalification-hashes.json).

## Reconstructable local source checkpoint

Local identity:

`9c09fdd0060c5fc3c257f740010e995de85bbc6154c3a1e5650c0fb9f6c9fd9c`

The ignored checkpoint contains a Git archive and verified extracted source for
all 343 tracked files, four additional frozen qualification harnesses, shared
harness hashes, the native JAR identity, original program/export hashes, canonical
fixture manifest/reference and prior evidence identities. It records Git HEAD and
tree and can be reconstructed independently of later source edits. Private owned
world data stays at its separately verified immutable reference; it is not in the
source archive or public evidence. Credentials, certificates and account databases
are not included. QROT02 and earlier source freezes remain untouched.

The final recovered S05 freeze remains
`806f257acef613a505a828c649ef2fbfac10eb4bb085ba9123a8674040852404`.

## Fresh full standard baseline

A new B01 run (`SQ-BASE-01`) used the recovered source, unchanged H04/v16 BCL,
canonical restore and read-only profiling, with every reuse flag and dispatch
observation reuse explicitly off. It independently passed 20/20 batches, 572
runtime operations, 71/71 placements/blocks and native plus closed-save checks,
with no failed action or retry: **498.938963 seconds**.

Observed overhead:

| Measurement | Result |
| --- | ---: |
| `walk_to` / zero new BCL movement instructions | 429 operations |
| Walking skill wall time | 202.420 s |
| Placement skill wall time | 68.790 s |
| Explicit aiming skill wall time | 22.063 s |
| Native RPC wall time | 270.018 s |
| Cooperative waits | 200.168 s |
| Observe / navigation RPCs | 6,514 / 3,534 |
| Inventory / menu RPCs | 2,839 / 1,774 |
| Stop / look / drive RPCs | 746 / 600 / 1,121 |
| Native use submissions | 71 |
| Observed native ticks / tick span | 9,996 / 9,996 (no gaps) |
| Nominal observed simulation time at 20 TPS | 499.8 s |
| Native Sneak transitions | 374 |
| Native Jump transitions | 6 |
| I3 operations with directional positioning | 7 |

These are nested, overlapping categories, not an additive latency breakdown.
Trace boundaries include sampling margin; nominal tick time is not a substitute
for wall-clock time. Jump transitions belong to the unchanged recorded program;
no extra jump strategy was added. Directional positioning counts are observed
I3 preparation, not automatically repeated BCL actions. Native yaw/pitch/key traces
and exact input ownership remain private. The old 464.23/412.10-second cohorts are
historical context, not current comparison arms.

## Controlled native microbenchmarks

M01 prospectively froze all five configurations over the same sealed mechanics
fixture: baseline, camera-only, Sneak-only, placement-only, and all three combined.
Horizontal trials were counterbalanced and repeated three times per mode. Vertical
three-block, interactive crafting-table support and mixed Move/Place/Place/Move/
Place/Place/Place scenarios each tested all five configurations. Cancellation was
measured for baseline and combined. Every positive placement retained its own
native block/item postcondition and one use submission. These are explicit generic
mechanics fixtures, not a replacement human recording or a building generator.

| Horizontal mode | Trials | Mean seconds | Change versus this baseline |
| --- | ---: | ---: | ---: |
| Baseline | 3 | 5.809100 | — |
| Camera | 3 | 5.447193 | 6.230% less wall time |
| Sneak | 3 | 5.532199 | 4.767% less wall time |
| Placement adapter | 3 | 5.776098 | 0.568% less wall time, inconclusive |
| Combined | 3 | 5.101259 | 12.185% less wall time |

Placement-only trial ranges overlap the baseline. It is not independently
qualified as a reliable performance improvement and remains excluded from the
proposed camera+Sneak pair. A fast combined microbenchmark does not qualify full
BCL performance, transformations, cross-task ownership reuse or default activation.

M01 retained **32 GO results and one NO-GO**, then stopped. The NO-GO was the
baseline actor-replacement diagnostic: native actor fencing and input cleanup
passed, but an overbroad diagnostic predicate required every frame after an
explicit world reload to be grounded. Eleven loading frames were not yet marked
grounded; coordinates remained unchanged, no remote inputs were held, final
health was 20 and the actor ended grounded. The failed verdict was not rewritten.

A new M02 freeze separated authorized control/post-ready safety from the explicit
loading interval, retaining both raw trace phases. It additionally required no
remote input or position change during loading. M02 planned a camera+Sneak pair
with placement reuse off. Its first baseline and pair trials passed (5.917126 and
5.073322 seconds); this is **one trial per mode, not a repeatability result**.

## Display-isolation blocker and safety response

The next M02 attempt could not complete safe cleanup through the hidden-display
window fence. Investigation found an unrelated Prism session on the visible
`:0` display sharing the launcher's singleton IPC home. It had forwarded our
dedicated test-instance launch to that visible session despite the launch command
selecting `:99`. Checking the launcher's requested environment is therefore not
sufficient proof of the actual child's display.

That attempt is **invalid for performance qualification**. Its partial native
exchanges, trace and closed snapshot are retained; it has no accepted GO result.
No visible-display fallback is permitted, and no new full optimization replay was
started. No frozen script or earlier result was edited to hide the failure.

Only the dedicated test JVM was terminated, after same-user, exact instance cwd
and Java entry-point checks. Its endpoint was disabled and port 8765 closed. The
unrelated user's launcher and Minecraft instance were not signalled or modified.
The owned hidden display was stopped. This is not a claim that all Minecraft
processes on the host were closed.

A benchmark-only read-only guard now checks actual process UID, start identity,
exact instance cwd, Java entry point and actual `DISPLAY`, not merely requested
launch settings. It also detects a foreign-display Prism/prismrun process in the
shared IPC home before launch, without terminating it or reading/exporting other
environment secrets. Five deterministic guard tests pass; a read-only preflight
confirmed rejection of the actual foreign launcher with zero launches/signals.
This does not itself constitute a new graphical qualification. Any resumed
harness must install these guards and use fresh source/attempt IDs before effects.

## Independent decisions and remaining gates

| Gate | Decision |
| --- | --- |
| Recovered baseline and M0/I3 contract | GO, preserved |
| Local reconstructable source checkpoint | GO |
| Fresh standard H04 baseline performance | GO, 498.939 s |
| Camera/Sneak microbenchmark benefit | Observed within scoped fixtures only |
| Placement reuse benefit | NOT ESTABLISHED; excluded |
| Combined/pair full H04 speedup | NOT RUN; micro/lifecycle/display gate incomplete |
| Optimized nine-case transformations | NOT RUN |
| Optimized unchanged-source repeatability | NOT RUN |
| Full optimized safety qualification | NOT ESTABLISHED |
| Default activation | NO-GO / unchanged off |

No movement/placement tolerance, native physics, BCL byte/order, transformation,
S1, actor fence, input-lease owner, camera interpolation or postcondition was
changed. No new cross-task key transfer or automatic action retry was introduced.
Physical F8 injection was not performed. Existing native implementations and
contracts remain unchanged.

Continuation requires an independently isolated launcher/IPC setup, or explicit
operator coordination that the shared foreign launcher is closed. Do not close
someone else's session, copy their account database or use the visible display to
finish the cohort. Preserve M01/M02 and all IDs; qualify fresh actor/edge/lifecycle
gates, the camera+Sneak pair, full independently verified replays, nine spatial
cases and repeatability before considering activation. Offline checks and hash integrity remain separate from those outstanding native
gates. The current 602-test suite retained one failure in each of three serial
runs: the existing terminal REPL correlation test returned responses 1/2/3 before
quit instead of expected 1/2/3/4. The same test passed in isolation. No CLI,
transport, assertion or timing fixture was changed to manufacture green QA.
The five new display-guard tests pass. Gradle, 209 skill / 50 BCL / 47 Play2Code
mutations and TLS 10/10 pass. Current full-suite QA is therefore **NOT GREEN**;
this is separate from the previously frozen recovery QA and another outstanding
gate before optimization activation.
