# Estimate distance without X-ray

`estimate_distance` is a **read-only Python skill**, not a new world-query RPC or
movement planner. It performs one ordinary bounded `observe` and computes geometry
from that response only. No Java/transport change or Minecraft JAR update is needed.
Reload the Python/MCP host to expose the new skill/convenience tool.

```python
with Bridge.from_env() as bridge:
    player = Player(bridge)
    result = player.estimate_distance("minecraft:grass_block")
    print(result["details"])
```

```sh
blockwire estimate_distance grass_block
# Select a position ONLY if it is already observed in the current view:
blockwire estimate_distance dirt --position 12 64 -8
```

MCP: `estimate_distance(target="minecraft:grass_block")`, or the registered
`run_skill("estimate_distance", {"target": "minecraft:grass_block"})`.
The direct convenience tool is read-only and can run while another goal owns the
actor. It never stops inputs or claims movement ownership. Measurement success
means an observed block was measured, **not successful navigation or survival**.

## Parameters and target selection

- `target`: exact block registry ID. `dirt` means `minecraft:dirt`, not grass,
  a translated item name or all soil blocks. Initial support is blocks, not entities.
- `position`: optional strict three-integer block position within normal world
  bounds. This filters the same current observation **in Python**; it never sends
  a coordinate query to the mod or forces a hidden lookup.
- `timeout_seconds`: usual cooperative .1–120-second budget, default 30.

Choose the nearest matching **block center to the player eye**, breaking ties by
block position. Multiple observed positions of the same ID may match; an optional
position selects exactly one. Unobserved positions are not extrapolated from
nearby samples, filled gaps, old sightings or known world-generation patterns.

Sources are exclusively the current `visible_blocks` compact first-hit samples,
fresh on-demand `sight_target`, and sight-tested `visible_interactables`. The
cached renderer `target` is deliberately not accepted by itself, since it can be
stale. No camera scan, aim, movement, chunk loading, save/NBT read, block-entity
contents, global resource search or remembered world map is involved.

The existing [visibility](visibility.md) budget is unchanged. Decode at most 337
sampled positions plus up to 16 interactables and a fresh forward hit. Malformed,
conflicting or over-budget observations fail closed. This inherits the native
observation's **partial, approximate potential visibility**, not pixel-perfect
renderer visibility. Detection never extends interaction reach.

## Output and unknown results

A successful result includes the selected block ID/position and source names,
matching observed count, actor/session/sample metadata, plus:

- `eye_distance_blocks`: Euclidean distance from the eye to the block center.
- `feet_distance_blocks`: Euclidean distance from feet to that center.
- `horizontal_distance_blocks`: horizontal center distance, without vertical motion.
- `vertical_delta_from_feet_blocks`: block-center Y minus feet Y; negative is below.
- `reference: observed_block_center`: compact samples do not provide exact surface
  hit points. These are **not** claimed as exact distances to an exposed top face.

No match returns `blocked/target_not_observed` with `visibility: unknown`, null
distance and unknown landing safety. "Not observed" does **not** mean
that a block is absent, that the space is air, or that a fall corridor is clear.

## Risk assessment belongs to the caller

The helper reports geometry and observation limits only. **It does not calculate
fall damage, remaining health, lethality, survival probability or an assumed drop
to a block's top.** This applies equally to Python, CLI and MCP output, for all
block types and regardless of player health.

Risk reasoning belongs to the calling agent/planner and its human-readable report,
not the measurement tool. A visible side does not establish that the top is
exposed, reachable, safe, free of entities or the first landing surface. Distances
to block centers are not verified fall heights. Unknown information must remain
unknown, rather than being turned into a jump authorization.

Successful measurements retain only explicit observation limits:

- `landing_safety: unknown`
- `clear_vertical_path: unknown`
- `target_top_observed: unknown`

No `fall_estimate`, damage, health prediction or `safe_to_fall` field is emitted.
The helper never recommends jumping, bypasses terrain guards or executes a fall.

## Checks and scope

`python/tests/test_distance.py` covers geometry/reference points, exact IDs and
position filters, sparse gaps, cached-hit rejection, fresh-source selection,
horizontal/vertical separation, health-independent geometry, absence of damage/survival predictions,
strict validation, bounds/conflicts, cancellation/deadline, read-only ownership,
Python/CLI and MCP strict/read-only dispatch. Fixtures are not fall acceptance.

An isolated graphical-client read-only trial measured a currently sampled dark
oak log (~1.446 eye-to-center blocks) and grass block (~1.890), and returned unknown
for unobserved diamond ore at `[0,0,0]`. Audited native requests were exactly three
`observe` calls, **without coordinates or controls**. The trial did not unpause,
move, mine, stop inputs or test an actual fall. See
[historical evidence](evidence/estimate-distance-live.json). That initial record
included a subsequently removed hypothetical fall model; it is retained unchanged.
The current helper exposes geometry only. A subsequent read-only live check
confirmed a visible grass-block measurement and an unknown diamond-ore result,
with exactly two native `observe` requests and no damage/survival prediction fields.
Its raw record is `build/estimate-distance-verification/geometry-only-live.json`.
Landing/survival safety is **NOT ESTABLISHED** by a distance measurement.
