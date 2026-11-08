# Opt-in two-hour subscription sessions

## Status: implementation qualified; authorized live run RUNNING

The operator subsequently requested startup. See the separate
[live-run report](blockwire-two-hour-session-run.md). Completion, useful cooperation
and full native two-hour qualification are **not yet established**. The preparation
checkpoint and tests below are not relabelled as completed native acceptance.

This profile lets the existing two independent GPT-6-luna loops run for **up to
7200 seconds of gameplay**, rather than stopping at the old 30-decision/300-op
allocation or a handful of known blocked goals. It does **not** guarantee useful
progress, two hours without faults, Survival safety, cooperation, or an eight-hour
soak pass. No new live run/model request is started by preparing this profile.

The prior C3 run remains separate historical evidence: one actor collected three
logs and crafted planks/sticks/a table, neither placed a useful shared workstation.
The earlier C2 TLS failure and series-001 CPU failure remain unchanged. See
[stagnation investigation](blockwire-autonomous-stagnation-analysis.md).

## Coordinated limits — not just a longer timeout

| Limit | Per actor | Two-actor campaign |
|---|---:|---:|
| Gameplay ceiling, starting after fresh native admission | 7200s | One shared gameplay deadline |
| Preparation / finalization allowance | — | 900s / 900s |
| Immutable outer scheduling deadline | — | 9000s from fresh activation |
| LLM requests / decisions | 720 | 1440 |
| Admitted BCL operations, including host queries/settings | 9000 | 18000 |
| Operations per model frame | 12 | Existing serialized actor execution |
| Model concurrency | Sequential per actor | 2 |
| End-to-end request timeout | 90s | No increase |
| Cumulative inference time charged | 7200000ms | 14400000ms |
| Model-ledger audit rows | — | 8192; SQLite remains bounded to16MiB |
| Feedback proposals | 100 | Separate per-actor stores; existing aggregate/storage caps |

The SDK still aborts at85s and its owned worker is killed/waited at90s. This is
not a remote-compute guarantee. Requests reserve before dispatch; uncertain calls
retain charges/slots and halt their actor. Shared counts, deadline/configuration,
deduplication and per-actor allocations survive host restart; **no reset/borrowing**.
An existing 30-minute ledger cannot be upgraded: use a fresh explicitly selected
campaign/world. Stopped/interrupted worlds are not automatically resumed.

The 9000s envelope includes setup and cleanup, **not 2.5h of gameplay**. If fresh
preparation consumes more than900s, the host refuses to start a shortened or
cleanup-starved two-hour campaign. Finalization is cooperative; OS/JVM stalls do
not gain a real-time force-release guarantee. The host stops starting model calls
when their full90s timeout cannot fit in remaining gameplay time, and waits
interruptibly for the deadline without further gameplay submissions.

These are **operational bounds for the explicitly verified existing subscription
route**, not hard output-token/cost ceilings or a paid API qualification. Provider
quota exhaustion/errors stop the affected actor without retry/fallback. This is
not global interception of legacy model adapters or a sandbox for trusted Python.

## Known goal failures vs terminal safety faults

The new opt-in host does not end the entire actor after eight total/four consecutive
known blocked goals, nor after three empty decisions:

- Known terminal `blocked`/goal-timeout: at least30s cooldown, then a **new** bounded
  model decision with fresh actor-matched scene, inventory and local navigation.
- Empty decisions: no empty BCL submission; at least30s idle interval. Finish
  proposals still stop, unverified.
- Normal completed frames: at least10s interval after the frame before another
  model request. Chat/events never trigger model calls.
- After two known failures of the same compiled frame in unchanged observed
  state, further proposals are rejected **before BCL admission** and wait120s.
  There is no substitute action, route, teleport, crafting/resource macro or
  automatically replayed frame. Comments/spacing do not create a different action.
- Partial inventory gain is meaningful new observed state even if a goal returned
  blocked/timed_out. A state change permits reconsideration, not a safety/progress
  certificate. The bounded fingerprint ignores clocks and quantizes position;
  it is not a hidden map or complete semantic equivalence detector.
- `UNKNOWN_NO_RETRY`, actor/player/world replacement, death, F8, resource failure,
  provider error, malformed model output or cancellation remain terminal. No
  automatic reconnect, rebind, respawn, provider fallback or rescue.

The minimum intervals, request caps, 720-entry per-actor failure memory and
immutable deadlines bound idle/replanning loops. Each rejected proposal still
costs a model request. Models cannot edit these policies or grant permissions.
Both actors use separate memories/pacing state; a healthy peer can continue
within its own allocation after the other actor stops.

