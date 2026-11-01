# Persistent projects (development)

A project is data above BCL, **not a building generator**. External model → typed
project decision/BCL → existing compiler/IR → BCLJobs/AgentRuntime → native Minecraft.
The model selects design, site, materials, priorities, access, repairs and revisions.
`ProjectJournal` owns facts, bounded persistence and acceptance. `ProjectAgent`
coordinates that model over the existing TLS SDK, with no second player controller.

## Fixed-reference building follow-up

The separate [Superflat benchmark](superflat-building.md) freezes a 71-block
reference independently of any model plan, restores identical closed snapshots,
and compares deterministic BCL with real external-model BCL. Its privileged
closed-save test audit is NOT exposed to project agents. Original trials and
assessments below remain historical, not silently requalified by newer code.

## Previous Stage B diagnosis

The recorded [previous qualification](gateway-building.md) and hashed artifacts
were checked before this follow-up. Its 333 Python tests/233 killed mutations and
10 TLS checks are historical baseline results, not new gameplay acceptance.

B01: one hand-soil harvest timed out with partial resources, one failed drop pickup,
one unsupported route, one wrong placement face and one player-body overlap. It
placed a roof; descending excavation later removed it. B02 repaired that SAME roof
position, not a second roof cell. B02's executed programs contain **86 aiming and
90 observation operations**, six successful walks, two `stuck` and two
`no_known_safe_route` failures. Repeated views were not relevant project progress.

Causes are separate:

- **Project management:** short notes/partial manifests were not a durable complete
  design. A batch finish was previously mistaken for the external goal. There was
  no compact canonical requirements/material/progress state across activations.
- **Observation:** camera sampling did not prove all walls/roof; removal could leave
  stale surfaces in a naive accumulator. Non-visible does not mean absent. A former
  harness also discarded intermediate V0 results; all outputs must be processed in
  order, with mutations invalidating affected evidence.
- **Navigation:** grass-lip/roof geometry did not provide a proven standable doorway.
  The native full-body/headroom/step graph correctly refused unsupported entry.
  Widening safety constraints or treating `arrived` as doorway proof is not a fix.
- **Planning:** the model spent many successful camera batches without resolving
  its enclosure/access requirements. It did not strategically revise the persistent
  whole goal when inspections stopped producing relevant information.
- **Harness:** an old whitelist rejected natural stone/grass floor/wall manifests;
  a rectangular-only predicate mismatched the chosen dugout. Correcting that bug
  did NOT establish an accessible complete shelter. The prior attempt remains failed.
- **Mechanical gaps:** full-cube plank placement was needlessly excluded despite
  existing log/plank recipes. It now uses the same guarded placement path. General
  terrain, arbitrary demolition and recovery-efficient cave construction remain
  unsupported, not replaced with hardcoded Survival progression.

## Typed data and persistence

`blockwire.projects.ProjectPlan` contains an operator-bound dimension/site, unique
position/material requirements with named sections, material reserves and optional
acceptance geometry. It is strict Pydantic data, not executable Python. Limits:
256 block requirements, 16 sections/reserve types, radius 16 around the declared
site. General requirements use registry IDs (not arbitrary code or block-state
predicates); enclosure walls/roofs and absence-by-clearance inference require the
explicit ordinary full-cube catalogue. Estimated demand is computed from the
model's requirements, never generated as a house plan by the host.

`ProjectJournal(path, identity, project_id, goal, policy=...)` reuses `SessionStore`:
private SQLite/0600, exclusive POSIX lock, 256 KiB context cap. Only trusted host
code selects paths, world namespace and fixed acceptance policy. `identity` uses
agent_id/world_id/player_id. **world_id is an operator-selected world namespace,
NOT a native save UUID**; the operator must select the correct owned world. No
hidden save/NBT queries or certificate/transport changes are used to infer identity.

Persisted state includes plan revision/digest, requirement states, observed
inventory, verified placement consumption by material, blockers, running intent,
request high-water marks, last observed actor/world pose, bounded recent events,
model/operation counters and objective status. A revision does not reset budgets.
Changing goal/policy/world identity is rejected. A different native dimension
requires a separate project, even when actor rebind is explicitly authorized.

A plan revision invalidates progress; on every activation all old proof is stale.
Historical plans and verified action counts survive, inventories do not become new
actor possession. `bind(scene, allow_rebind=True)` must be explicitly authorized
after replacement. Pending intents become `interrupted_intent_not_replayed` only
after a fresh valid bind. No action list, input receipt or model memory is replayed.

## Observe → reconcile → verify

Requirement states:

- `correct`: fresh native visible ID exactly matches the planned full cube.
- `wrong`: a different solid/observed ID at that coordinate.
- `missing`: native standing body/head clearance proves the planned FULL CUBE cannot
  be there. This does **not** claim literal air or inspect arbitrary hidden blocks.
