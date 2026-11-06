# Targeted search — scoped hidden-client acceptance

**Verdict: SCOPED PASS.** One fresh graphical Minecraft client, an authenticated
hidden display, six real `gpt-6-luna` provider calls, real MCP stdio discovery/calls,
and the authenticated machine-v1 gateway/native TLS connection. No simulated
Minecraft backend or direct Python call labelled as an MCP test.

## Declared fixture and bounds

The operator requested a real test of the new search feature. A separate fresh,
loopback-only, offline-identity Peaceful Survival server used an explicitly
**synthetic sight fixture**, prepared before player launch: flat ground, one
exposed off-axis oak log, and one birch log behind a stone screen. No items were
given; no post-join setup, teleport, rescue, harvest or movement was permitted.
This is not naturally generated forestry or arbitrary-spawn qualification.

The owned nested display was authenticated, had no TCP listener, and used an
unmapped host parent. The actual Minecraft JVM's UID, instance cwd, entrypoint and
hidden display were verified **before** the native connection. No visible fallback
or unrelated window/process interaction. Software rendering at15FPS; no comparative
performance claim. CPU≤80%, available RAM≥8GiB and disk≥20GiB gates remained active.
Affinity is not exclusive CPU reservation; no hard financial/token ceiling is claimed.

Limits:480seconds test time,900seconds outer lifecycle, six model requests,
one explicit camera action, one coarse report, three searches, and at most102
native search pages. No provider retries or action replay. Source and JAR freezes,
requests, page responses and process/display proofs remain private under
`build/search/hidden-001/`; all owned resources are closed and the scope is STOPPED.

## Observed results

The real model made the prescribed test calls; it did not choose a forestry route.
Its final prose was retained as **unverified**, not used as acceptance evidence.

| Call | Observed result |
|---|---|
| `turn(yaw=0, pitch=0, duration_ms=200)` | Native angular/release postcondition confirmed |
| `look_around()` | No central sight anchor; no invented hits/distances |
| `search(target="logs", range=32, cone_degrees=30)` | One `minecraft:oak_log`, absent from the captured coarse surface samples |
| `search(target="minecraft:birch_log", range=32, cone_degrees=30)` | No sampled match; the closed save independently confirms the occluded birch log exists |
| `search(target="logs", range=8, cone_degrees=30)` | No sampled match; the exposed target lies outside this ray length |

The positive hit's first sampled surface distance was **19.558020686842788 blocks**;
eye-to-center distance was **20.025343942143525 blocks**. These are distinct
measurements, not interaction reach or guaranteed nearest-surface distance.

Each search completed34 pages,4,225 grid cells and3,209 actual cone rays:102 native
pages and9,627 rays total. Native sample intervals were5.297s,4.700s and4.600s in
this one rendering environment; this is not a latency guarantee. Responses retained
source times, `partial_visibility=true`, `absence_proven=false`, and
`pixel_visibility_verified=false`.

## Independent audit and shutdown

After verified client/server shutdown, a separate audit:

- verified frozen source/JAR hashes, the six actual provider identities/call counts,
  MCP discovery and the owned hidden-child proof;
- decoded only the declared fixture voxels from the closed Anvil save;
- independently reconstructed the cone grid and first full-cube/ground intersections
  without importing production search/filter code;
- checked every page's ray count, target membership, first sampled points, distances,
  faces, aggregation, pose/view binding and unchanged source timestamps;
- checked unchanged native/closed-save player position, empty inventory, health20,
  zero walking distance and no mined-block statistics;
- confirmed `cleanup=released`, `unknown=false`, normal server exit, closed game/
  gateway ports, destroyed owned display parent and no remaining owned client.

An initial audit-only assertion incorrectly expected every per-page hit to use the
north face. Some later rays legitimately hit the west face. The independent audit
was corrected to derive the face from the reconstructed intersection; the failed
audit log remains retained. **Production code, the frozen run and its outcomes
were not changed or replayed.** Replay recording integrity/finalization passed;
interactive Replay Viewer review was **NOT RUN**.

## Qualification boundary

This establishes additional native search observations beyond the coarse sample,
correct conservative occlusion and range negatives **for this fixture** through
real model→MCP→TLS→Minecraft calls. It does not establish pixel-complete visibility,
natural-world exploration, harvesting,64 natural logs, crafting, building,
performance under other loads, or live interruption during a scan. Ordinary MCP's
fresh native search path is unit-tested but its separate graphical acceptance is
still **NOT RUN**. Historical failed/unknown campaigns and previous `look_around`
results are not relabelled.

See [search contract](search.md) and [redacted evidence](evidence/search-hidden-test.json).
