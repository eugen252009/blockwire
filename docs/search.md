# Targeted `search` — additional read-only perception

`look_around()` remains the inexpensive coarse report. `search(target="logs")`
actually gathers **additional native sight observations**; it does not filter the
same 273 overview rays or walk an automatic resource-search route.

```python
player.search("logs", range=64, cone_degrees=30, timeout_seconds=10.)
player.search("minecraft:oak_log")
```

CLI: `blockwire search logs --range 64 --cone-degrees 30`.
Ordinary MCP and machine MCP expose `search` with these same parameters. The
machine model loop also offers `search` and cached `look_around` as separate
perception tools, never as members of an action composition. Legacy
`search_blocks` is a different, active movement/search skill and is unchanged.

Requires the matching development **Fabric JAR and Python SDK**; restart the owned
client after installation. `observe.search_supported` advertises the new native
operation. No automatic installation, migration, retry or legacy fallback. Private
MCP input policies must explicitly allow the new tool; their historical default
allowlists have not been broadened.

## Scope and cost

- `target`: exact namespaced block ID, or `logs` (oak, spruce, birch, jungle, acacia,
  dark oak, mangrove, cherry and pale oak **unstripped log** IDs). This is not fuzzy
  text matching, leaves/planks, Nether stems, or proof that a tree is natural.
- `range`: integer 1–64 blocks, default64, measured from the current eye along a
  ray. **Not interaction reach** or a player-centered world-map query.
- `cone_degrees`: full 3D cone10–90°, default30°, centered on the current native
  player-eye direction. No central crosshair hit, reticle window or Y slab needed.
- Fixed65×65 perspective grid (4,225 grid cells); cells outside the circular cone
  are skipped. At most128 cells/rays per native request, at most34 pages, and at
  most32 distinct returned target blocks. Python stops when the result cap is hit.
- Timeout0.1–30seconds, default10; cancellation/deadline checks surround each page.
  A running native RPC is not instantly cancellable. It owns no controls and is
  never retried; late results are discarded. One search page may be in flight per
  machine gateway. Ordinary MCP retains its single-read admission bound even
  after a caller deadline/cancellation until that RPC finishes.
- Ray shape queries use the same loaded-only block getter as the overview.
  Missing chunks/window edges are opaque unknown; no chunk loading/generation,
  block-entity enumeration/NBT, inventory inspection or arbitrary query origin.

The page `view_id` binds actor, exact eye/view pose and query parameters. Every
native page requires the actor session; subsequent pages require the original
view ID. Movement, rotation, crouch/eye-height changes or actor replacement can
abort a scan. **Search never freezes or stops another action** to obtain a stable
view. Choose to wait for a settled pose explicitly if needed.

## Result semantics

Matches contain registry ID, block position, observed surface/aim point, face,
eye-to-surface `distance_blocks`, and separately `eye_distance_to_center`.
Distances are in blocks. Results retain native page sample timestamps, view/actor
identity, cells/rays visited, `scan_complete` and `result_limit_reached`.

`targets_observed` / `succeeded` proves only that matching first-hit surfaces were
observed during the scan. It does not prove approachability, interaction reach,
wood collection, safety, or the operator's larger objective. Results are not
ranked into a route, recipe or harvest plan.

`target_not_seen` / `blocked` means **not seen**, never “there is no wood.” The LLM
must choose further camera views or bounded exploration, then observe again.
These actions are separate explicit tools, not an internal search planner.

`scan_complete` means the finite grid was traversed, **not complete visibility**.
Pages are fresh reads, not one atomic world snapshot; blocks may change between
pages. Changed/malformed actor/view/page responses discard accumulated matches.
Timeouts do not turn an incomplete scan into a negative finding.

### Not pixel-perfect visibility

This is denser **geometric outline/fluid raycasting**, not renderer segmentation.
It can discover blocks between the coarse overview rays, but still misses small
exposed patches between its own rays. Glass, leaves and other transparent textures
can geometrically occlude a target despite visible rendered pixels behind them.
Entities, texture alpha/depth and arbitrary modded rendering are not reconstructed.
Accordingly: `partial_visibility=true`, `absence_proven=false`,
`pixel_visibility_verified=false`, `atomic_snapshot=false`. No guarantee that every
rendered log is discoverable.

## Architecture and controls

Java adds only the bounded `search` observation. Python owns page orchestration,
strict validation, deduplication and deadlines. The machine gateway uses a separate
`search` page request outside the action FIFO, with `observe` permission and
persisted request identity. It does not add an action-BCL opcode or second executor.
Interrupt generations invalidate pending page results; transport/actor failures
terminate the bound connection without reconnect/replay. Status/interrupt admission
is independent of waiting for a native page. TLS, authentication, actor fences,
queue bounds, F8 and native input leases remain unchanged.

The standalone machine agent durably reserves **34 search-page operations** before
each requested search against its total operation cap; unused reservations are
not refunded. `reserved_search_pages` is reported separately from
`reserved_action_operations`. Cached `look_around` charges a model decision but
adds no native search-page operations. All exploration decisions remain model-owned.

## Verification scope

- `SearchContractTest`: a log missed by the coarse overview is found by additional
  rays without a central hit; loaded-only/occluded/transparent-fluid fixtures,
  cone/range limits, exact matching, pose/query tokens, caps and strict envelopes.
  Dispatch actor/read-only checks are static source contracts.
- `python/tests/test_search.py`: schemas, page identity/geometry, cancellation,
  ownership, result caps, ordinary MCP deadline/admission and async audit,
  real TLS + simulated native machine MCP, observer permission, concurrent
  interruption, transport failure/no replay and pre-dispatch agent budgets.
- `tests/run_search_mutations.py`: isolated Python/native mutations; working
  sources and historical evidence are not mutated.

The pre-graphical working-tree snapshot (including separate pending campaign work)
passed **827 Python tests**, Gradle `check` and local `build`, **10 TLS interop
checks**, and **25/25 search mutations**. The independently exported commit subset
passes **746 Python tests**, Gradle,10 TLS checks and104 applicable isolated
mutations, including the same25 search mutations. See
[commit-subset checks](evidence/search-commit-checks.json). Regression
mutations: machine14/14, look-around7/7, feedback16/16, gateway14/14, typed tools6/6.
See [source-scoped contract manifest](evidence/search-contracts.json). These counts
are implementation checks, not an extension of historical gameplay qualification.

A subsequent [real-model hidden-client test](search-hidden-test.md) is **SCOPED
PASS**: the exposed fixture log missed by the coarse rays was found, while the
occluded-log and short-range checks correctly returned no sampled match. All102
native pages were independently audited against the closed synthetic fixture.
No production change was needed. This is not natural-world forestry acceptance.

**Ordinary-MCP graphical search, natural Survival exploration, harvesting, general
runtime performance and64-log acceptance remain NOT RUN.** Earlier hidden-display
`look_around` evidence retains its original source/scope; it is not retroactively
relabelled as search acceptance.
