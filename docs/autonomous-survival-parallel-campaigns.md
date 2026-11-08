# Four concurrent autonomous Survival campaigns — parallel-002

## Decision

**Four real concurrent LLM-controlled Minecraft campaigns: GO, scoped to this
bounded experiment.** This is not another readiness-only test and not a sequence
of single-player campaigns. **Useful Survival development was not achieved.**

| Gate | Result |
| --- | --- |
| Four-client infrastructure | **GO**: 120-second admission preflight and actual campaigns |
| Four-agent concurrency | **GO**: four independent campaigns overlap **690.885 seconds** |
| Agent isolation | **GO, scoped**: separate native actors/endpoints/worlds, gateways, SQLite journals, contexts and recordings; four live cross-actor bindings rejected |
| Autonomous execution | Real model-selected observation, exploration, navigation and attempted acquisition; **no tools/home** |
| Replay capture | **4/4 PASS**: originals copied, SHA-256, CRC and complete monotonic packet framing |
| Native Replay Viewer playback | **3/4 short beginning samples PASS; 04 NOT RUN**, separate post-campaign launcher blocker |
| Resource stability | **GO** for the observed campaigns; no resource watchdog stop or affinity escape |
| Long-term autonomy | **NOT QUALIFIED** |

[Machine-readable results](evidence/autonomous-survival-parallel-campaigns.json)
and [new evidence hashes](evidence/autonomous-survival-parallel-campaigns-hashes.json)
preserve every agent, failure and timing. The earlier
[parallel readiness attempt](autonomous-survival-parallel.md),
[6+1+1 qualification](autonomous-survival-cpu-allocation.md) and
[single-agent campaign](autonomous-survival-campaign.md) are different cohorts.
Their private worlds, original artifacts and hash maps were not replaced or pooled.
The historical generic JSON remains intact; this campaign has a new evidence name
rather than overwriting the failed 16-client attempt.

## Source and configuration

Baseline revision **a9a7405**, with the existing uncommitted CPU benchmark helpers
and a new ignored host under `build/autonomous-survival/parallel-002/`. Production
`python/src/` and Java execution were **unchanged**. The mission schema, strict
BCL allowlist and output presentation reuse Campaign 001; its gameplay loop/world
were not invoked. A source freeze was written before the new preflight/campaign.
All experimental stateful input reuse remained **OFF**.

Actual `lscpu` topology was re-derived before allocation and separately checked
against sysfs siblings: Ryzen 7 5800X, 8 physical cores, 16 logical SMT CPUs.

| Role | Physical cores | Logical CPUs |
| --- | --- | --- |
| Minecraft / Blockwire / owned rendering helpers | 1–6 | **1–6,9–14** |
| Local model dispatcher and CLI | 7 | **7,15** |
| Left unused by benchmark tasks, primarily OS/background | 0 | **0,8** |

This is owned-thread affinity, **not exclusive reservation**. OS services and
unrelated applications retain their affinities. Java startup masks were explicitly
enforced before native connection; all sampled Java/GC/Netty/render, BCL host and
owned helper/model threads remained inside their assigned pools. Authentication,
TLS hostname/per-instance trust, actor fences, ownership, F8, queues and leases
were not changed. Only the authenticated hidden **:99** display was used, with
actual child UID/start-time/cwd/entrypoint/DISPLAY proof before connection.

New instances **survival-parallel2-01 … 04** have independent clean normal-world
snapshot copies, seed **74219031427**, Minecraft **26.3**, **Survival / Peaceful**,
commands/bonus chest OFF, empty inventory and initial saved pose **(-1.5,93,5.5)**.
No prior campaign progress, tools, materials or structures were supplied. The same
licensed profile UUID is used in four independent native entities/worlds: this is
not four separately licensed Microsoft accounts.

Native Video Settings verified **Custom / render 8 / simulation 5**, 30 FPS limit,
Minimized-only idle throttling and `pauseOnLostFocus=false` for every client before
measurement. Heap maximum 2 GiB, 640×360 windows, ReplayMod **26.3-2.6.28** active
before the first gameplay action. The established renderer remained CPU
**llvmpipe**, not NVIDIA acceleration.

