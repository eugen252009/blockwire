# Play2Code — passive human-play recording

Play2Code records ordinary local Minecraft play and exports a raw event timeline
plus conservative BCL/1 source batches. It is a **recorder and translator**, not a
controller, macro player, optimizer, planner, or new BCL runtime.

## Authority boundary

```
local keyboard/mouse → vanilla Minecraft input/physics/world updates
                           │
                           └→ passive Play2Code observations → private raw JSONL
                                                                  │
                                              explicit host export │
                                                                  ▼
                                      existing BCL registry/compiler → .bcl batches
```

The native recorder never sets a key, changes the camera, selects a hotbar slot,
invokes attack/use, sends a packet, or changes a block. Minecraft continues to own
movement, collision, placement, mining, inventory, and server acknowledgement.
The exporter never executes generated source. Replay, if separately authorized,
uses the existing BCL/1 compiler, runtime, skills, actor fences, input leases,
cancellation, postconditions, TLS transport, and F8 stop path.

There is no Play2Code wire RPC, MCP tool, skill, hidden generator, second movement
controller, or new opcode. The authenticated native protocol is unchanged.

## Local operations

Play2Code is intentionally local so a remote controller cannot manufacture a
“human” baseline.

1. **Start — F9** (remappable under Blockwire controls): requires live,
   unpaused, non-spectator gameplay with no screen open and the Blockwire control
   endpoint disabled.
2. **Stop — F10**: stops accepting new interaction intents, then keeps a bounded
   20-tick observation window so the last placement/mining result can become a
   stable observed mutation. The capture is then sealed.
3. **Export — host CLI**:

   ```sh
   blockwire-play2code inspect /path/to/minecraft/recordings/<id>
   blockwire-play2code export /path/to/minecraft/recordings/<id>
   # Or copy into another private root:
   blockwire-play2code export /path/to/capture --output-root recordings
   ```

F8 keeps its existing endpoint/input-release behavior. Starting the endpoint while
a recording is active invalidates and stops that recording **before** the endpoint
is started. A recording also fails closed on a nonempty remote-owned input set,
player/world replacement, death, client shutdown, write failure, or bounds.
Auto-started control must therefore be disabled with F8 before F9.

## What is recorded

The client writes an append-only private timeline at
`<minecraft-game-dir>/recordings/<id>/raw-timeline.jsonl`, plus `capture.json`.
On POSIX, directories are mode 0700 and files 0600.

The raw timeline contains:

- one end-of-client-tick sample per recorded tick: absolute/relative feet position,
  block cell, velocity, yaw/pitch, ground/sprint/sneak state, health, selected
  hotbar slot, main/off-hand summaries, and actual movement/attack/use key state;
- discrete hotbar-selection changes;
- native `startDestroyBlock` and `useItemOn` intents with crosshair block/face,
  hand, held item, player pose, and bounded candidate positions;
- a confirmed placement only when the expected block differs from the pre-action
  state and remains observed for at least three end ticks;
- a confirmed break only when the target differs from its pre-action state, is
  observed as air, and remains stable for at least three end ticks;
- explicit unconfirmed/unsupported interactions and a terminal recording event.

This is **client-observed stable state**, not server-authoritative proof. A later
server correction remains possible. No drop collection, damage avoidance, or
external objective is inferred. Only positions directly correlated with native
human interaction intents are watched; there is no background world scan.

Bounds are 216,000 ticks (three nominal hours), 300,000 events, 256 MiB total raw
timeline, and 128 KiB per event line. A bound stops the capture instead of silently
dropping history.

## Coordinate contract

Every relevant raw event retains both forms:

- `*_absolute`: native world coordinates. Player positions are feet coordinates;
  block positions are integer voxels.
- `*_relative`: player deltas use the exact start position; block deltas use the
  floored start block position.

Generated BCL always declares `S1 absolute`; it never relies on ambient relative
modal state. The manifest repeats both origins and this contract.

## Conservative BCL mapping

Export uses `default_commands()` and `compile_bcl()` from the installed Blockwire
package. It does not copy an opcode table or add a BCL feature.

| Recorded evidence | Existing BCL output |
|---|---|
| changed grounded tick with active or just-released movement input | ordered `M0 X Y Z F` checkpoint |
| required recorded held item for a mapped mutation | `I1 I=...` |
| stable main-hand placement of a registry-supported block | exact `I4 B=... P=[x,y,z] C=false` |
| stable break-to-air of a registry-supported removable block | exact `C3 B=... P=[x,y,z] D=false` |

