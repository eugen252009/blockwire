# Parallel autonomous Survival: resource-gated 16-client attempt

## Latest: four real concurrent campaigns (separate parallel-002 cohort)

The [four-agent campaign report](autonomous-survival-parallel-campaigns.md) now
records actual concurrent LLM gameplay: 690.885 seconds of four-agent overlap,
77 model decisions, 510 submitted BCL operations, four independent worlds/memories
and recordings. Infrastructure/concurrency/resource gates passed; useful Survival
development did not (five leaves mined, no pickups/tools/home). Three original
replays were briefly played; the fourth viewer-only launch was blocked by Flatpak.
The [new evidence](evidence/autonomous-survival-parallel-campaigns.json) is additive:
the failed 16-client cohort below, its JSON and historical hashes remain intact.

## Follow-up: corrected live profile and 6+1+1 affinity

The [separate CPU-allocation follow-up](autonomous-survival-cpu-allocation.md)
verifies live Custom/8/5 settings and six physical Minecraft cores plus one local
inference core and an unused-by-benchmark OS pair. It measures a five-instance
qualified boundary; six misses the prospective CPU headroom rule, and eight/16
remain unqualified. It does not rewrite the different configuration, outcomes or
hashes of the historical attempt below.

## Decision — target not achieved

**16-instance concurrent autonomous gameplay: NO-GO / BLOCKED by the measured
resource/configuration preflight.** A final settings audit also found that the
requested lower-distance profile was not verified. This is not a successful
16-agent campaign, not eight
LLM-controlled players, and not a sequential substitute.

- **16** isolated instance/world/context configurations prepared.
- **8** real native worlds simultaneously active at peak.
- **4** is the largest stage that passed the observed **short resource-readiness**
  gates; this does not qualify the intended 8/5 render/simulation profile.
- **0** autonomous campaigns, gameplay model decisions or BCL campaign operations.
- All 16 autonomous outcomes remain **NOT RUN**, not failed or successful Survival.

[Evidence](evidence/autonomous-survival-parallel.json) and
[point-in-time hashes](evidence/autonomous-survival-parallel-hashes.json) preserve
all stages, failures and artifacts. The earlier
[single-agent campaign](autonomous-survival-campaign.md), its world, memory and
historical hashes were not changed or reused as this cohort's progress.

| Qualification | Verdict |
| --- | --- |
| 16 concurrent autonomous players | **NO-GO:** 8-client preflight failed; 16 not launched |
| Native readiness concurrency | **2/4 PASS, 8 FAIL**, not long-term gameplay qualification |
| Actual simultaneous loaded worlds | **8**, verified by overlapping native traces |
| Agent isolation | Scoped directory/endpoint/certificate/actor separation; **not 16 BCL/context qualification** |
| Autonomous progress / strategy comparison | **NOT RUN** for all 16 |
| Replay capture | 10 readiness-only artifacts from 8 clients; CRC/framing PASS |
| Native replay playback | One readiness artifact opened/played; other nine NOT RUN |
| Resource stability | CPU/RPC boundary reached at 8; safe global stop completed |
| Long-term autonomy / live failure isolation | **NOT QUALIFIED** |

## Hardware and prospective safety limits

Host: **Ryzen 7 5800X, 8 physical cores / 16 threads**, approximately **62.18 GiB
usable physical RAM**, initially about 93.5 GB free disk, RTX 3060 **12 GiB** and
RTX 2080 SUPER **8 GiB**. No local LLM model was loaded; the selected authenticated
model backend is remote. Its server RAM/VRAM is **not observable** here.

The established authenticated hidden **Xephyr `:99`** workflow renders Minecraft
through **CPU llvmpipe**. All eight inspected client logs confirm that renderer.
The NVIDIA cards' available VRAM did **not** mean these clients were GPU-accelerated.
No visible `:0` fallback, host display change or unrelated process termination was
used to manufacture capacity.

All candidate instances were configured for Minecraft 26.3, the same existing
Blockwire/Fabric/API and ReplayMod 26.3-2.6.28, **2 GiB maximum Java heap**, 640×360
window, requested 30 FPS, render distance **8**, simulation distance **5**, and
`pauseOnLostFocus=false`. `LP_NUM_THREADS=2` was requested, not presented as proof
of an exact renderer-thread count. Actual native heap arguments were inspected.
Stateful reuse stayed off.

