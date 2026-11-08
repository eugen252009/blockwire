# Parallel Survival: verified 6+1+1 CPU allocation and live 8/5 profile

## Measured decision

**Five simultaneous instances is the maximum qualified count under this run's
prospective workload, background load and resource rules.** It is not inferred
from the number of allocated cores.

- 2 and 4 clients passed 120-second measurements; four also passed 180 seconds.
- 6 maintained ~20 TPS, passed RPC/BCL checks, but used **85.53% of the allocated
  Minecraft pool**, just above the **85% headroom limit**. This is a resource-rule
  failure, **not a crash, lost tick performance or failure to execute BCL**.
- Boundary refinement measured **5** rather than leaving that count untested:
  120 seconds passed, then **180 seconds passed** at **77.61% pool utilization**.
- 8 was **NOT RUN** because the six-instance resource gate failed. No threshold
  was relaxed and no 16-agent campaign was started.

This qualifies short native readiness, two existing-runtime BCL camera actions per
client per phase, and concurrent read-only remote-model probes. It does **not**
qualify five long-running Survival agents, concurrent mining/walking/crafting, a
universal hardware maximum or 16-agent capacity.

[Machine-readable measurements](evidence/autonomous-survival-cpu-allocation.json)
and [new hashes](evidence/autonomous-survival-cpu-allocation-hashes.json) are
separate from the [historical unpinned attempt](autonomous-survival-parallel.md).
Old worlds, recordings, verdicts and hash maps remain intact.

## Actual topology and process placement

`lscpu -e=CPU,CORE,SOCKET,NODE,ONLINE`, JSON topology and sysfs sibling lists agree:
Ryzen 7 5800X, one socket, **8 physical cores / 16 logical CPUs**. SMT siblings are
`(0,8), (1,9), …, (7,15)`.

| Role | Physical cores | Logical CPUs |
| --- | --- | --- |
| Minecraft + Blockwire execution | 1–6 | **1–6,9–14** |
| Local inference dispatcher / CLI | 7 | **7,15** |
| Left available primarily for OS/background work | 0 | **0,8** |

`tests/building/cpu_allocation.py` derives this split from physical core/socket
identities, rejecting partial/unavailable SMT pairs. It does not assume consecutive
logical IDs are physical cores. The owned benchmark programs use inherited/taskset
masks and Linux `sched_setaffinity` for **every owned process thread**. Exact UID,
cwd and process start time must match before enforcement. The utility rejects the
caller, wrong identities and malformed allocations.

Java/GC/Netty/render threads, Blockwire BCL workers/monitor, and owned Prism/Xephyr
helpers were restricted to the Minecraft pool. Model probes ran in a separate
process launched on `7,15`, with sampled dispatcher and CLI thread masks checked.
Every measured phase observed **no affinity escape**. Checks were approximately
once per second; raw per-thread masks are preserved.

Some initial Java threads still had broader masks despite inherited launch
placement. Those startup masks were recorded and corrected **before native API
connection and world measurement**. Affinity is not a security cpuset and does not
prevent a process from attempting later changes; the measurement watchdog rejects
observed escapes. No privileged/system-wide cpuset configuration was used.

**No system-service, Xorg, unrelated launcher, user agent or system-wide affinity
was changed.** CPU 0/8 was left unused by benchmark processes, not made exclusive.
Normal services/background jobs remain unrestricted and can use other CPUs. Thus
per-core host utilization includes unrelated work, IRQs and system activity; it is
not all attributed to Minecraft or to the model dispatcher.

The selected model backend remained the existing **remote openai-codex /
gpt-6.1-sol** provider. The one-core allocation applies to **local inference
orchestration/CLI**, not remote model weights or remote server CPUs/VRAM. No local
model was installed or silently substituted.

## Corrected and verified running-client settings

The configuration defect is now understood: Minecraft 26.3 `GraphicsPreset.apply`
sets render/simulation distances to **16/12** for FANCY; CUSTOM does not apply that
preset override. The official mapped class bytecode was inspected privately.

New dedicated `survival-cpu-01 … survival-cpu-08` instances use:

- `graphicsPreset:"custom"`, **renderDistance:8**, **simulationDistance:5**.
- Requested max framerate 30, VSync off, 640×360 window, 2 GiB Java heap.
- `pauseOnLostFocus:false` so unfocused worlds actually run concurrently.
- Inactivity FPS reduction set to **Minimized**, not AFK, before measurement, to
  avoid an idle-only frame-rate change during readiness tests.
- Same Blockwire/Fabric/ReplayMod stack; all experimental stateful reuse OFF.

Each of the **seven actually launched** clients was checked through the native
in-world Video Settings screen **before and after** testing. Required observed
labels were:

```text
Preset: Custom
Render Distance: 8 Chunks
Simulation Distance: 5 Chunks
Max Framerate: 30 fps
Reduce fps when: Minimized
```

Screenshots were not substituted for structured native values; complete native GUI
snapshots are retained privately. Saved options were separately checked after
shutdown. This is **not just an options.txt edit or an inferred preset**. The
unlaunched eighth instance has configured values but no live-value qualification.