Native ports **13601–13604**, gateway ports **14601–14604**, native keys/certificates,
actor sessions, BCL session namespaces, gateway TLS state, `campaign.sqlite`, event
queues and recordings are separate. Four invalid bindings using the next world's
actor token were rejected before effects; four correct TLS gateway bindings and
four independent model nonce/context probes then succeeded.

## Independent decisions and fair scheduling

Every agent received the same supplied natural Survival objective, same capability
catalogue/recipe metadata and same system policy. **No wood→tools→house sequence,
route, building blueprint, Test A or Play2Code program was supplied.** The host
bounds/validates/persists requests; the LLM chooses goals, routes, resources and
responses to failure. Native runtime postconditions remain authoritative.

The existing selected **openai-codex / gpt-6.1-sol**, medium-thinking backend is
remote. A separate local FIFO dispatcher on **7,15** permits at most **two model
requests**, one outstanding request per agent, independent request IDs/tickets,
contexts, timeout/cancellation flags and private raw provider logs. CLI tools,
extensions, MCP, skills, context files and persistent PI sessions were disabled.
Only each agent's own observed world, memory and recent decisions enter its next
request. Model working memory is not an authoritative world map.

An inference slot is released as soon as its model response ends, **not while its
BCL task runs**. Native/BCL actors execute independently. This is demonstrated by
~**624 sampled seconds** with one agent's actual model inference overlapping a
*different* agent's BCL execution. Fairness/context/cancellation also passed six
private host/scheduler contracts using a fake provider, separately from real
native acceptance.

Events use the existing per-gateway subscriptions: `inventory.changed`,
`player.health`, `command.completed`, plus mandatory lifecycle events. A background
consumer drains each bounded client queue and keeps a short important-event
summary; no tick stream is forwarded to the LLM. Gateway observation/delta
filtering remains unchanged. Continuous native telemetry is operator evidence,
not additional strategic model prompts.

## Limits and controlled termination

Each agent independently retained **30 decisions / 300 submitted operations /
1,800 seconds**, maximum 24 operations per generated frame. As in Campaign 001,
explicit host observations/modal operations count toward its operation budget.
Additional failure bounds: **8 total failures**, **4 consecutive failed frames**,
and **at most 2 submissions of an identical failed frame**. There is no automatic
retry, world reset, teleport, rescue, respawn or reactivation.

Admission: 30 seconds warmup, then 120 seconds. Prospective resource rules remained
**≤85% MC-pool CPU**, ≥18 native client/game-time ticks/s, observation RPC p95
≤150 ms, ≥8 GiB MemAvailable, ≥20 GiB disk and no swap growth. During gameplay,
60-second pool headroom, >95% over ten host intervals, sustained RPC/TPS, memory,
swap and storage violations trigger controlled global stop/cancel/persistence.
A separate campaign/global orchestration deadline and operator stop path remain.
No threshold was increased because of background workload.

All four passed preflight: **68.94% MC-pool mean CPU**, stable ~20 TPS, four real
model-context probes, live settings/recording proofs and authenticated gateways.
The host then proceeded directly to gameplay. Agent 02 reached its consecutive
failure budget first; the other three continued. The others eventually reached
eight total failures. These per-agent stops did **not** stop healthy peers.
No campaign had uncertain transport, pending replay or automatic restart.

## Actual concurrency and outcomes

Campaign sessions began at UNIX timestamps **1793809555.364–1793809555.618**.
The last ended at **1793810568.588**, a **1,013.224-second** campaign span. All four
were active simultaneously for **690.885 seconds**, not merely four open windows.
Native worlds continued running independently after individual agent termination
until normal final save/quit.

Peak observed concurrent BCL tasks: **4**. At least two BCL tasks were active for
~**714 sampled seconds**. State sampling is approximately one second; these are
observed intervals, not a claim of nanosecond scheduling precision.

