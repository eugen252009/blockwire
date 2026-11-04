# Stateful qualification: resumed native work

## Decision

**Recovered standard path remains GO. Optimized default activation remains NO-GO/off.**
Production Python and Java sources are unchanged from recovery commit `1d5fcbe`.
No commit, push, release or deployment was performed in this continuation.
The earlier [blocked checkpoint](stateful-requalification.md), failures and hash
maps remain historical evidence. New results are in the separate
[resume evidence](evidence/stateful-requalification-resume.json) and
[hash manifest](evidence/stateful-requalification-resume-hashes.json).

## Environment and REPL correction

The conflicting user launcher/game had exited before continuation. No unrelated
process was terminated. Every new launch passed the foreign-launcher preflight;
34 actual child-process proofs establish UID, exact instance cwd, Java entrypoint
and `DISPLAY=:99` **before native connection/measurement**. Requested launcher
environment alone was not accepted. Existing authenticated hidden-display,
canonical-fixture and native-instance workflows were reused.

The original REPL correlation test passed alone but again failed in the full
602-test suite. It expected four answers after `:quit`, although `:quit` deliberately
cancels immediately. A fixed 30 ms input delay was not a response barrier. The
correlation test now ends at EOF, which drains submitted requests, with all four
ID/modal/invalid-source assertions unchanged and no scheduling sleep. A separate
event-synchronized test proves immediate quit cancels an in-flight request, does
not wait indefinitely, produces no fabricated completion and never resubmits.
No CLI, protocol, runtime, assertion tolerance or timeout was relaxed.

## New native micro and safety cohorts

M03: **13/13 GO**, including three counterbalanced horizontal trials per mode,
vertical/mixed/crafting-table interaction, cancellation and actor replacement.
Only camera+Sneak reuse was proposed; placement reuse remained false.

| Horizontal mode | Trials | Mean seconds |
| --- | ---: | ---: |
| Baseline | 3 | 5.816631 |
| Camera+Sneak | 3 | 5.304222 |

The observed isolated reduction is **8.809%**, not a full-program speedup. Earlier
M01's 12.185% result enabled all three options and is not pooled with M03.
Actor loading is explicitly separate from authorized/post-ready control: loading
must have no remote input or position change; authorized/post-ready observations
must remain grounded. M01's earlier actor diagnostic NO-GO is not rewritten.
E03's sealed native Sneak-edge walks passed **4/4**, with no loss of grounding,
no Jump and unchanged geometry. Each positive placement retained exact block,
item-consumption and single-use postconditions. No cross-task input transfer.

## Full unchanged H04 execution and actual timings

A02: **6/6 complete GO**, each 20/20 batches, 572 runtime operations, 71/71 blocks,
zero failed actions/retries, independent native and closed-save verification.

| Arm | Seconds | Observed reduction against control mean |
| --- | ---: | ---: |
| Baseline 1 | 506.155 | — |
| Baseline 2 | 525.860 | — |
| Baseline 3 | 527.031 | — |
| Camera only | 495.086 | 4.733% |
| Sneak only | 523.138 | -0.665% |
| Camera+Sneak | 513.510 | 1.188% |

Control mean: **519.682 s**. The pair lies inside the control range and each
optimized arm has only one A02 observation. **Stable full-program performance
benefit is not established.** Camera-only's single observation is not repeatability
qualification. The prior 498.939 s standard GO remains intact but was not silently
used as a matched control across host-time cohorts; historical visible/GPU results
are not comparison arms. RPC/skill categories in the original baseline profile
remain nested/nonadditive; no timing extrapolation is used.

## Repeatability and transformation results — separate gates

S02 uses one frozen source/configuration and independently restored worlds:

| Identity | Seconds | Verdict |
| --- | ---: | --- |
| ST-ID01 | 521.596 | GO |
| ST-ID02 | 510.737 | GO |
| ST-ID03 | 513.303 | GO |
| ST-ID04 | 516.188 | GO |

All four have complete native/closed-save acceptance and zero retries. This is
**4/4 identity repeatability**, not a completed nine-case cohort. S02 then stopped
at `ST-90`: setup never observed the expected TitleScreen, before world load or
BCL replay. Its exact unexpected screen/cause was not captured; no network or
Blockwire defect is asserted. The ID was not relaunched and the failed preparation
remains. A fresh independent S03 spatial catalog added read-only menu diagnostics,
without changing load behavior, timeouts, gameplay or source BCL.

| S03 case | Seconds | Verdict |
| --- | ---: | --- |
| SU-ID | 575.951 | GO |
| SU-90 | 511.578 | GO |
| SU-180 | 569.708 | GO |
| SU-270 | 563.772 | GO |
| SU-X01 translation | 546.662 | GO |
| SU-X03 reflection | 212.299 before termination | UNKNOWN_NO_RETRY |

The five GO cases independently meet all 71-block, native/closed-save and
zero-failure/retry criteria. Reflection lost the BCL connection after seven batches,
210 operations and 24 verified placement events. No final native/closed-save
acceptance exists. Its initiating host/display shutdown cause is **not established**;
no automatic reconnect/replay or new native attempt followed. Original journals,
result and the interrupted closed world were preserved without claiming completion.
The legacy harness subsequently attempted to verify an absent `ended-world` and
raised a secondary exception; that traceback is retained, not treated as a new
execution or a gameplay failure count.

**No optimized 9/9 PASS.** S02/S03 are not pooled with one another or historical
cohorts into a synthetic complete qualification. This and inconclusive performance
independently prevent activation.

## Final automated QA and safe end state

- Python: **603/603 PASS**, three final serial full-suite runs.
- Focused TLS-WebSocket/terminal contracts: **35/35 PASS**.
- Gradle check: PASS.
- Mutations: **209/209 skill, 50/50 BCL, 47/47 Play2Code** killed.
- TLS interop: **10/10 PASS**.
- Existing handoff/grounding/input-lease/gateway tests remain included. Historical
  unchanged-source HM04 movement **211/211** is retained, not relabelled as a new
  optimized movement acceptance. The new native edge/lifecycle gates are above.
- Physical F8 injection: **NOT RUN**; contracts/implementation unchanged.

The first offline-QA preflight wrongly required a running display after shutdown;
two subsequent read-only preflights encountered unrelated protected `/proc` cwd
entries. Those script errors/logs remain. The final preflight checks only actual
same-UID Java candidates and closed test ports; QA then completed fully. No user
process was signalled to make it pass.

Owned Minecraft/gateway processes are closed, ports 8765/8879 closed, instance
control disabled and hidden display stopped. Camera, Sneak, placement and dispatch
observation reuse defaults remain false. TLS, actor/session fences, ownership,
leases, cancel/F8, budgets, tolerances, native physics and cleanup are unchanged.
H05 still requires owner construction; arbitrary terrain/shapes/modpacks/angles
remain unqualified. Further reflected native testing needs a new authorized
independent fixture/cohort, never replay of the uncertain session.