Worlds are new independent copies of the earlier verified **clean pre-gameplay**
Survival/Peaceful snapshot, seed 74219031427, empty inventory, full health/hunger,
commands off. The previous progressed campaign world and all earlier instances were
untouched. The same licensed profile UUID is used in separate worlds; native actor
sessions, certificates, API keys and endpoints remain independent.

## Prospective gates and measured workload

Admission rules: **Minecraft-pool mean busy ≤85%**, native client/game-time tick
rates ≥18/s, **observation RPC p95 ≤150 ms**, at least 8 GiB MemAvailable, 20 GiB disk,
zero swap growth, stable actor/health/grounding, and all owned measured threads
inside their assigned CPU pool. CPU normalization is over **12 logical siblings of
six physical Minecraft cores**, not the full 16-thread host. A >95% pool mean across
ten intervals could abort safely. Total orchestration was bounded to 7,200 seconds.

Every measurement followed 30 seconds of warmup. Native observations were sampled
about twice per second. Bounded 512-sample trace reads retained native tick/actor/
monotonic/game-time continuity without overflowing the 1 MiB transport reply limit.
Two non-world-mutating V2 camera goals executed through the existing
`BCLRunner`/`AgentRuntime` per client, with observed angle postconditions and normal
input cleanup required. Native physics, TLS, per-instance trust, actor fences,
ownership, leases, cancellation and F8 were not changed.

Four independent read-only model probes per phase ran while the Minecraft worlds
and observation workload were active. The camera probes occur later in the same
phase; **overlap between camera execution and model requests is not guaranteed**.
No resource acquisition, building plan, movement strategy or autonomous campaign
was substituted for this benchmark.

## Concurrency measurements

The requested ramp was 2/4/6, then 8 only if resource limits allowed. The five-client
refinement was added prospectively after four passed and six missed headroom; it
used fresh unused instance 07 as the fifth client (instances 01–04 + 07), still on
the same Minecraft CPU pool. Instance number 07 does **not** mean CPU/core 7.

RPC values below are **worst per-client** nearest-rank quantiles, not pooled
percentiles. Observe is the admission rule; all RPC types are also reported.

| Phase | Clients | Seconds | MC-pool mean CPU | Observe p50/p95/p99 ms | All-RPC p50/p95/p99 ms | Result |
| --- | ---: | ---: | ---: | --- | --- | --- |
| C02 | 2 | 120 | 34.02% | 45.7 / 81.7 / 91.9 | 51.6 / 90.3 / 102.6 | GO |
| C04b | 4 | 120 | 62.47% | 58.3 / 98.0 / 109.5 | 67.5 / 107.5 / 120.7 | GO |
| C06 | 6 | 120 | **85.53%** | 74.1 / 129.5 / 149.8 | 84.9 / 141.1 / 179.4 | **NO-GO: CPU headroom only** |
| CONFIRM04 | 4 | 180 | 62.33% | 53.6 / 97.1 / 110.9 | 59.8 / 108.1 / 120.0 | GO |
| C05 | 5 | 120 | 76.43% | 63.2 / 110.6 / 127.7 | 74.7 / 117.2 / 144.8 | GO |
| CONFIRM05 | 5 | 180 | **77.61%** | 69.0 / 126.0 / **150.6** | 77.2 / 135.0 / 163.4 | GO under p95 rule |
| C08 | 8 | — | — | — | — | NOT RUN: six failed resource gate |

All measured clients stayed around **20 native ticks/s**, with matching
client-observed game-time progression. Six executed the BCL programs successfully;
its headroom failure was only **0.53 percentage points** over the declared limit.
That limit was not changed after seeing the result. Five's p99 tail is explicitly
reported above; a p95 admission pass is not a claim that every RPC is below 150 ms.
Rendered FPS and exact server MSPT were not independently instrumented.

There were **26 verified camera BCL programs / 52 camera operations** across these
windows and **24 read-only model requests**. These are mechanical benchmark actions,
not autonomous Survival decisions. Peak actual concurrency was six; no 8- or
16-instance capacity is claimed.

## Actual per-core CPU distribution

Values are mean host busy percentages **averaged over each physical core's two SMT
siblings**. They are neither exclusive process attribution nor a claim that SMT
doubles physical-core throughput. All 16 logical-CPU means/peaks and raw deltas are
also preserved in machine-readable evidence.

| Physical core | SMT CPUs | Benchmark role | 2 clients | 4 clients | 5 clients | 6 clients | 5-client confirmation |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 0 | 0,8 | OS spare, benchmark excluded | 13.24% | 20.83% | 18.43% | 25.96% | 35.69% |
| 1 | 1,9 | Minecraft/Blockwire | 47.49% | 65.79% | 78.16% | 86.21% | 79.18% |
| 2 | 2,10 | Minecraft/Blockwire | 20.10% | 59.08% | 75.89% | 85.54% | 77.18% |
| 3 | 3,11 | Minecraft/Blockwire | 39.58% | 62.89% | 76.06% | 85.22% | 77.22% |
| 4 | 4,12 | Minecraft/Blockwire | 30.41% | 62.50% | 75.98% | 85.59% | 77.46% |
| 5 | 5,13 | Minecraft/Blockwire | 23.97% | 60.58% | 75.46% | 85.12% | 76.46% |
| 6 | 6,14 | Minecraft/Blockwire | 42.54% | 64.01% | 77.05% | 85.50% | 78.16% |
| 7 | 7,15 | Local inference allowed | 11.77% | 19.26% | 18.04% | 24.15% | 34.85% |