| Agent | Active seconds | LLM decisions | Submitted BCL ops | Returned skill outcomes: succeeded / blocked | Verified walks | Native walking metres | Stop |
| --- | ---: | ---: | ---: | --- | ---: | ---: | --- |
| 01 | 1,013.224 | 23 | 147 | 121 / 8 | 43 | 48.56 | 8 total failures |
| 02 | 691.018 | 16 | 111 | 86 / 7 | 35 | 37.31 | 4 consecutive failures |
| 03 | 750.360 | 18 | 119 | 96 / 8 | 34 | 33.44 | 8 total failures |
| 04 | 901.162 | 20 | 133 | 106 / 8 | 38 | 46.02 | 8 total failures |

Totals: **77 real gameplay decisions**, **510 compiled/submitted operations**,
**440 returned skill outcomes: 409 succeeded / 31 blocked**, **150 verified native
walk goals**. The remaining submitted count includes modal/event operations and
unexecuted suffixes stopped after a failure. These counters are **not interchangeable**.
Four additional model requests were preflight probes, not gameplay decisions.

The raw live operation counter tracks submissions. A separate post-run joined
telemetry file reconstructs completed model/terminal skill counts from timestamped
replies; it does not retroactively relabel submissions as successful outcomes.
Movement statistics are closed native counters, not Euclidean net displacement;
setup/play-time counters are not passed off as gameplay duration.

### What the agents actually achieved

Agent 01 initially surveyed before choosing resources; 02 moved toward nearby
wood, 03 attempted gathering directly, and 04 aimed before gathering. All four
subsequently explored canopy routes and reconsidered inaccessible trees/descent
sites. Some chose bounded native dig-step/clearing attempts. There was no observed
independent house/tool strategy because none established access to usable timber.

Independent closed-save NBT/statistics show:

- Agent 01 mined **2 spruce leaves**, agent 02 **3 spruce leaves**.
- Agents 03/04 have no mined-block counter progress.
- **No item pickups**, empty saved inventories for every agent.
- **No crafting, tools, placed blocks, shelter, food supply or storage** established.
- Every player has **20 health / 20 hunger**, zero death and zero damage-taken stats.
- All four distinct final worlds and private SQLite memories remain preserved.

A blocked skill is **not a no-effect promise**: the partial leaf mutations are
reported despite failed subsequent dig-step goals. Closed native world/statistics,
not model notes, establish these facts. No claim is made that five leaf removals
constitute useful resource acquisition or a base.

The 31 blocked outcomes were **13 `no_verified_step_destination`**,
**11 `no_reachable_exposed_logs`**, **4 `no_reachable_exposed_blocks`**,
**2 `step_not_completed`**, **1 `unsupported_clearance_block`**. These are
observed geometry/resource-access limitations, not evidence of a shared-context,
transport or CPU failure. Their precise underlying terrain/mining causes were not
fixed or independently root-caused during the frozen experiment.

## Actual resource and latency measurements

Campaign MC-pool CPU mean: **68.38%**. No sustained gate violation, swap growth or
sampled affinity escape. Peak summed Java/auxiliary/monitor RSS **16.02 GiB**;
local inference RSS **289 MiB**; minimum MemAvailable **35.92 GiB** and available
disk **39.98 GiB**. Summed RSS can double-count mappings. Recording stayed ON;
packet-byte growth was monitored and its cost is included in these totals.
**Causal isolated recording overhead was NOT MEASURED.**

| Agent | All-RPC p50 / p95 / p99 ms | Observe p95 ms | Model RTT p50 / p95 / p99 s | Model queue p95 s |
| --- | --- | ---: | --- | ---: |
| 01 | 101.6 / 126.8 / 147.5 | 126.2 | 13.94 / 20.89 / 26.22 | 6.60 |
| 02 | 99.5 / 121.1 / 142.2 | 120.4 | 12.45 / 17.08 / 17.08 | 10.90 |
| 03 | 96.8 / 123.3 / 145.9 | 122.6 | 12.45 / 22.90 / 22.90 | 10.59 |
| 04 | 100.5 / 123.9 / 145.9 | 123.1 | 13.46 / 16.86 / 19.50 | 5.53 |