Every eligible grounded movement tick is retained; paths are not smoothed and
waypoints/actions are not optimized. `M0` is still a goal through the existing
walker, not raw W/A/S/D timing replay. `C=false` prevents the generated placement
from adding an unrecorded plant-clearing attack. C3 claims removal only, never a
drop. Unsupported registry values are rejected by the real compiler and listed in
`conversion.json`; they are never approximated.

BCL/1 permits at most 32 operations per source. Export therefore creates ordered
`bcl/0001.bcl`, `0002.bcl`, ... batches. Each starts with:

```bcl
BCL/1
S0 sync
S1 absolute
S3 stop
```

The remaining 29 slots retain source order. Every batch is compiled during export;
its source SHA-256, registry digest, program digest, and operation counts are in the
manifest.

The following remain raw evidence with explicit unsupported-conversion records or
limitations: airborne/jump arcs, exact key durations, yaw/pitch/mouse trajectory,
backward/strafe semantics, exact hotbar slot identity, off-hand placement,
unconfirmed use/attack, unsupported blocks/items, and motion without recorded local
movement input. No optimistic command is invented for them.

## Export layout

After export, `recordings/<id>/` contains:

```text
capture.json              native sealed-capture metadata
raw-timeline.jsonl        unchanged raw event timeline
conversion.json           event→BCL mapping and unsupported conversions
bcl/0001.bcl ...          ordered, unoptimized, compiling BCL/1 batches
manifest.json             timing, coordinates, counts, compiler checks, hashes
manifest.sha256           hash of manifest.json
```

`manifest.json` hashes every raw/conversion/BCL artifact. It explicitly records
`replay.attempted=false`, `qualified=false`, and `status=NOT_RUN`. Compilation is
not replay evidence, a gameplay receipt, or objective acceptance.

Recordings contain player UUIDs and exact world locations. `recordings/` is ignored
by Git and the allowlisted bundle builder does not include runtime game directories.
Keep raw captures private unless they are explicitly reviewed and redacted.

## Replay protocol

A replay is a new measured run, never a continuation of the human world:

1. seal and hash the human capture;
2. restore a fresh independently verified fixture snapshot;
3. bind a fresh actor/session and use the ordinary authenticated BCL stack;
4. execute batches in order without editing generated source;
5. preserve every compiler/runtime failure and uncertain outcome;
6. run independent native and closed-world acceptance after the final action.

A successful BCL program still proves only its operation postconditions. The
external objective needs its own independent verifier.

## Native implementation smoke — PASS; replay NOT RUN

A private isolated graphical-client smoke exercised the actual F8/F9/F10 path and
PID/cwd-verified automated local window input. With the endpoint disabled, the recorder
captured 515 native ticks, movement, one stably observed cobblestone placement,
one stably observed break-to-air, and one deliberately retained unconfirmed
follow-on mining intent. Offline export preserved the raw timeline byte-for-byte
and compiled one ordered BCL batch containing 17 generated payload operations,
including 13 unsmoothed movement checkpoints. No remote-controller interference
was present. The client was closed normally and the frozen fixture was restored to
its original identity afterward.

This smoke validates native capture and conservative compilation only. Generated
BCL was not executed, no external building objective was attempted, and replay
status remains `NOT_RUN`. It is not a human baseline or benchmark result.

Final deterministic verification passed the Gradle build/check, 478 Python tests,
20 Play2Code Java contract checks, all 51 native mutations (including the five
Play2Code native mutations), all 14 exporter mutations, packaged CLI loading, and
the allowlisted bundle audit. The public-safe, coordinate-free summary is retained
in [the Play2Code evidence record](evidence/play2code.json); raw capture and world
data remain private.

## Manual 71-block Superflat benchmark — PENDING

The owner-only benchmark uses the existing frozen `superflat_house_5x5` objective:
46 wall blocks plus a 25-block roof, 71 required cobblestone voxels, clear entrance
and interior, intact floor, no helpers, native interior access, and a safe player.
The canonical snapshot identity remains
`d61d166e4431e7693907cc0590f1808e2d8f12d62befe3b0a5a64c22b70696a7`.

Prepare metadata only:

```sh
.venv/bin/python tools/play2code_benchmark.py describe --run-id H01
.venv/bin/python tools/play2code_benchmark.py prepare --run-id H01
```

The prepared status is `PENDING_OWNER_MANUAL_BUILD`. The tool does **not** restore
or load Minecraft, record input, build any block, generate a baseline, replay BCL,
or run acceptance. The owner must restore the canonical snapshot, disable the
endpoint, press F9, manually build the complete house with ordinary input, press
F10, and export the resulting capture. Test-A source, model output, commands,
teleportation, creative/admin rescue, and hidden/manual artifact generation are
forbidden as substitutes for the human baseline.

No human house recording or replay has been performed in this implementation
work. Benchmark capability and replay correctness therefore remain **PENDING**.