For example, sampled owned MC processes accounted for approximately **69.23%** of
the MC pool during five-client confirmation, versus **77.61% total busy** including
unmodified background/system activity. At six, the corresponding figures were
**82.51% owned / 85.53% total**. Those owned-process estimates use sampled live-PID
CPU-counter intersections and can miss short-lived intervals; the independent host
core counters drive the conservative headroom gate.

Core 7's 34.85% is **not** attributed entirely to the model CLI: the local probe
processes were brief and their sampled attributed pool fraction was much smaller.
The OS spare being busy likewise does not imply benchmark threads escaped there.
Their recorded masks exclude 0/8; ordinary background work was deliberately not
moved or restricted.

## RAM, GPU and inference latency

| Phase | MC Java + auxiliary + monitor RSS peak | Local inference RSS peak | Minimum MemAvailable |
| --- | ---: | ---: | ---: |
| 2 clients | 7.65 GiB | 272 MiB | 47.09 GiB |
| 4 clients | 15.19 GiB | 274 MiB | 39.69 GiB |
| 5 clients | 18.64 GiB | 274 MiB | 35.85 GiB |
| 6 clients | 22.73 GiB | 270 MiB | 31.04 GiB |
| 5 confirmation | 18.69 GiB | 275 MiB | 35.10 GiB |

No swap growth occurred. Summed RSS can double-count mappings; it is not unique
physical RAM consumption. All clients remained on the established hidden
**CPU llvmpipe** renderer. Sampled global GPU peaks were 3060 **12 MiB / 0%** and
2080 SUPER **794 MiB / 46%**; these include unrelated host graphics and are **not**
credited as Minecraft GPU acceleration or remote model VRAM usage.

The local dispatcher and at most two concurrent CLI requests were bound to
`7,15`. Model roundtrip latency includes CLI startup/parsing, network and remote
service time; isolated remote forward-pass latency/VRAM is unknown.

| Phase | Model RTT p50 / p95 / p99 seconds |
| --- | --- |
| 2 clients | 6.22 / 6.62 / 6.62 |
| 4 clients | 6.23 / 7.53 / 7.53 |
| 5 clients | 5.72 / 6.34 / 6.34 |
| 6 clients | 6.13 / 8.25 / 8.25 |
| 5 confirmation | 5.64 / 9.49 / 9.49 |

Only four small-context requests were made per phase: p95/p99 therefore reflect
sample extrema, **not an inference-service SLA**. Queue delays, individual RTTs,
SDK-reported token counts and per-thread affinity samples remain in the evidence.
No full-gameplay-context throughput or 16-agent scheduler qualification is implied.

## Preservation, retained errors and shutdown

All earlier campaign/parallel evidence was left intact. Eight new clean worlds
were prepared; seven were launched and independently checked after shutdown:
Survival/Peaceful, full health/hunger, empty inventory and no mining/crafting/item-use
progress. All seven original readiness replays passed ZIP CRC and complete
monotonic packet-framing checks. Native viewer playback was **NOT RUN for these
new artifacts**, not borrowed from historical playback acceptance.

An initial C04 setup was not run because native exclusive-controller HTTP 409
prevented an immediate follow-up live-settings connection. Its incomplete directory
and error remain; fresh setup proofs plus a release interval preceded **C04b**.
No native exclusivity or TLS timeout was weakened to pass.

After all measurements completed, agent 03's shutdown connection timed out during
handshake, before any close RPC. That client was **not reconnected/replayed**:
normal WM_DELETE was sent only to the UID/cwd/start-time/display/PID-verified owned
game window. Its saved NBT/world and finalized replay were independently verified.
Other clients used native save/quit normally. The cleanup issue is retained rather
than being erased by the successful measurement.

All owned games, local model workers, native ports **11601–11608**, reserved gateway
ports **12601–12608**, and the owned launcher/display are closed. Controls are
disabled; no pending gameplay or persistent service affinity change remains.
Unrelated processes were not signalled or pinned. Historical maps were not regenerated.

Regression: **610/610 Python tests**, including seven CPU allocation/authority
contracts; **7/7 isolated CPU-guard mutations**, **209/209 skill**, **50/50 BCL**,
**47/47 Play2Code** mutations; Gradle and **TLS 10/10 PASS**. Production Java/Python
execution was unchanged. Physical F8 injection and a new 211-case movement run were
**NOT RUN**; no movement/general Survival qualification is claimed.

No commit, push or deployment occurred. The five-instance finding is specific to
this configuration, background load, duration and headroom rule. Changing the rule,
using a GPU-backed renderer or attempting 8/16 requires a new bounded qualification,
not reinterpretation of the retained six-instance result.
