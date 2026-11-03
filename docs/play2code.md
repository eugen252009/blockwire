# Play2Code — passive human-play recording

Play2Code records ordinary local Minecraft play and exports a raw event timeline
plus conservative BCL/1 source batches. It is a **recorder and translator**, not a
controller, macro player, optimizer, planner, or new BCL runtime.

The [M0/I3 pose-handoff recovery](pose-handoff.md) restores the existing H04
standard replay without changing its recording, BCL or transformations. Frozen
S05 passes 9/9 (four identities plus the established spatial variants); native
movement regression passes 211/211. Reuse remains default-off and unqualified for
activation. Historical failed cohorts and H05's owner-manual pending status remain.

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
   # Portable capture-relative source for H01 or another explicitly selected run:
   blockwire-play2code export /path/to/capture --output-root recordings \
     --coordinate-mode relative --benchmark superflat_house_5x5
   # Explicit derived translation (three strict integers):
   blockwire-play2code export /path/to/capture --output-root translated \
     --coordinate-mode relative --translate -2 0 -4
   # Explicit horizontal block-lattice reflection:
   blockwire-play2code export /path/to/capture --output-root mirrored \
     --coordinate-mode relative --mirror-axis z --mirror-coordinate 0
   # Exact positive-Minecraft-yaw quarter turn around an explicit anchor voxel:
   blockwire-play2code export /path/to/capture --output-root rotated \
     --coordinate-mode relative --rotation 90 --rotation-anchor 0 0
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

The default export remains self-contained `S1 absolute`. An explicit
`--coordinate-mode relative` export instead derives point values from the exact
capture start and voxel values from its floored block origin. Its first batch
executes exactly one `S1 relative`; continuation batches omit S1 and therefore
must run in order in the same persisted BCL session without reset or re-homing.
Every relative field is checked against the corresponding absolute field and
capture origin before publication. The manifest repeats both origins, selected
mode and continuation requirement.

### Explicit offline coordinate derivation

Export can derive a separate program with one strict integer XYZ translation,
optionally one reflection across an X- or Z-axis block lattice coordinate, and an
exact 0°/90°/180°/270° horizontal rotation. For reflection coordinate `C`, voxel
`v` maps to `2*C-v`; continuous points reflect about `C+0.5`. A nonzero rotation
requires an explicit anchor voxel `(Aₓ,A𝓏)`. Voxels rotate around that lattice
coordinate while continuous feet, pose, view-target and hit points rotate about
the matching block centre `(Aₓ+0.5,A𝓏+0.5)`. The operation order is mirror, then
rotation, then translation.

Positive rotation follows positive Minecraft yaw: clockwise on a north-up map
viewed from above. Relative horizontal offsets map as follows: 90° `(x,z)→(-z,x)`,
180° `(x,z)→(-x,-z)`, and 270° `(x,z)→(z,-x)`. These are exact swaps/sign changes,
not trigonometric point rotation, so quarter turns do not accumulate drift. Yaw
adds the selected turn and normalizes to `[-180,180)`; pitch is unchanged.
Horizontal support-face vectors rotate exactly while up/down remain unchanged.
Pure rotation retains player-local movement labels because recorded yaw rotates
with the path; reflection still exchanges left/right and corresponding diagonals.
The exporter applies this to typed M0/M3/M4/M5 movement fields, V2 points, I3
support/pose/aim/face fields and C3 voxels.

The recorded point/voxel homes remain unchanged. A relative derived export still
contains exactly one first-batch `S1 relative`; transformed world evidence is
expressed against that same execution-time home and continuations never re-home.
Raw timeline bytes, action/opcode order, batch count and operation count remain
unchanged. The manifest labels the result
`DERIVED_COORDINATE_TRANSFORM_NOT_NEW_HUMAN_RECORDING`. Identity export remains
byte-identical to the original exporter output. This is an offline typed-source
operation, not a new BCL runtime mode, hidden controller, path optimizer, or claim
that replay will succeed.

## Conservative BCL mapping

Export uses `default_commands()` and `compile_bcl()` from the installed Blockwire
package. It does not copy an opcode table or add a BCL feature.

