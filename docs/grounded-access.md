# Grounded builder: observed return routes and scaffold teardown

Follow-up to `grounded-builder.md`, not a replacement for its historical evidence.
The executor remains **experimental; graphical acceptance is NOT RUN**. No house
was built, no game was launched, and the separate Survival benchmark was not
resumed. `evidence/grounded-access.json` records this source scope and its checks.

## What changed

Python goal planning now retains a bounded history of explicitly requested native
navigation meshes (`python/src/blockwire/skills/build_access.py`). It does not
query arbitrary coordinates, scan saves, load chunks, infer air from omissions,
use desired blueprint cells as observations, or synthesize native geometry.
There are no new Java/transport/MCP/BCL changes in this follow-up. The ordinary
walking motor, native physics, actor fences, no-flight input guards, F8 and TLS
boundary remain in force. This helper is not a new registered skill or planner
inside MCP; the existing operator-local `blockwire-build` entry remains explicit.

* Only hazard-free native nodes and typed flat, diagonal or one-block step edges
  enter the history. Gap edges remain excluded. Actor, actual pose/current-cell
  correspondence, indices, coordinates and budgets are checked.
* A newly sampled footprint replaces previous knowledge there. Missing/hazardous
  cells invalidate old paths; missing does **not** mean air. Cross-window edges
  can remain **historical**, explicitly not fresh. They must be sampled again
  before the adjacent waypoint is sent to the walking motor.
* Placement/removal projections only **subtract** known nodes and edges. They
  account for standing headroom, full supporting floors, both diagonal corner
  floors and the existing native step/jump clearance envelope. Removing a block
  never predicts a newly usable lower landing. Only a subsequent native mesh can
  add that landing or a newly opened passage.
* The dependency envelope is restricted to an ordinary upright player. Existing
  actor-fenced motion telemetry must show grounded, non-sneaking, pose-consistent
  bounds: positive width/depth at most 0.7 blocks and height 1.75–1.85 blocks.
  Scaled/crawling or otherwise unsupported geometry stops rather than borrowing
  the standard envelope. Body and mesh reads are sequential, not atomic.
* The initial return cell must already be within 0.15 blocks of its center, and
  its standing/head cells must be outside all desired target voxels. No automatic
  relocation or new build-site authorization is inferred from these checks.

## World changes and return plans

Before a placement, a door toggle, or scaffold removal, the builder refreshes the
local mesh and records a return plan that survives the proposed subtraction.
Both door halves participate in the projection. Inventory selection, camera
preparation and candidate exploration are not gameplay outcomes. If no eligible
stance has an observed return path, no corresponding world action is dispatched.

The journal's `retreat_plan` contains `observed_build_retreat_v1`, the actor,
proposed change, path, observation-frame references and `all_in_latest_mesh`.
Its claim is **`observed_route_history_requires_fresh_each_edge`**, with
`traversed:false`: a planning record is not evidence of traversing that route.
Frame references describe the in-memory observation history; these records are
not a complete independent capture of all native mesh responses.

Walking is broken into adjacent waypoints. Before each motor invocation its
edge must be present in the current mesh; the motor retains its own native
observations, collision handling, cancellation and local replanning. A missing
route stops instead of using an old edge, inventing a jump or reconnecting.
All legs of one approach share a single child deadline of at most 30 seconds,
inside the unchanged overall build deadline. Every look/drive retains the actor
session and grounded-Creative guard.

Distant parts of a return plan may be old. A world change or another actor can
invalidate them before traversal. This is a conservative planning aid, **not a
promise of an escape route, an atomic world snapshot, immunity or a complete
construction schedule**. No cleanup, rescue or building continues after cancel.

## Temporary cobblestone

Scaffold authorization, air-before-placement, fresh native full-floor evidence,
placement ownership, material/count and observed-effect requirements are retained.
A temporary block cannot be the required floor under a desired permanent door.

Observed scaffold placements record dependencies on already owned clicked
supports and floors. Teardown prefers higher blocks but must remove dependent
children before their parents. It selects a stance whose projected return path
does not depend on the block being removed. An adjacent stance above the block
is permitted; standing on the block being removed is not. The native own-support
and unchanged-owned-cobblestone checks remain authoritative.

Ownership/state and the return plan are checked **again after approach/aim**,
before the removal request. Air still needs two later distinct native ticks;
a break receipt alone is insufficient. Removal cannot use a predicted lower
floor as an escape route. The next native snapshot may observe such a floor.

Bookkeeping for verified placement/removal happens before any further
cancellable read or graph operation. A cancellation immediately after effect
verification therefore does not lose a known scaffold or a confirmed removal.
The pending-effect latch stays set until that bookkeeping is committed: a hard
library interrupt between verification and accounting retains uncertainty.
Uncertain effects still retain `unknown_no_retry` and potentially incomplete
scaffold inventory. Existing ledgers cannot resume.

## Bounds and remaining limits

History is limited to 8,192 nodes and 32,768 edges; a native frame to 405 cells
and 4,096 edge/transition entries; a planned route to 512 edges. Cancellation and
deadline checks also occur inside graph work. Existing work-area, 64-block,
preparation, scaffold, RPC and 32-MiB audit limits remain. Extra observations can
exhaust those limits; they do not grant a larger run envelope.

The heuristic is still incomplete. In particular, it does not establish that
all 658 house states can be reached, that all scaffolds will be removable, or
that the actor can always return after external changes. It does not clear
source-air interiors, replace occupied blocks, support arbitrary partial-shape
floors, or certify server/save state. Conservative stopping can leave scaffolds
or a partial structure. Final exact-state, scaffold-air, grounded-return and
input-release checks remain required for success.

Tests use independent graph inputs and the earlier small voxel fixture with
**mocked walking, Creative GUI and placement**. Injected ownership in bridge
teardown cases is not an actual construction trace. They test rejection,
bookkeeping and scheduling contracts, not Minecraft physics, GUI behavior,
flight avoidance, a complete house, performance or real return safety. The
mutation runner rejects compilation/import/runtime errors as mutation kills.
A fresh explicitly authorized isolated graphical scope is still required.
