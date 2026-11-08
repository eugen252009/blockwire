# BCL machine profile — actions, reporting, interrupt

`machine-v1` is an explicit new gateway profile on the existing authenticated
BCL/1 TLS transport. Legacy BCL/1 programs, opcode meanings, saved coordinate homes
and historical replay evidence are not migrated. Use a new state directory/session.

## Independent action, reporting, control and perception paths

1. **Action FIFO:** small native commands, or a finite ordered composition of them.
   No search, resource selection, recipe selection, path planning, observation opcodes,
   variables, loops, callbacks or executable game text. Compile the whole frame
   before effects. Native Minecraft owns physics, reach, crafting and inventory.
2. **Reporting:** an out-of-band `report` request selects channels. Initial values
   and subsequent changed values arrive as unsolicited events while the FIFO runs.
   This is M155-like automatic reporting, NOT an observation instruction inserted
   into a program. State is sampled at a bounded cadence; this does not claim every
   intermediate game tick is captured. Native chat/entity push remains optional.
3. **Interrupt:** out-of-band cancellation of this controller's active AND queued
   work, not a command appended to the FIFO. Its receipt means cancellation requested,
   not release. No new action is admitted until terminal cleanup and a fresh native
   input-release proof, followed by explicit `resume`. Uncertain release quarantines
   the controller; no replay, automatic reconnect/rebind/respawn or automatic resume.

4. **Explicit perception:** cached `look_around` filters delivered scene data;
   `search` requests additional bounded native ray pages. Neither is an action-BCL
   opcode or composition member. No implicit turning, movement, harvesting or
   resource route. No match means not seen, never absent. See [search](search.md).

The paths are independent tasks, not competing native controllers. Native RPCs
still share one authenticated lease and are serialized individually. Reporting
never waits for an entire program to finish. A stalled native RPC cannot be made
instantaneously cancellable in Python; native short leases and F8 remain independent.

## Lean action vocabulary

- `G1`: bounded directional input pulse. This is not a one-block teleport or a route.
- `G2`: native camera orientation to explicit angles or a world-space point, with observed angular completion.
- `G3`: explicit input phases with retained common keys, optional aim and one-shot press; see [construction mechanics](machine-construction.md).
- `M1`: one native attack/use press, followed by fresh release observation.
- `M2`: attack/use hold up to30s (command deadline at most35s); each native
  lease still at most6 ticks. Long interactions need continuity, not a longer
  native lease. Renewal under real game load remains unqualified.
- `M3`: select a hotbar slot and verify selection.
- `M4`: open/close the native inventory and verify its state.
- `M5`: one click with exact menu/state/slot identity. Pickup and quick-move only.
- `M6`: caller-specified slot/cursor assertion program with fresh IDs and no click replay.

Inventory transfer x→y is a composition of guarded clicks using newly reported
menu/state IDs. A multi-click recipe is not an atomic transaction; stale IDs fail
closed. Block placement is native `use`, not direct world modification. No auto-equip,
support substitution, material choice or placement retry is hidden in the command.

`completed`/program completion describes command execution and its stated local
postcondition (e.g. input release), NOT a successful placement, harvest or external
goal. Those outcomes must be established from reported world/inventory changes.
Internal reads for identity, native preconditions and completion checks remain
mandatory; removing observation *opcodes* does not remove safety checks.

## API and compatibility

Gateway selection: `--profile machine-v1`. Clients bind with the same explicit
profile, actor and UUID. Profile mismatches are rejected before admission. Old
clients continue to use `legacy` by default; no global opcode replacement.

Typed `action(name, parameters)` requests compile to canonical instructions using
only the authoritative registry. `compose(actions)` accepts1..32 discriminated,
strictly typed calls and validates the ENTIRE composition before dispatch. The
model supplies JSON, not BCL strings. MCP exposes these schemas without requiring
the model to write code. BCL text remains available to explicit program authors.
`report`, `interrupt`, `resume` and the bounded `search` page request are
transport/control/perception requests, not action opcodes. Search requires `observe`
permission; one native page in flight per gateway; interrupt invalidates its result.

State reports include actor identity, host sample identity and observation time;
they are partial client-known snapshots, not atomic omniscient world state. Wire
sequence numbers identify gaps. Queue overflow/oversize or native loss fails closed;
critical control must not be silently discarded. No durable event replay.

### Entry points

- `python -m blockwire.bcl.gateway --profile machine-v1` plus the existing explicit
  certificate, key, token and state-directory arguments starts the gateway. Use a
  fresh, dedicated state directory and explicitly review any opcode policy: opcode
  meanings are profile-specific. Do not repurpose a historical campaign ledger or
  blindly carry a legacy opcode allowlist into this profile.
- `python -m blockwire.machine_mcp --help` describes the explicit TLS binding.
  Tools: `pulse`, `turn`, `press`, `hold`, `select_slot`, `inventory_screen`,
  `click_slot`, `input_sequence`, `slot_program`, `compose`, plus `remember_plan`,
  `reporting`, `events`, `look_around`, `search`, `task_result`, `interrupt`,
  `resume`. No legacy BCL/source/high-level goal tools are exposed.
- `python -m blockwire.machine_agent --help` starts the explicit external-model
  host. Its decisions receive delivered event snapshots, request history and task
  results. Explicit `search` can additionally obtain bounded native sight data;
  `look_around` reads the cached scene. Neither performs exploration. A background
  consumer drains events during inference and action execution. The model can
  choose `interrupt` during a running composition. Defaults:600s,20 inference
  requests,100 reserved operations; no restart of a used run directory.
  Each search durably reserves its full34-page maximum against that operation cap,
  reported as `reserved_search_pages` separately from action operations. Failed or
  unused reservations are not reclaimed. Internal action safety reads remain separate.