**Final configuration audit: additional NO-GO.** All eight launched clients saved
render/simulation distances **16/12**, while the eight never launched still contain
requested **8/5**. The inherited graphics preset is `fancy`; preset application is
a plausible mechanism, not independently proven by a corrected-run A/B. The
persisted values were inspected after the run, not live render-distance telemetry.
Consequently the effective requested low-cost profile was **not established**.
The numbers below remain actual observations, but **must not be described as an
8/5 configuration qualification or a lower-distance hardware ceiling**. Raw
measurements, intended policy and original stage verdicts were retained, not edited
to hide the mismatch. No late settings change or undocumented rerun followed.

Pass rules were recorded before measurement:

- Native client ticks and observed game-time progression each at least **18/s**.
- Native observation RPC p95 at most **150 ms**.
- Mean host CPU at most **85%**, at least **8 GiB MemAvailable** and **20 GiB disk**.
- No swap growth, actor replacement, damage, loss of grounding or native inputs.
- Separate actual child UID/cwd/Java-entrypoint/hidden-display proof before connecting.
- Planned 60-second measurement after warmup. A stricter watchdog was prospectively
  added/frozen before the 8-client stage: abort above **95% mean CPU across ten
  successive host intervals**. Memory/swap/storage watchdogs could also abort.

Global orchestration limit: **5,400 seconds**. Preparation through final native
cleanup/playback took about **2,737 seconds**; this is not gameplay duration.
Planned per-agent campaign limits remained 30 decisions, 300 operations, 30 minutes
and eight failures. None of those autonomous activations began.

## Actual concurrent ramp

| Active worlds | Measurement | Mean / peak host CPU | Java RSS sum peak | Min available RAM | Native RPC p95 range | Verdict |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 2 | ~60 s | 28.46 / 30.93% | 8.06 GiB | 49.97 GiB | 109–114 ms | PASS |
| 4 | ~61 s | 58.99 / 65.38% | 16.21 GiB | 41.97 GiB | 126–147 ms | PASS |
| 8 | ~12.8 s, watchdog abort | 96.10 / 97.12% | 32.55 GiB | 25.71 GiB | 229–347 ms | **FAIL** |
| 16 | Not started after failed gate | — | — | — | — | **BLOCKED** |

At eight, **every** client's RPC latency failed the 150 ms rule. Client ticks and
client-observed world-time progression remained approximately 20/s; that alone did
not establish responsive or safe execution. The CPU watchdog stopped the readiness
measurement rather than allowing uncontrolled overload to continue. No native
inputs were held and no gameplay mutation was attempted. Every sampled actor stayed
alive, grounded and at full health; zero trace samples were dropped.

Public p95 values use nearest-rank `ceil(.95*n)`. The original short-window guard
recorded a lower-order statistic; raw values and original NO-GO verdicts remain.
All eight fail either calculation, so the independent quantile calculation does
not rehabilitate or alter a result.

The overlap is real, not a count of sequentially connected clients: each worker
used a separate live TLS connection, independent actor and concurrent measurement
barrier, with overlapping native tick/monotonic/game-time traces. This establishes
**eight simultaneously active readiness worlds**, not eight autonomous planners.
Four passed one short resource-readiness window; the final configuration mismatch
prevents qualification of the intended graphics profile. This is **not** a qualified
30-minute four-agent campaign or a permanent hardware maximum.

RSS sums can count shared/JVM mappings more than once. MemAvailable is reported
separately; there was no swap growth. Resource peaks cover sampled windows, not
every startup instant. Native bridge CPU shares its Minecraft JVM and was not
independently attributed. Client ticks are not rendered FPS; exact render FPS and
server MSPT were not instrumented. GPU samples stayed near baseline (3060 roughly
12 MiB; 2080 SUPER roughly 245–246 MiB, very low utilization), consistent with
llvmpipe rather than available-GPU throughput.

## Equivalent worlds and actual isolation scope

Instances are named **survival-01 … survival-16**. A new native GUI-created normal
Survival/Peaceful world, seed **74219031427**, commands/bonus chest OFF, was saved
before any gameplay progress. Closed-save verification confirmed empty inventory,
health/hunger 20/20 and no mining/crafting/item-use statistics. Its clean snapshot
was cloned into 16 separate owned world directories. All start at the same saved
**(-1.5, 93, 5.5)** pose. This is not the previous campaign's progressed world.