- `unknown`: no adequate fresh proof. Unseen/unloaded is never absent or correct.

Only plan targets are cached, not an expanding world map. Surface evidence expires
at 120 seconds; native floor/headroom/connectivity at ten seconds. Re-observation
can downgrade previously correct positions and emits a world-change event. This
can detect damage/player edits when reobserved, not attribute who changed a block.

Mining, failed/partial potentially world-mutating batches and plan changes invalidate
evidence. Local movement/aim failures retain bounded surface proof but discard stale
navigation; they do not falsely imply every wall vanished.
Successful exact placement invalidates its target and native geometry; later V0
results reconfirm them. Every operation's V0 is processed in order, so an observation
BEFORE excavation cannot certify the post-excavation state. A fresh final sweep is
mandatory and world mutations end it. These are sampled client observations, not
server-atomic or permanent guarantees; unsupported/hidden changes remain unknown.

Block requirements and native access are separate. A placement-pose/route failure
becomes a bounded blocker scoped to the **current native mesh**, not a global claim
that the coordinate/resource can never be reached. The model chooses another pose,
route, resource, site, order or revised design. There is no `if roof -> gather oak`.

Result semantics remain distinct:

- `COMMAND_COMPLETED`: terminal operation, possibly failed.
- `BATCH_COMPLETED`: terminal BCL result, not the objective.
- `PROJECT_PROGRESS`: reconciled observed requirement counts.
- `OBJECTIVE_INCOMPLETE`: unknown/missing/wrong/unsafe/unverified conditions remain.
- `OBJECTIVE_VERIFIED`: fixed trusted criteria met in a fresh quiescent sweep.

BCL `program_verified` continues to attest ONLY its subprogram; external
`objective_verified` remains false there. A model's `finish` is a proposal only.

## Mechanical independent observation acquisition

`blockwire.project_inspection.inspect_project` inspects only the existing MODEL's
frozen targets, through the existing BCL exchange callback. It does not build,
mine, craft, choose resources, infer unseen IDs or own player inputs. The host
routes and fences every V0/V2/M0 through the usual SDK/runtime. Batches and view
poses are bounded, world mismatches return to the external planner, and every
inspection charges the host's existing operation budget. Up to three 64-operation
sweeps per activation are allowed; no budget is reset. Operator QA used a separate
explicit read-only inspection budget and never enabled building permissions.

It aims at exposed FACE centres rather than an interior cube centre: the latter
can hit a neighboring stacked cube before reaching the requested block. Candidate
poses are limited to currently reachable native cells near the initial elevation;
inspection may revisit a pose for a DIFFERENT remaining target (not blindly repeat
the same failed view). Merely aiming never certifies existence. Actual fresh native
surface IDs plus native geometry must still meet the whole fixed contract.

The first native QA sweep exhausted 63 operations with seven unknown targets. A
second sweep had one interior floor left unknown because a global visited-pose
filter prevented returning inside. Both failures remain. Per-target pose revisits
then verified all 26 targets in **35 operations**, without construction or inventory
changes. Current ProjectAgent's integrated inspector also returned
`OBJECTIVE_VERIFIED` in a separate native integration test (46 operations), using a
deterministic VERIFICATION-ONLY request, not a fake building planner.

## Independent enclosure policy

`enclosure_v1` is an opt-in operator-selected acceptance contract, not the general
project schema or a construction skill. Before construction the MODEL must declare
connected interior cells, one cardinal-adjacent entrance, height 2–4 and all desired
blocks/sections. The validator rejects holes in side/corner columns, blocked body/
head space, absent roof above any interior/entrance cell, duplicate coordinates,
foreign dimension and unbounded designs. It generates no placement sequence.

The design can vary; there is no host-selected size/location/material/template.
Full final acceptance needs every declared block freshly matched, reachable safe
native standing cells for ALL interior cells and doorway, an actual doorway edge,
a fresh final sweep, no pending effects, and a previously OBSERVED unmet target
becoming correct in this same plan, or a verified native placement OUTCOME at a
matching current-plan target (appearance AND consumption, not an input receipt).
Baseline survey precedes construction; initial
unknown is not invented empty space. This causal world-state witness survives lost
receipts/restarts. A receipt counter or unrelated old placement cannot establish it. Compatible
revisions preserve historical unmet-target witnesses only where coordinate AND
expected ID still match; current surface/geometry proof is nevertheless invalidated.
Player attribution/consumption is separately audited in the actual qualification. Natural pre-existing walls require native
observation, not an invented manifest. `blocks_v1` is a separate general block-goal
policy; it must not be substituted for shelter qualification.

## One-voxel mechanical adapter