| Recorded evidence | Existing BCL output |
|---|---|
| changed grounded tick with active or just-released movement input | ordered `M0 X Y Z F` checkpoint |
| sealed elevated rotating crouch run | `M3` path, or one continuous `M4` when exact placements occur before crouch release |
| sealed bounded step-off followed by a local no-damage landing | exact `M5 Q L H P B` native drop |
| required recorded held item for a mapped mutation | `I1 I=...`; repeat only after sealed `held_count_after=0` evidence |
| stable main-hand placement of a registry-supported block | exact `V2` + `I3 B P F Q R K J C=false`, or the same verified placement embedded in `M4` |
| stable break-to-air of a registry-supported removable block | exact `C3 B=... P=[x,y,z] D=false` |

Every eligible grounded movement tick is retained; paths are not smoothed and
waypoints/actions are not optimized. `M0` is still a goal through the existing
walker, not raw W/A/S/D timing replay. M3/M4/M5 are emitted only from matching
sealed view, input, pose, support and landing evidence. Directional pulses remain
one native tick; M4 can use per-button leases so crouch stays held without adding
a direction tick. `C=false` prevents an unrecorded plant-clearing attack. C3
claims removal only, never a drop. Unsupported registry values are rejected by the real compiler and listed in
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
its source SHA-256, registry digest, program digest, coordinate/home dependency,
and operation counts are in the manifest. Absolute batches each declare
`S1 absolute`; relative export declares `S1 relative` only in batch 0001 and uses
the persistent session home thereafter (continuation batches can carry 30 payload
operations because they omit S1).

The following remain raw evidence with explicit unsupported-conversion records or
limitations unless a narrow contract above matches: arbitrary airborne/jump arcs,
key durations, yaw/pitch/mouse trajectories, backward/strafe semantics, exact
hotbar slot identity, off-hand placement, unconfirmed use/attack, unsupported
blocks/items, and motion without recorded local movement input. No optimistic command is invented for them.

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

## Historical native implementation smoke — PASS

A private isolated graphical-client smoke exercised the actual F8/F9/F10 path and
PID/cwd-verified automated local window input. With the endpoint disabled, the
recorder captured 515 native ticks, movement, one confirmed placement, one
confirmed break and one retained uncertain intent. Offline export preserved the
raw timeline byte-for-byte and compiled 17 payload operations. This remains a
capture/export smoke only, not the later house verdict.

## Manual 71-block Superflat benchmark — H04 GO

The owner-only benchmark uses the frozen `superflat_house_5x5` objective: 46 wall
blocks plus a 25-block roof, clear entrance/interior, intact floor, no helpers,
native interior access and a safe player. The canonical snapshot identity remains
`d61d166e4431e7693907cc0590f1808e2d8f12d62befe3b0a5a64c22b70696a7`.

H01–H03 remain immutable calibration failures. H04 is the first strict manual GO:
2,214 sealed events, 2,056 ticks and 71 confirmed unique placements. Independent
closed-save verification found exactly 71/71 required blocks with no extras; the
manual interval was 101.947 seconds and the sealed capture interval was
102.781447078 seconds. The endpoint stayed disabled and ordinary owner
keyboard/mouse input performed the build. The sealed support, face, pose, view,
crouch, jump and movement evidence was sufficient; no re-recording was needed.

## Generated reconstruction replay — R33 GO

R01–R32 remain immutable NO-GO attempts with their first failure preserved. R33
is the first strict generated replay GO. It used one frozen, unedited relative
export (manifest SHA-256
`34dfe48a25983950fe57c0bd01f0bfd48aed2415e6a0fd634a3c6aad0053833d`)
on a fresh canonical snapshot through the ordinary authenticated BCL/runtime/native
stack. The 20 batches contained 571 payload operations: 429 M0, one continuous
M4, one bounded M5 native drop, two evidence-driven I1 equips, 69 V2 and 69 I3.

All 20 batches completed with zero failed actions and zero automatic action
retries. The runtime reported all 71 placement postconditions, including two
placements inside M4. Independent native inspection and a second verification
after the graphical client had closed both found the exact 71-block objective,
no missing or unexpected blocks, intact floor, complete roof, accessible interior
and a safe player. Replay execution took 457.253838652 seconds.

H04 manual GO and R33 replay-functionality GO remain separate verdicts.

## Repeatability and relative portability — Q03/P03 GO

The first qualification harness attempt, R34/Q01, failed before any BCL effect
because its local ephemeral TLS files had not been provisioned. Q02 then retained
one GO and two NO-GO runs: R36 and R37 both stopped at M4 sample 22 because the
runtime checked immediately after the third and final permitted one-tick pulse,
before native residual motion had settled into the unchanged `A=0.3` radius.
These failures remain immutable.

