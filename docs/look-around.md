# `look_around` — bounded reticle report

```python
report = player.look_around()
blocks = report['details'].get('blocks', [])
# Each row: id, position (voxel), center, distance_blocks, angle_degrees, sources.
```

CLI: `blockwire look_around`. MCP: `look_around()`; the ordinary skill registry
also exposes `run_skill('look_around', {})` and the typed skill tool.
Restart the relevant Python MCP process to discover the new tool.

## Geometry and authority

- Fixed **30° total three-dimensional cone**, ±15° about current yaw/pitch.
  This is not a 30° camera rotation or a 360° sweep.
- Fixed **10×10 continuous horizontal X/Z window**, ±5 blocks around the
  native sampled forward ray's `aim_position`. Boundary points are included.
  This is not a ten-block radius, cube, or distance limit from the player.
- Both filters apply to observed block **centres**; centre filtering is an
  approximation and can exclude an edge-hit block. No additional Y slab.
- Distances are Euclidean eye-to-centre distances in blocks, rounded to 0.001.
  They are not exact visible surface distances, reach checks or route proofs.
- Uses only the existing bounded first-hit surface samples and sight-tested
  interactables, deduplicated by voxel. Missing cells remain unknown, not air.
  Sampling is partial, not exact renderer/pixel visibility or exhaustive coverage.
- Without a sampled forward block hit, returns `crosshair_anchor_not_observed`;
  no world-space reticle point is invented and no cached renderer hit is used.
- Entities are explicitly unsupported: the existing scene entity rows lack
  positions needed for this cone/window filter. No wider entity list is passed
  off as matching this smaller region.

## Freshness and controls

Ordinary Python/CLI/MCP uses one `observe` call with cancellation/deadline checks.
It neither claims nor releases input ownership and performs no camera/input action.
`machine-v1` MCP instead filters its latest independently delivered scene event:
`cached: true`, source event/metadata and original sample time are retained. It
makes no native RPC, drains no events, adds no action or BCL observation opcode,
and rejects failed streams/actor mismatches. Old samples do not become fresh.
No target selection, resource strategy, hidden terrain query or transport change.

## Verification

Deterministic geometry, bounds, cancellation, ownership, CLI and both MCP paths
are covered in `python/tests/test_look_around.py`; isolated mutations are in
`tests/run_look_around_mutations.py`. Simulated tests are not gameplay acceptance.
The [real-model hidden-display test](look-around-hidden-test.md) now has scoped
native PASS for missing-anchor and positive block/distance reports over machine
MCP. The intervening invalid-argument/unknown-cleanup case remains recorded.
Fresh-query ordinary-MCP graphical acceptance and broader views remain **NOT RUN**.
