# Bounded extended sight and compact block surfaces

`observe` / Python `Player.observe()` / MCP `describe_surroundings` now return
extended block sight in addition to the original native interaction target.
There is no extra enable switch or background scan: this is an on-demand,
read-only observation. Update the Fabric JAR and restart Minecraft to use it.
Reload MCP after updating the Python server to get its updated tool description.

## What is returned

- `target`: unchanged native crosshair interaction target/reach. It may be absent
  even when a distant chest is visible. Only Minecraft decides interaction reach.
- `sight_target`: first native block-outline/fluid hit along the player-eye forward
  ray, up to **64 blocks**. Includes registry `id`, integer block `position`,
  `aim_position`, `distance` to the hit surface and hit `face`. This is a block
  ray, not a replacement entity/crosshair interaction selection.
- `visible_interactables`: up to **16** potentially visible block targets, ordered
  by surface distance. Same fields plus `kind`: container, workstation, door,
  switch, bed or bell. Individual chest halves are separate block positions.
  These labels describe vanilla block families, not a promise that use will open
  a GUI; reach, server rules, locks and ordinary native behavior still apply.
- `visible_blocks`: compact, losslessly encoded **observed first-hit positions**,
  not a world map. Only block registry IDs are serialized; no state/NBT dump.
- `visibility`: profile `sampled_surfaces_v1`, range, sample ray count, approximate
  view parameters, candidate counters, explicit limit/truncation flags, and
  `partial: true`.

The readable `text` names the extended forward hit and reported interactables so
an LLM does not have to infer them from the block encoding. Closed-container
contents, custom container names, sign text and other block-entity values are
never inspected or returned by this observation. Ordinary `inventory` still
requires a genuinely open native container before exposing its slots.

## Compact encoding

`visible_blocks.encoding` is `palette_x_runs_v1`:

```json
{
  "encoding": "palette_x_runs_v1",
  "origin": [100, 65, -20],
  "palette": ["minecraft:prismarine", "minecraft:chest"],
  "runs": [[0, -2, -2, 3, 4], [1, 1, -1, 6, 1]],
  "observed_blocks": 5
}
```

`origin` is the floored world-coordinate player eye position. Every run is
`[palette_index, dx, dy, dz, length_along_positive_x]`. The example contains four
prismarine blocks at X 98–101, Y 63, Z -17 and one chest at [101,64,-14].

Only consecutive actually observed blocks of the same ID and Y/Z merge into a
run. Unknown gaps are never filled. Decode with integer addition and palette
lookup; no evaluation/executable codec is involved. The encoding discards no
observed position/type, but the observation itself is deliberately sparse:
**omitted cells are unknown, NOT air, passable space or proof of absence**.
Do not plan movement from this surface sample; use the native collision mesh and
its supported-motion contracts instead.

## Visibility construction and work bounds

All work runs on the client thread, for the currently connected player/world:

1. Cast a fixed **21 × 13** perspective grid (273 rays) through native outline
   shapes/fluid surfaces, up to 64 blocks. The approximate grid spans 100 degrees
   horizontally and 70 vertically around the player's eye/view direction.
2. Within a fixed **9 × 9 already-loaded chunk window**, visit at most **2048
   block-entity position keys** (near chunks first). Never read map values, block
   entities, their contents, custom names or NBT. No arbitrary position/filter/
   radius request is added. Non-block-entity interactables such as doors and
   crafting tables are found only if a surface sample hits them.
3. Filter candidate centers to distance ≤64 and a fixed 120-degree view cone,
   retaining at most the nearest 64 candidates from those visited. Test up to
   three vertical aim points per candidate with native outline/fluid rays; only
   report it when the first hit is that candidate's block position.
4. Publish at most 16 interactables. The compact block set contains at most
   **337** distinct sampled/candidate-verified positions (273 + 64).

`candidate_positions_visited` and `candidate_sight_tests` count metadata visits
and tested candidates, not all native shape/state lookups. Shape-ray traversal
and mod-provided shape callbacks have a cost; these finite work bounds are not a
hard wall-clock performance guarantee. No per-tick scan/cache/global map is added.

Chunk lookups explicitly use `getChunk(..., false)`. All native shape queries use
a loaded-only block getter: missing chunks/window edges are opaque unknown, not
air. A ray cannot see through an unloaded gap to a loaded chest behind it. The
block getter deliberately supplies no block entities, including to shape code.
No server chunk requests or world generation are introduced.

## Deliberate limitations

This is **potential visibility**, not the actual renderer/frustum/pixel result.
The player eye is the origin even in third-person view. Camera FOV, fog, darkness,
textures, entity occlusion and other mods are not reproduced. Glass and fluids
conservatively occlude rays; an object visible through them to a human may be
omitted. Partial shapes and off-center objects can also be missed. Chest discovery
is stronger than uniform sampling because known block-entity positions get
explicit sight tests, but remains incomplete under view/budget/occlusion limits.
Block families outside the classifier can still appear in compact surfaces but
are not advertised as interactables. No resource search, arbitrary coordinates,
server scanning, hidden-container contents or increased action reach is exposed.

To put an item in a detected chest: observe its target, approach within native
reach on supported terrain, use `look_at` on its reported `aim_position`, refresh
the native `target`, then request ordinary `use`. Inspect the newly opened menu
and use fresh menu/state/slot identifiers. Refresh inventory to confirm transfer;
an input receipt is never proof that an item moved. This change does not add an
automatic chest-transfer planner or perform any action by itself.

## Contracts and qualification

`VisibilityContractTest` uses actual Minecraft outline/fluid ray code with
bounded deterministic block fixtures, not a graphical world:

| Contract | Coverage |
|---|---|
| VIS01 | Distant chest and independent extended forward ray |
| VIS02 | Output fields and no block-entity value access |
| VIS03 | Stone/glass/fluid occlusion |
| VIS04 | Unknown chunks block sight and are never queried |
| VIS05 | Range/cone and off-center candidates |
| VIS06 | Ray/candidate/target/response caps and truncation |
| VIS07 | Lossless palette runs, negatives, gaps, type changes, empty and seeded generated fixtures |
| VIS08 | Interactable classification without inventing interactions |

`./gradlew check` includes `visibilityContractTest`. The Python SDK contract
checks unchanged one-request dispatch and preservation of the new structured
fields. `tests/run_mutations.py` includes six targeted visibility mutations:
occlusion bypass, transparent unknown terrain, range bypass, compression across
unknown gaps, metadata cap bypass and target cap bypass. Existing TLS, transport,
actor and skill checks remain applicable. New local logs go under
`build/visibility-verification/`; historical evidence manifests are not rewritten.
Current artifact/source/log hashes and commands: [evidence/visibility.json](evidence/visibility.json).

Executed development checks: Gradle build/check PASS, 44 Python unit tests PASS,
9 artifact packaging contracts PASS, 10 real TLS interoperability checks PASS,
and 14 Java + 11 Python skill mutations KILLED (six Java mutations specifically
exercise visibility). Native visibility fixtures executed 6027 assertions,
including seeded codec round trips; this is not a count of independent gameplay
scenarios or a proof of visibility completeness. The first target-cap mutation
exposed a weak occluding-wall fixture; a separated visible arc now exercises more
than 16 independently visible targets and detects that mutation.

**Graphical Minecraft acceptance with this new JAR: NOT RUN.** Native fixture
rays and mocked protocol tests do not establish real-client chest discovery,
modpack compatibility or performance. No user world, inventory, credentials,
installed JAR or running client was changed as part of implementing this feature.