Each instance has its own directory, world, API key and planned agent/world/BCL
namespace. Native ports **9161–9176** and reserved gateway ports **10161–10176**
are distinct. The eight launched clients generated **eight different TLS leaf
certificates and eight different live actor sessions**. The unlaunched eight have
no falsely invented native certificates, actors or sessions.

The same licensed Minecraft profile UUID is present in the cloned single-player
saves. These are **independent native player entities/worlds/actors**, not a claim
of 16 separately licensed Microsoft accounts or unique account UUIDs. No account
database, native certificate/key, progressed world or SQLite journal was copied
from another agent. Each prepared context has its own metadata and the same
requested natural Survival objective, without a resource or building sequence.

No campaign gateway, strategic event aggregator or gameplay SQLite journal was
activated after the resource failure. Thus native endpoint separation is scoped
evidence, **not** a live qualification of 16 BCL sessions, journal recovery,
cancellation, gateway fault isolation or independent long-term memory.

## Per-agent outcomes — no best-case selection

All rows have **0 campaign model requests/tokens and 0 BCL campaign operations**.
Resource/crafting/building/navigation-success metrics for autonomous gameplay are
**NOT RUN**, not fabricated zero-performance trials. Closed readiness saves for
01–08 independently contain no mining, crafting or placement progress.

| Agent | Native readiness exposure | Last readiness result | Readiness recordings | Autonomous outcome |
| --- | --- | --- | ---: | --- |
| survival-01 | 2, 4, 8; separate one-client calibrations/playback | 8 FAIL | 3 | NOT RUN |
| survival-02 | 2, 4, 8 | 8 FAIL | 1 | NOT RUN |
| survival-03 | 4, 8 | 8 FAIL | 1 | NOT RUN |
| survival-04 | 4, 8 | 8 FAIL | 1 | NOT RUN |
| survival-05 | 8 | 8 FAIL | 1 | NOT RUN |
| survival-06 | 8 | 8 FAIL | 1 | NOT RUN |
| survival-07 | 8 | 8 FAIL | 1 | NOT RUN |
| survival-08 | 8 | 8 FAIL | 1 | NOT RUN |
| survival-09 | Prepared; not launched | NOT RUN | 0 | NOT RUN |
| survival-10 | Prepared; not launched | NOT RUN | 0 | NOT RUN |
| survival-11 | Prepared; not launched | NOT RUN | 0 | NOT RUN |
| survival-12 | Prepared; not launched | NOT RUN | 0 | NOT RUN |
| survival-13 | Prepared; not launched | NOT RUN | 0 | NOT RUN |
| survival-14 | Prepared; not launched | NOT RUN | 0 | NOT RUN |
| survival-15 | Prepared; not launched | NOT RUN | 0 | NOT RUN |
| survival-16 | Prepared; not launched | NOT RUN | 0 | NOT RUN |

Campaign totals: **0 successes, 0 failed campaigns, 0 partial-progress campaigns,
16 NOT RUN**. A failed readiness gate is not a failed LLM Survival strategy. No
comparative gameplay distribution or recurring planner mistake can be inferred.
The recurring measured bottleneck is CPU-bound native RPC latency at eight.

## Shared-model probe, not a qualified 16-agent scheduler

After native clients were closed, the existing selected **openai-codex /
gpt-6.1-sol**, medium-thinking CLI handled four tiny independent nonce/context
requests through a **bounded two-worker, fixed four-request FIFO executor**.
All four replies matched only their own nonce. The first two started immediately;
the next two waited about 4.7–4.8 seconds. Total wall time was about **10.09 s**,
roughly **23.78 tiny requests/minute**. Per-probe SDK-reported input/output/cache/
reasoning token counts are retained, not estimated billing claims. A separate
read-only memory probe measured about **128.98 MiB maximum child RSS** for the
local CLI; remote inference-server memory remains unknown.

These are **five transport/resource probe requests, zero Minecraft decisions**.
They do not establish throughput with full game context, fair 16-agent scheduling,
event-volume isolation, or combined native+inference resource stability. No
inference slot was held during BCL because no BCL campaign was allowed to start.
No shared mutable conversation state or central gameplay planner was introduced.
A production parallel campaign scheduler was not promoted past the failed gate.

## Replay capture, calibration and playback