Recent in-memory history is limited to four frames, with explicit omission
metadata; RPC latency samples use a4096-entry ring while private journals retain
the audit. Event/context, gateway queues, frame sizes, memory/context/response byte
limits and disk/RAM/CPU admission/watchdogs remain bounded. Input-audit10000 and
feedback SQLite32MiB caps are not disabled. All stop/cancel/status paths retain
ordinary authority even at audit/budget exhaustion.

## Use from a trusted host

Offline, no connection or model call:

```sh
python -m blockwire.session_policy
```

```python
from blockwire.session_policy import TwoHourSessionProfile
from blockwire.model_limits import ModelLimits

profile = TwoHourSessionProfile()
policy = profile.model_policy("fresh-two-hour", ("agent-a", "agent-b"))
# Explicit verified subscription proof and a NEW private directory are required:
# manager = ModelLimits(directory, policy, subscription_proof=verified_route)
# Share this manager/ledger between the two independently bound actors.
# Configure each existing gateway with profile.input_policy(immutable_allowlist).
```

`SessionPacing` and `observed_state_key` provide host-side scheduling only; callers
must still validate complete decisions, enforce fresh UUID/actor fences, admit
operations through the common ledger before submission, and release controls in
cleanup. Keeping a two-hour Python loop alive is not gameplay acceptance.

**Legacy defaults are unchanged.** `OperationalPolicy` remains30min/30requests/
300ops, `ExperimentSeriesPolicy` retains its distinct allocations, the ordinary
`blockwire-agent` CLI retains its current short-session limits, and the
[eight-hour soak](autonomous-survival-soak.md) gates are not waived. No Java/native
movement, crafting, collision, placement support whitelist or TLS deadline changed.

## Preparation checkpoint before authorized activation (private)

`build/blockwire-multiplayer/two-hour-001/` is a fresh **PREPARED_NOT_STARTED**
localhost cohort at the preparation checkpoint, using the retained-native-lease
host from C3. It was subsequently activated only by the explicit startup request.
Its two actor
allocation, gateway/input caps, deadlines, cooldowns and context limits are wired
to this profile. No world directory, model ledger or STARTED marker is created
by preparation. No current control endpoint is enabled.

Its supervisor requires a **separate explicit operator activation**: a nonsymlink,
owned0600 `activation-approved-private.json` in that directory, with exactly
`campaign="two-hour-001"`, `gameplay_seconds=7200` and
`operator_authorized_two_hour_run=true`. That approval was intentionally absent
at preparation and was written only after the subsequent **Starte ihn** request.
Future activation must recheck the current model route, original evidence/source,
owned hidden clients, native cancellation/input state, live8/5/30fps settings,
independent actors and fresh CPU/RAM/disk/latency admission. CPU pool ceiling80%,
RAM8GiB, disk20GiB, observep95≤250ms and affinity rules are unchanged. Affinity is
placement, not CPU reservation. The same authenticated native lease is retained
from setup through controller/finalization; its loss is terminal.

Preparation alone launched no game clients/server/display/model workers. The
separate authorized activation now runs the guarded native/model cohort.
The prepared supervisor entry point is
`./.venv/bin/python build/blockwire-multiplayer/two-hour-001/master.py`.
Without the separate matching approval above it fails before STARTED, ledger,
Minecraft or model effects; this refusal is tested. Do not bypass it to run an
old/stopped cohort.

Native two-hour reliability, full injected-fault shutdown, full-duration ReplayMod
finalization/Viewer review and actual useful long-term cooperation remain **NOT RUN**.
Historical native/evidence cohorts are never rewritten as two-hour acceptance.

## Implementation qualification

**748 Python tests, Gradle and TLS10 PASS**. All **159 public mutations** are
killed (137 existing plus22 two-hour policy/scheduling mutations). The actual
prepared host loop additionally passes **26 deterministic tests**, **11 retained
lease handoff mutations** and **8 loop-wiring mutations**. Virtual clocks exercise
the full7200s loop, more than8 known goal blocks, idle decisions beyond the old
limit, repeated-frame rejection, stop during cooldown, unknown receipt, actor
lifecycle, unconfirmed cleanup and journal failure. These are not Minecraft runs.

Initial failures were preserved: a repeatable synthetic threaded-SSL fixture
stall, an ambiguous old mutation anchor and an isolated host-mutator import setup
error. A private comparison passed60 fresh fixture tests after disabling only
synthetic TLS1.3 post-handshake tickets. The fixture change retains TLS1.3, pinned
certificate/auth checks and the3s client deadline; no production TLS code changed
and C2's native timeout cause is not declared solved. Final checks use the corrected
fixture and uniquely scoped mutation anchor.

Machine evidence: [two-hour-session-profile.json](evidence/two-hour-session-profile.json).