`I4 Bmaterial P[x,y,z]` / `place_at` takes ONE agent-selected desired coordinate,
not a support. It checks an already observed result first, considers only currently
observed neighboring full-cube supports, ranks visible faces, and delegates to the
existing actor-fenced `place_block`/walker. At most three pre-use candidates are
tried. Uncertain use, motion/actor/inventory failure NEVER triggers another use.
There is no design, acquisition, construction order or scaffold generator.

The old traces showed significant model effort spent choosing support/face geometry.
I3 remains compatible explicit control; I4 removes this unnecessary mechanical
burden without deciding which voxel the agent wants. A separate real-TLS/native
probe placed a model-declared missing roof voxel using I4 AFTER the failed B world
was saved. That operator probe is **not** reclassified as autonomous B completion;
the next fresh trial starts from the CLOSED EMPTY baseline again.

## Materials and idempotence

`material_report` supplies per-material unverified/missing demand, current inventory,
known-only and worst-case shortfall, native recipe metadata, available recipe batches
and possible output. Unknown requirements are explicitly separated and require
observation, not automatic collection. The legacy shortfall field is worst-case.
Options are independent arithmetic, NOT jointly reserved resources or a strategy.
For 24 planned planks, eight held planks and two matching logs: direct shortage 16,
possible recipe output eight, remaining shortage eight. The model decides what to
craft, collect, substitute or abandon. Unknown targets should be inspected before
assuming they need materials. Reserves and temporary access blocks are model data.

Verified `block_placed` events track consumed material separately from world
progress. Inventory deltas are recorded as NET observed changes, not silently
attributed to gathering/crafting/consumption. Section completion uses current world
proof, not placement-event counts.

Explicit-support `I3` first checks a fresh native observed destination. If it already
matches, `desired_block_already_observed` succeeds WITHOUT a use or item consumption,
even without a held copy. Unknown destinations are not presumed correct. This is
postcondition idempotence, never replay of an uncertain transport request. Small dry flowers (including lily of the valley) can be cleared by one separately
fenced native attack before placement; fresh EXACT ground-support proof is required
before any use. A mere attack receipt never authorizes blind placement. Structural
blocks, dangerous plants and unknown vegetation are not cleared by that path.
Existing request deduplication, actor fences, ownership, exact native hits and placement
consumption verification remain. Planks join supported full-cube placement/support
materials; partial shapes, fluids and arbitrary mod blocks do not.

## Explicit host and lifecycle

Offline schema: `.venv/bin/python examples/project_agent.py --describe`.
Model context retains the last ACTION result separately from the follow-up V0/I0:
a successful inspection must not hide the failed placement's actual hit/face data.
Observations are timestamped at capture in BCL outputs, not rejuvenated when a
multi-operation frame finally arrives. Timestamp/clock assumptions are local trusted
gateway wall-clock; this is not cross-host authoritative time synchronization.

The example requires explicit gateway URL, pinned certificate/token file, project
state/audit files, trusted model argv JSON, identity, actor session, goal and limits.
It does not start a gateway or select a cloud/model implicitly. Model subprocesses
get copied data, no Player, native credentials, tools or filesystem authority.
`--resume` is explicit; `--rebind` additionally authorizes a freshly observed actor.
Use the same project contract and correct operator-selected world. Gateway/native
controller exclusivity still applies. Do not start a second competing native host.

Budgets: max 100 model calls per activation (default 60), 160 per persistent project,
512 total BCL operations including observation exchanges, one queued/active request
from this host, ≤32 operations/frame, duration ≤3600 seconds, 10 unchanged relevant
states by default (≤20). Newly confirmed requirement positions within the activation, verified placements,
plan revisions or inventory changes are relevant; camera rotation and re-seeing an
expired previously confirmed surface alone are not. Fresh activation revalidation
has its own confirmation high-water, never reused as current proof. All limits are host-side and plan revisions cannot reset them.
Requested placements (256), gathered item counts (512) and crafting batches (128)
also have persistent host-side reservation caps, charged before effects even for
failed attempts. These are conservative request budgets, not invented physical
consumption. Native action deadlines, actor guards, short input leases, F8, TLS, per-instance
trust, authentication, isolation and cancellation are unchanged. A timeout/disconnect
means uncertain work: preserve its intent, stop, close/cancel through the gateway;
never automatically reconnect/replay. Truly noncooperative trusted Python remains
a quarantined explicit-host-restart boundary.

A fresh-state summary contains the plan, section counts, each unknown/missing/wrong
position, inventory/demand/options, current bounded blockers, last observed pose,
running intent, counters and recent decisions. A new LLM invocation needs this
summary, not the full old conversation. Goal-policy checks do not choose actions.

## Qualification