Native client TPS minima were **19.96–19.97**, client-observed game-time minima
**19.87–19.94**. RPC quantiles are nearest-rank per active agent window; model queue
and model roundtrip are separate. RTT includes CLI startup, remote service and
network, not isolated remote forward-pass latency. GPU/VRAM samples are global
host observations, not attributed to the remote model or llvmpipe Minecraft.
Exact rendered FPS/server MSPT were not instrumented.

| Physical core | SMT CPUs | Mean host busy |
| --- | --- | ---: |
| 0, OS spare | 0,8 | 31.33% |
| 1, Minecraft | 1,9 | 71.48% |
| 2, Minecraft | 2,10 | 65.89% |
| 3, Minecraft | 3,11 | 68.39% |
| 4, Minecraft | 4,12 | 68.32% |
| 5, Minecraft | 5,13 | 66.57% |
| 6, Minecraft | 6,14 | 69.64% |
| 7, local inference allowed | 7,15 | 32.50% |

These average SMT-sibling busy fractions include unrestricted background/system
work, not exclusively these process groups. All logical-core means/peaks, GPU,
RAM, storage, RPC, inference intervals, task states and recorder growth remain in
raw and machine-readable evidence. Native bounded trace ring overwrites are not
silently described as zero-loss continuous profiling.

## Recordings, verification and retained diagnostics

Each original campaign recording was finalized before playback QA and copied to
its agent's private `replay/` directory. Capture started before that agent's first
BCL gameplay frame. Metadata, native child/world/actor binding, timestamps, packet
range, file size, SHA-256 and closed-world identity are preserved independently.

| Agent | Replay bytes | Integrity | Actual native playback |
| --- | ---: | --- | --- |
| 01 | 4,401,903 | CRC + complete monotonic framing PASS | Short beginning opened/played PASS |
| 02 | 4,174,633 | CRC + complete monotonic framing PASS | Short beginning opened/played PASS |
| 03 | 4,319,399 | CRC + complete monotonic framing PASS | Short beginning opened/played PASS |
| 04 | 4,252,955 | CRC + complete monotonic framing PASS | **NOT RUN: post-campaign launcher failure** |

The fourth **post-campaign viewer-only launch** reported
`Extension org.freedesktop.Platform.GL.default has invalid merge-dirs` and never
reached a verified owned JVM/TLS endpoint. Its bounded launch timed out. No system
runtime/driver repair, visible-display fallback or hidden rerun was attempted.
This does not retroactively make agent 04's successfully recorded real campaign a
failure to start. The other three playback checks inspected actual rendered world
samples and Exit Replay controls, **not every interaction or the entire duration**.
Original world snapshots were archived before viewer QA. These playback samples
cover recording beginnings, which include setup before autonomous activation;
model-driven gameplay was **not visually audited** through playback.

Other retained diagnostics: the initial preparation used an incorrect allocation
field name and failed before any client/instance was created; it was corrected.
The first closed audit scanned only the replay root and missed files in
`recording/`; its assertion failure was retained. The corrected recursive audit
verified the existing snapshot bytes and all four original recordings. No gameplay
was retried, no world was reset and no historical failure was removed.

## Regression and safe shutdown

**610/610 Python**, **6/6 private host/scheduler contracts** before and after,
Gradle, **TLS 10/10**, **209/209 skills**, **50/50 BCL**, **47/47 Play2Code** and
**7/7 CPU-affinity** isolated mutations PASS. Production movement/crafting/input/
transport were unchanged. A new native 211-case movement cohort, physical F8
injection and deliberate live gateway-crash/death recovery were **NOT RUN**.

New decisions stopped, BCL inputs settled/released, pending state was preserved
without replay, all worlds saved normally, all four campaign recordings finalized,
and gateways/model workers closed. Viewer QA clients also closed. All owned native
and gateway ports are closed, all four control configs disabled, and only verified
owned idle launcher/display processes were stopped. No unrelated services or
processes were pinned/signalled. No commit, push, tag, upload, release or deployment.

Worlds and memory are retained for inspection, **not automatically resumed**.
Any later activation must reconcile fresh native actors/worlds with remembered
hypotheses; it must never replay an old pending frame. Multi-hour autonomy,
hostile-mob Survival, resource progression/home construction and 8/16-agent capacity
remain separately unqualified.