The correction adds only up to four cancellable 50 ms native observation intervals
after that final pulse. It submits no additional directional input and performs no
action retry. Under the new frozen Q03 source, R38, R39 and R40 each completed
20/20 batches, 572 runtime operations and 71/71 placement postconditions with zero
failed actions and zero retries. Independent native and closed-client save checks
passed for all three, establishing strict replay repeatability at 3/3.

P03 then ran the identical source freeze and byte-identical v16 BCL at two
additional prepared relative homes. Together with R38, the voxel-home translation
deltas were `[48,0,0]`, `[48,0,48]` and `[0,0,48]`; all 71 corresponding blocks
translated exactly. Each origin retained an intact floor, clear entrance,
accessible interior, safe player and no structure at the other qualified origins.
This establishes portability only across these three equivalent isolated
Superflat preparations, not arbitrary terrain or worlds.

The H04 capture contains 2,056 native ticks, 26 directional movement episodes and
71 final-structure placements with no temporary scaffold. Its saved movement
counters total 27.90 horizontal metres. R33 used 9,156 saved gameplay ticks and
26.53 horizontal metres. The generated program has 431 movement operations, 71
placements and 20 explicit stop directives. Fifteen placements use the original
floor as support; 56 use earlier structural blocks, including all 25 roof blocks.
Operation counts and human ticks have different granularity and are not an
efficiency ranking.

Current deterministic verification passes 551 Python tests, `./gradlew check`, all
47 Play2Code exporter mutations, all 183 skill mutations, all 48 BCL mutations and
10/10 isolated TLS interop checks.
The original [H04/R33 record](evidence/play2code-h04-r33.json) remains unchanged;
the repeatability/portability evidence is in
[its separate record](evidence/play2code-repeatability-portability.json).
Raw timelines, UUIDs, precise homes, saves, credentials and keys remain private.

## Offline translation and reflection — GO for the two retained references

The frozen H04/v16 recording and construction order were derived into separate
programs; neither H04 nor its original BCL was edited. Offline checks retained all
20 batches, 571 payload operations, one persistent `S1 relative`, exact opcode and
action order, and all 71 placement dependencies (15 original-floor and 56
prior-structure supports). Entrance and roof geometry matched the transformed
objective with no missing or unexpected cells.

H01's exact closed-save structure is a pure `[-2,0,-4]` translation of H04. X01
executed its derived program on a fresh isolated canonical copy: 20/20 batches,
572 runtime operations, 71/71 placements, zero failed actions/retries, and exact
native plus closed-client verification. This qualifies that translation replay;
it does not relabel H01's historical position-mismatch verdict.

H02's exact closed-save structure reflects H04 across voxel Z=0 (continuous plane
Z=0.5). The first frozen mirror X02 correctly transformed coordinates, yaw, faces
and hit points but retained the recorded M4 `right` control. It stopped in batch 15
at sample 5 with `recorded_path_diverged`, 55 verified placements and no retry.
That NO-GO remains immutable. A new frozen derivation exchanged lateral recorded
controls as required by reflection. X03 then completed 20/20 batches, 572 runtime
operations and 71/71 placements with zero failed actions/retries; independent
native and closed-client verification found the exact reflected house, clear
entrance, complete roof, accessible interior and safe player.

The resulting coordinate-transformation verdict is GO only for these two exact
retained Superflat references and the frozen H04 strategy. It is not a different
human strategy, broad structure synthesis, or arbitrary terrain portability.
See the public-safe
[coordinate-transformation record](evidence/play2code-coordinate-transformation.json).

## Exact quarter-turn rotation — QROT01 historical result

The rotation freeze retained the original 20 batches, 571 payload operations,
612 compiled operations, exact source/action order and one first-batch
`S1 relative`. An independent reference implementation—not `CoordinateTransform`
itself—checked every typed operation, all 71 destinations, 15 original-floor and
56 prior-structure supports, entrance orientation and complete roof for 90°, 180°
and 270°. The 0° export remained byte-identical to H04/v16. Current translation
BCL remained byte-identical to X01 and reflection artifacts remained byte-identical
to X03.

Native functionality is GO because each required orientation has a fresh strict
success: ROT90-A, ROT180-B and ROT270-A each completed 20/20 batches, 572 runtime
operations and 71/71 placement postconditions with zero failed actions/retries.
Independent native inspection and post-exit closed-save verification found exact
rotated geometry, no missing/incorrect/unexpected blocks, the entrance on the
expected side, a complete roof, accessible interior and safe player.