Implementation, simulated snapshots, TLS/native integration and actual external-LLM
Minecraft trials are separate.

A first fresh supplied-material trial (`build/project-verification/A01`) completed
uninterrupted with **56 actual external LLM calls**, 40 verified cobblestone placements
and **43/43 declared requirements** matched. Its independently model-chosen 4×4
outer design has 2×2 interior, two-high walls, roof, entrance, access and observed
floor requirements. A separate conservative replay of native observations AFTER
the last potential world mutation independently passed the fixed enclosure policy:
all declared blocks plus current native reachable interior/floor/headroom/entrance.
Model finish and input receipts were not used as proof. The saved completed world
is retained privately. This is **Stage A GO for this one uninterrupted trial**, not
proof of repeatability or Survival material acquisition.

### Controlled recovery

A02-interrupt began from another unbuilt supplied-material baseline. The real model
chose its own 54-voxel design. After ten actual placements the harness intentionally
lost the terminal acknowledgement BEFORE project commit: seven were committed and
three remained uncertain. The durable intent survived. After save/reload and a
fresh explicitly authorized actor binding, A03-resume restored the SAME plan with
no old conversation and never replayed that intent. Across both activations there
were **56 placements at 56 unique positions**, covering all 54 model targets plus
access blocks, with no duplicate consumption. Final inventory was eight cobblestone.

**The recovered whole goal did NOT pass.** The model lost supported descent from the
finished roof and stopped on `no_relevant_progress_budget`. A complete placement
ledger is not current world/native access proof. This remains CONDITIONAL recovery
qualification, not an uninterrupted success or an accepted goal.

### Controlled empty-inventory Survival

Fixture: new natural **Blockwire Persistent B02**, seed 2, Survival/**Peaceful**,
commands OFF, bonus chest OFF explicitly captured in creation UI, respawn radius 0,
empty inventory, no provided resources/tools/structure. Peaceful is a declared
hazard reduction, not Normal/hostile/food or general unattended qualification.

- B01: 60 real model calls, regular wood acquisition, native planks and 26 placement
  events; stopped incomplete on its model-call bound. B02-resume was the SAME world,
  not a new fresh trial; it stopped again on lack of relevant progress. Both failures
  and a closed failed-world snapshot remain unchanged.
- After the generic I4 improvement, B03-fresh restored the CLOSED EMPTY baseline:
  a second independent fresh attempt on the SAME seed, not a repaired failed world.
  The model first chose a larger 42-plank design, then autonomously relocated and
  reduced it to match **24 planks actually crafted from six gathered oak logs**.
  It placed 14 wall blocks, nine roof blocks and one temporary access block. No
  crafting table/tool was needed for this chosen material; tool progression is NOT
  claimed. A native lily clearance occurred through explicit I3 Ctrue; no operator
  cleared the site. Final native floor/access proof uses the natural grass floor.
- The original B03 terminal remains `OBJECTIVE_INCOMPLETE / no_relevant_progress_budget`
  after 47 model calls. Its late compatible-plan revision discarded a historical
  change witness, and model-directed cube-centre/negative-coordinate views left
  three targets unknown. Those generic metadata/inspection faults were fixed;
  the original failed terminal result was NOT rewritten.
- B04 was VERIFICATION-ONLY, with world-mutating permissions removed. Its LLM also
  reached the ORIGINAL 512-operation project limit. No resource/action counter was
  reset to continue building. Separate bounded native QA then acquired the missing
  observations. On B07, the frozen original model plan had **26/26 targets correct**:
  14 walls, nine roof blocks, two natural-floor requirements and one access block,
  plus native reachable interior/entrance/floor/headroom. Inventory was unchanged,
  health 20. NO additional block placement, removal, crafting, command or manual
  structural correction occurred after B03.

**Stage A: GO for one uninterrupted supplied-material trial.**
**Stage B: CONDITIONAL GO:** actual empty-inventory material→build objective is
independently proven in controlled Peaceful Survival, but autonomous uninterrupted
terminal verification/reliability is not yet demonstrated. The building execution
and the later read-only acceptance are separate facts, not a relabelled original
successful terminal. Current runtime inspection integration is additionally native
qualified, not a second fresh complete building campaign.

Current campaign denominator: A uninterrupted 1/1; B uninterrupted terminal 0/2,
one of those two fresh B worlds ultimately independently confirmed. Intentional
recovery/QA activations are separate, not extra fresh attempts/successes. This small
sample establishes functionality, NOT a general success rate or new-seed reliability.
See [scoped evidence](evidence/persistent-projects.json).
Older [Stage A recovered acceptance and Stage B failures](gateway-building.md)
remain intact. An interrupted/recovered run is never relabelled uninterrupted.
No push, release, upload or production deployment is authorized.
