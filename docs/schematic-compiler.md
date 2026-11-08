# Litematica compiler: grounded Creative specification, v1

**First compiler stage only — not yet an executable building bot.**
`COMPILED_PLAN_ONLY`, `execution_ready: false`, Minecraft acceptance **NOT RUN**.
The compiler does not connect to Minecraft, select a world or resume a prior run.

The intended builder walks and, where safe, makes ordinary native jumps or uses
explicit temporary scaffolding. **No flight, teleport, `/setblock`, `/fill`,
`/give`, Litematica paste or direct world writes.** Creative is solely the native
material source: no resource gathering and no Survival-style consumption checks.
The existing paused Survival benchmark remains a separate, unstarted scope.

## Use

From the repository, with no Minecraft configuration or connection:

```sh
PYTHONPATH=python/src .venv/bin/python -m blockwire.schematic inspect \
  'schemas/starter house.litematic'

PYTHONPATH=python/src .venv/bin/python -m blockwire.schematic compile \
  'schemas/starter house.litematic' \
  --origin 0 64 0 --output build/litematic/my-new-plan
```

After installing the updated Python package, `blockwire-schematic` is the same
entry point. `inspect` computes bounds/counts and lists unsupported states.
`compile` rejects unsupported content before creating output. There is deliberately
**no `run` subcommand**, generated Python execution, fabricated BCL or command file.

`--origin X Y Z` translates the **minimum occupied corner**, excluding empty
selection padding. It defaults to `(0,0,0)` for offline inspection; it does not
mean a safe building site, the player's position or the selection's original
corner. No rotation/mirroring is implemented. A later runner must check actual
world/dimension build-height limits and the explicitly selected actor/site.

The output directory must **not exist**, including empty directories and symlinks.
Its parent must exist. The compiler writes private 0700/0600 artifacts:

- `plan.json`: exact target states, placement groups, layers, potential supports,
  verification requirements, no-flight/no-cheat policy and execution blockers.
- `materials.json`: placement-item counts, not required Creative stack sizes.
- `README.txt`: the non-executable status and missing execution components.
- `manifest.json`: source digest and output hashes/sizes, written last.

An interrupted export is retained and cannot be resumed/overwritten. Source files
are never edited; labels/descriptions/authors are never used as instructions or
output paths. Compile success does **not** prove buildability, native reach,
collision safety, valid routes or a completed structure.

## Import contract

The bounded importer is `python/src/blockwire/litematic.py`; it does not import
privileged save readers from `tests/building/`.

- One gzip NBT member, Litematica versions **6 or 7**, absent/zero SubVersion.
  Minecraft data version is retained, not upgraded or silently remapped.
- Big-endian signed long arrays; `max(2, ceil(log2(palette_size)))` bits per cell,
  **contiguous** bit packing across long boundaries, X fastest, then Z, then Y.
  This is not modern Anvil's padded block-state storage.
- Negative region sizes use the minimum region corner; they do not reverse the
  palette stream. Nonoverlapping regions retain their relative offsets.
- Air is omitted from placement and **never interpreted as authorization to clear
  the world**. Overlapping region volumes are rejected even where one is air.
- Entities, block entities and pending block/fluid ticks must be empty; unknown
  region payload fields are rejected. No chest contents, signs, command NBT,
  scheduled simulation or executable source is silently imported.
- Bounds: 8 MiB compressed, 32 MiB decompressed, one million NBT node/array-entry
  budget, depth32,32regions,64blocks per dimension/enclosing span,262144selected
  cells,8192non-air blocks and4096palette entries per region.
- Invalid lengths, duplicate compound keys, malformed strings/nonfinite numbers,
  truncated streams, trailing gzip/NBT data and invalid palette indices fail closed.
  Modified UTF-8 labels are parsed as data. Metadata counts are not trusted.

## v1 block-state coverage

The compiler accepts a deliberately small exact vanilla catalogue:

- stone, cobblestone, stone bricks, dirt, oak planks;
- nonsnowy grass blocks;
- oak logs/wood with X/Y/Z axis;
- dry oak stairs with facing, half and all five shapes;
- dry glass panes with all four connection flags;
- unpowered spruce doors with facing, hinge, open/closed and paired halves.

Every property is retained. Missing, extra or unsupported properties/blocks are
reported by inspection and reject the entire compilation, never substituted or
partially dropped. Waterlogged/powered states are not silently approximated.
This catalogue describes **desired states**, not qualified placement motors.

Door halves must agree on position/orientation/hinge/open/power. A lower half is
one placement/item; its upper half is a separate verification target belonging to
the same placement group. Open doors still require a real native interaction;
the desired `open` value is not permission to write block state directly.

Stair shape and pane connections require a verification after neighboring blocks
are complete. Initial placement verification alone cannot certify them. Supports
listed from the blueprint are explicitly `observed: false`: they might not yet
exist in Minecraft, and can depend on another placement in the same layer. Axis
logs constrain the clicked support face. A missing blueprint support is a need
for fresh world support or an explicitly planned temporary scaffold, **not a
license to place a floating block**.

Bottom-up layers are work groups, **not a runnable operation order**. The compiler
does not invent standing poses, fly to an unreachable block, assume unspecified
air is traversable, or assert that a scaffold is available/cleaned up.

## Supplied starter-house inspection

The supplied local schematic was decoded and compiled offline:

- Selection32×16×32; actual occupied area **14×10×14**.
- **658 target block states**, **656 placement operations**, two upper-door
  verification targets;163neighbor-dependent targets (149stairs,14panes).
- Materials:136oak logs,54oak wood,92oak planks,149oak stairs,125stone bricks,
  84grass blocks,14glass panes and2spruce doors.
- All source target coordinates and properties were compared against an
  independently decoded palette stream, not only the schematic's metadata.

The private preview is `build/litematic/starter-house-001/`, origin `(0,0,0)`.
It is **not** a selected build site or gameplay evidence. The schematic itself,
worlds and generated private plans are not added to a distributable.

## Still required for a real grounded build

1. Native Creative material selection and placement verification without assuming
   item consumption. No `/give`, direct stack mutation or Survival guard bypass.
2. Native exact-state observation/placement for axes, stair facing/halves/shapes,
   pane connections and door halves/hinges/open state. Current ordinary visibility
   exposes IDs rather than full block-state properties.
3. Python planning from fresh bounded native geometry: reachable grounded work
   poses, ordinary walking/jumps, bounded scaffolding and a supported way back.
   No Minecraft-side planner, flight-toggle sequence or hidden-coordinate reads.
4. Owned-scaffold removal, fresh final block-state/air/access verification,
   actor/world fencing, durable no-replay execution, cancellation and input cleanup.

The existing `place_block`/`place_at` BCL motors deliberately require their current
supported items/geometry and observed consumption. The compiler does **not** weaken
those contracts or pretend its JSON can already be passed to that executor.
No new MCP tool, Java operation, transport authority or automatic builder is added.

Contract fixtures and mutation checks are offline compiler tests, **not native
Creative, navigation, scaffolding or construction acceptance**. The matching
[evidence manifest](evidence/schematic-compiler.json) records this boundary.