### Explicit extended runs

Defaults and ordinary limits remain unchanged (maximum1,800s,100 decisions,
1,000 operations). `machine_agent --extended-run` / `run(..., extended_run=True)`
explicitly permits up to **86,400s,1,000 decisions and1,000,000 operations**.
Set `--duration`, `--max-decisions` and `--max-actions` as well: the flag alone
never raises their small defaults. Limits are persisted before inference, and
remaining model calls, operations and time are supplied as context. This is an
operator-selected execution envelope, not a currency/token quota or a guarantee
of progress, uptime or provider availability. `finish_session` can still end early.

For an external MCP facade, explicitly select `--max-session-tasks 1000`
(`create_machine_server(..., max_session_tasks=1000)`). Its default lifetime bound
remains128 task IDs. This is **not queue capacity**: the existing action FIFO,
active-task, wire, event, native lease and per-command timeout bounds stay intact.
Admission accounting is serialized across primitive/composition calls, without
locking interrupt or cached status. Old task results may still be evicted from
the bounded SDK cache; missing results never authorize replay.

Long runs require an independently supervised hardware/storage/lifecycle stop and
an explicitly authorized model. Use fresh private directories; never restart a
used ledger, auto-respawn/rebind or replay uncertain work. F8, actor fencing,
release confirmation and terminal uncertainty rules are unchanged. A generous
budget is not permission to weaken these protections. Extended offline contracts
are in `python/tests/test_machine_extended.py`; a1,000-decision simulated scan loop
is **not**1,000 real-model calls or a24-hour graphical qualification.
The [first real extended allocation](machine-extended-runs.md) ended after18
model-selected calls despite ample remaining budget; its server-save timeout is
retained separately. It does not qualify1,000 real calls or collection success.

After SDK reinstall, the equivalent scripts are `blockwire-machine-mcp` and
`blockwire-machine-agent`. Existing entry points remain explicitly **legacy**;
no previously configured host or frozen campaign is silently switched.

MCP's `events` tool drains a local inbox, not Minecraft. State channels are
coalesced to their latest snapshots with a cumulative coalescing counter; the
command/control queue is bounded64 and never silently drops. The MCP host automatically enables initial reporting. Generic MCP hosts
must consume this inbox themselves; MCP notifications do not automatically launch
inference. The standalone machine agent consumes it concurrently. The gateway
uses an independent sampler (at most one refresh per0.5s), emits changes and
refreshes unchanged channels with a2s heartbeat (`changed=false`). Quiet state
therefore does not leave a permanently stale baseline. `observed_monotonic_ns`
is the start of the non-atomic sample; compare it with a completed command's
`input_release.release_observed_monotonic_ns`, not message arrival order, when
requesting post-command evidence. Both clocks belong to the same gateway process.
This is not a claim of new Java event hooks for every transient state change.
Existing optional native chat/entity pushes remain separate.

### Example typed composition

```json
{"actions":[
  {"name":"turn","parameters":{"yaw":90,"pitch":0}},
  {"name":"pulse","parameters":{"buttons":["forward"],"seconds":0.2}}
]}
```

The executor does not invent the next action, target or recipe. To move exactly
one block, a caller must use position events and explicit bounded corrections;
`pulse` itself promises only a bounded input interval and observed input release.
Movement pulses are at most2s. Hold/input/slot programs have at most35s command
deadlines; other commands at most5s. Each primitive releases its inputs. Common
keys can be retained only within explicit `input_sequence` phases, not across
independent primitive calls. Arbitrary GUI/text entry is not implemented; finite
composition is not a claim that every human interaction is already expressible.
No silent fallback to a legacy skill is permitted for a missing primitive.

Controller binding checks compatible, fresh native motion ticks before any action.
Returning to an existing controller session requires release proof and explicit
resume; a new connection never resumes or replays cancelled work automatically.
Failed/cancelled execution also passes a read-only release barrier before the FIFO
can start another frame. Uncertain proof quarantines the dispatcher, including
new actor/session admission, rather than merely hiding the old task.

Ordinary `cancel`, `reset` and `respawn` requests are rejected in this profile so
legacy controls cannot bypass the machine interruption barrier. An interrupt
carries a generation ID; only the matching fresh release event confirms that stop.

## Qualification

The later [hidden real-model search test](search-hidden-test.md) qualifies only
additional perception in a declared synthetic sight fixture: exposed-log discovery
beyond coarse rays, occlusion and short-range negatives. It does not qualify
natural-world exploration, harvesting or general machine gameplay.

Initial profile checks (before the [construction extension](machine-construction.md)):
**779 Python tests PASS**, `./gradlew check` PASS,
**10 TLS interop checks PASS**, **14/14 machine mutations killed** and **6/6 typed
provider mutations killed**. Simulated-backend TLS tests cover concurrent reports,
queue cancellation, explicit reconnect/resume, stale release quarantine, wire gaps,
unchanged-state heartbeats, audit failure, typed compositions and model decisions
while an owned composition is still active. See [contract evidence](evidence/bcl-machine-contracts.json).

New graphical-client/native gameplay acceptance: **NOT RUN**. Unit/TLS tests can
qualify parsing, separation, queue bounds and cancellation contracts, not practical
navigation, successful mining/crafting, damage avoidance or Survival completion.