Every launched readiness world recorded independently with ReplayMod 26.3-2.6.28.
The documented `renameDialog=false` setting allowed noninteractive finalization;
packet recording remained passive and native controls/Play2Code were unchanged.
There are **10 original-copy `.mcpr` artifacts from 8 clients**, under:

`build/autonomous-survival/parallel-001/agent-NN/replay/`

Every archive passed ZIP CRC plus complete monotonic packet-framing checks, with
its own file size, SHA-256, metadata and agent directory. Streams grew during the
recorded ramp measurements. All failed-readiness periods are retained; nothing was
trimmed into a success montage. Eight unlaunched clients have no replay claim.

One original survival-01 readiness recording, **2026_11_04_11_43_48**, was opened
and played in the actual native Replay Viewer after the ramp had stopped. The
world view, playback overlay and native Exit Replay control were observed. This
was **single-client operator QA, not a resumed campaign or concurrency stage**.
The other nine files have integrity checks but no individual native playback.
All clips are readiness-only, not recordings of autonomous mining/building.

A one-client idle calibration measured recorder ON (~13.75% host CPU) and OFF
(~13.61%). The ON stream grew; OFF had no active stream growth. Different JVM,
world-time and warmup histories make these **observational measurements**, not a
controlled causal overhead percentage or evidence that recording scales to 16.

## Diagnostics, persistence, regression and cleanup

Retained setup failures are separate from resource outcomes:

- A transient launcher/bootstrap PID ambiguity failed closed; the same created JVM
  was subsequently proven before any native connection, not relaunched as gameplay.
- A private close helper opened a second native connection too quickly and received
  exclusive-controller HTTP 409. It was corrected to use one connection through
  save/quit; TLS, API-key checks and native exclusivity were not weakened.
- A setup click was explicitly rejected during a loading overlay. Later setup
  required a fresh TitleScreen **and no overlay** before clicking.
- Launch/IPC timeout and idle-console diagnostics remain. Only an exact owned idle
  Prism console received normal WM_DELETE after proving its game stopped; owned
  launcher SIGTERM occurred only after all associated game JVMs had closed.
- GNU `time` was unavailable for the first memory probe (127, no model request).
  Fresh-parent Python `RUSAGE_CHILDREN` supplied the separate actual measurement.
- The final settings comparison failed: launched instances persisted 16/12 rather
  than requested 8/5 with the inherited `fancy` preset. The full mismatch matrix is
  preserved. No requested-profile GO was manufactured from observed resource passes.

All **16 generated worlds remain**, with independent closed-save audits/copies for
all eight tested clients. Calibration worlds were archived, not deleted or pooled
as campaign outcomes. Original single-agent world/memory/evidence are untouched.
No uncertain gameplay action was replayed; no autonomous action was submitted.

The global resource boundary justified stopping the readiness cohort: no individual
agent fault was used to kill otherwise healthy autonomous peers. All eight saves
and recordings finalized, controls remained unheld, and clients exited normally.
All owned Minecraft/model/gateway/launcher/display workers are stopped and all
reserved native/gateway ports closed; control is disabled in all 16 configs.
No unrelated process was terminated. No campaigns or pending intents exist to
resume; future gameplay needs new explicit activation and fresh actor binding.

Final regression: **603/603 Python**, Gradle check, **209/209 skill**, **50/50 BCL**,
**47/47 Play2Code** mutations and **TLS 10/10 PASS**. Production Python/Java and
qualified movement/input/TLS paths remain unchanged. A new 211-case movement run,
physical F8 injection, live per-agent gateway failure/cancel/crash/recovery and
16-agent event scheduling were **NOT RUN**, not supplied by simulated tests.
No commit/push/tag/upload/release/deploy occurred.

## Remaining blocker

The available GPUs do not accelerate this established hidden llvmpipe setup.
First resolve and verify the inherited-preset/distance mismatch in a new bounded
qualification; merely writing options was insufficient. A future explicitly
isolated GPU-backed renderer or verified lower-cost configuration may change the
limit. This result does **not** prove that the hardware could never support 16,
especially under the intended but unverified 8/5 profile. Extending the actual
failed eight-client run directly to sixteen would violate the prospective CPU/
latency gates. Do not bypass those gates, switch to a user's visible session,
weaken leases/tolerances or report sequential work as concurrent gameplay.