ROT180-A remains an immutable NO-GO. It stopped in batch 15 at M4 sample 22 with
`recorded_path_sample_not_reached`, 55 placement events and 57 verified blocks;
the final sampled distance was just outside the unchanged 0.3 radius. No tolerance,
directional pulse or action retry was added, and the independently calculated
coordinates/orientation remained exact. The fresh unchanged ROT180-B run passed.
Across the prospectively frozen two runs per orientation, strict repeatability is
therefore NO-GO: 90° 2/2, 180° 1/2, 270° 2/2 (5/6 overall). Functionality and
repeatability are separate gates.

This qualification covers exact quarter turns of the cobblestone H04 strategy on
the equivalent isolated Superflat fixture. Arbitrary angles and direction-sensitive
block-state rotation are not implemented or claimed. The 5/6 result remains the
immutable QROT01 point-in-time record; see the public-safe
[coordinate-rotation record](evidence/play2code-coordinate-rotation.json).

## ROT180 stabilization — root cause confirmed, QROT02 repeatability GO

Follow-up comparison found no transformed-program difference: ROT180-A and
ROT180-B used byte-identical batch-15 BCL and the same fresh snapshot, and their
positions immediately before M4 differed by only 0.000023713 blocks. The retained
ROT180-A final position was inside the 0.3 radius for M4's penultimate directional
sample (0.278329) but just outside the immediately following hold sample (0.301872).
A hold sample has no direction to apply. The recorded-path runtime had considered
the directional sample complete using only its own target, so it skipped the final
sealed direction pulse even though the next hold target was not yet reachable.
That terminal sample-completion defect is the confirmed cause of the observed
`recorded_path_sample_not_reached`. Historical per-tick telemetry was not retained,
so the exact earlier native tick that produced the small positional difference
cannot be reconstructed.

The correction is deliberately narrow. Before accepting a directional sample that
is immediately followed by a hold sample, both sealed targets must now be inside
the existing arrival radius. Otherwise M4 may issue only the current sample's
already-recorded one-tick direction under the existing maximum of three pulses,
then use the same bounded passive coast observations. It adds no tolerance, action
retry, new direction, alternate path, path smoothing or BCL/runtime transform.
Actor checks, deadline/cancel checks, per-button leases, cleanup and F8 remain
unchanged.

A private isolated suffix fixture reproduced the old completion gate 3/3 at exactly
0.301872 blocks with zero movement pulses. The corrected gate succeeded 3/3, each
with exactly one recorded `right+sneak` pulse. The complete M4 segment succeeded
5/5 both before and after the correction under controlled nominal starts, while the
corrected runs also observed both embedded placements; this bounds the claim to the
confirmed terminal-sample condition rather than claiming all intermittent motion
was made deterministic.

After 555 Python tests, Gradle, 47/47 Play2Code mutations, 184/184 skill mutations,
48/48 BCL mutations and ten TLS interoperability checks passed, QROT02 froze the
source before native replays. Three fresh ROT180 runs passed 3/3. Two fresh runs
for both ROT90 and ROT270 also passed, for 7/7 strict quarter-turn successes. A 0°
identity replay and fresh X01 translation/X03 reflection replays passed as well,
for 10/10 planned native runs. Every run completed 20/20 batches, 572 runtime
operations and 71/71 placement postconditions with zero failed actions or automatic
retries, followed by read-only native inspection and post-exit closed-save
verification.

Strict rotation repeatability is therefore GO for the prospectively frozen QROT02
cohort: 90° 2/2, 180° 3/3 and 270° 2/2. This does not erase the QROT01 5/6 result or
relabel ROT180-A. It still qualifies only the frozen H04 strategy on equivalent
isolated Superflat fixtures. Human generalization remains pending H05. See the
public-safe [rotation-stabilization record](evidence/play2code-rotation-stabilization.json).

## Next human benchmark — H05 pending

H05 is prepared on a fresh canonical fixture with the endpoint disabled. A separate
empty F9/F10 preflight proved passive recording controls, but it is explicitly not
the human benchmark and must not be exported as H05. When the owner resumes the
prepared handoff, press F9, manually build the same objective using a deliberately
different construction order/camera path, then press F10 and wait for completion.
Until that happens, H05 remains `PENDING_OWNER_MANUAL_BUILD`, its replay is
`NOT_RUN`, and human generalization remains `PENDING`.
