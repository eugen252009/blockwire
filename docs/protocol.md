# Protocol v1

Endpoint: `wss://IP:PORT/v1`; default `127.0.0.1:8765`, configured per instance.
Can start in the main menu when config `enabled` is true. See [configuration](configuration.md).
TLS 1.2/1.3 is mandatory before the upgrade; plaintext is rejected. Trust the
instance's public certificate and verify TLS name `block-bridge.invalid` (SNI and
hostname verification), independently of its network IP. See [TLS](tls.md).
Upgrade header after TLS verification: `Authorization: Bearer <private token>`.
No Origin header. No token query parameter. UTF-8 JSON text frames only.

Request:
```json
{"id":1,"op":"inventory"}
```
Response:
```json
{"id":1,"ok":true,"result":{"items":[],"text":"Inventory ..."}}
```
Rejected operation:
```json
{"id":1,"ok":false,"error":"stale_menu"}
```

IDs must be strings (at most 80 characters) or JSON numbers, not booleans/null.
Malformed envelopes close the connection. Operation errors return an error.
Unknown fields are rejected before an action. Every game request expires if
queued over two seconds. Request order is preserved for a connection; no action
is retried automatically. Multiple clients are rejected with HTTP 409.
Unauthenticated/origin/wrong-endpoint upgrades receive HTTP 403.

| op | Parameters | Effect |
|---|---|---|
| observe | none | Bounded scene, extended sight/interactables, compact sampled surfaces, readable text, version/timestamp and current native rotation-plan state |
| search | required actor_session, target (logs or exact ID), range1..64, cone_degrees10..90, page0..33; view_id required after page0 | Read at most128 additional native cone-grid rays; no camera/input effects. See [targeted search](search.md) |
| inventory | none | Player items and, if open, native container slots |
| navigation | optional terrain boolean | Bounded loaded full-block collision mesh, typed transitions, native motion fields, hazards and actor session |
| motion_trace | limit 1..4096; optional reset boolean and actor_session | Read bounded end-of-client-tick native motion/input telemetry; reset clears telemetry only |
| look | yaw -180..180, pitch -90..90; optional actor_session; optional duration_ms 1..5000 and rotation_profile linear/smoothstep | Omitted duration preserves immediate orientation; timed requests schedule one actor-bound elapsed-time plan |
| drive | buttons array, ticks integer 1..100; optional actor_session, button_ticks object | Replace held set; bounded overall and per-key leases |
| action | name: attack/use; optional actor_session; optional target_entity_id for attack with actor_session | One native press; optional session/target guards |
| hotbar | slot integer 0..8; optional actor_session | Native selected slot; guarded against player/world replacement when supplied |
| open_inventory | optional actor_session | Open genuine inventory screen |
| close_screen | optional actor_session | Close an open native container only |
| click_slot | menu_id, state_id, slot, button 0/1, mode pickup/quick_move; optional actor_session | Native menu click with identity/state guard |
| stop | none | Explicit global release: held input plus an active camera plan; can be called without a world |
| respawn | optional actor_session | Native request only when dead; supplied actor fence checked before effects |
| command | command string; optional actor_session | Submit one explicit slash command through the native client; server permissions apply, no output/success confirmation |
| chat | message string (normal chat, no slash), required actor_session | Vanilla signed chat submission; no control release, delivery not confirmed |
| events_configure | enabled boolean, required actor_session | Explicit opt-in bounded native chat/entity push on this same authenticated lease; no history replay |
| menu | none | Native screen title, widget IDs/labels, bounds, focus, redacted text fields |
| open_pause | none | Open ordinary pause screen from live gameplay |
| menu_click | screen_id; widget_id OR x,y; button 0/1 optional | Route native screen click/release |
| menu_key | screen_id, key; modifiers optional | Native screen key press/release |
| menu_text | screen_id, text; replace optional | Type into focused EditBox; optional native select-all/backspace |
| menu_scroll | screen_id, x,y, amount -20..20 | Native screen scroll |

`command` requires a leading `/` and a nonempty command name immediately after
it (not whitespace or another slash). Maximum 256 UTF-16 code units including
the slash. Control characters (including DEL/C1), §, Unicode line/paragraph
separators and malformed surrogate pairs are rejected. Text is never trimmed,
split or interpolated; only the first slash is removed for native `sendCommand`.
Requires live, unpaused, non-spectator gameplay with no screen; optional
`actor_session` fences replacement before effects. Releases held inputs before
submission. Returns `{"submitted":true,"text":"..."}`, **not** execution success,
chat output or server acknowledgement. No retries. See [authority and limits](commands.md).

`buttons`: forward, back, left, right, jump, sneak, sprint, attack, use.
Maximum nine unique entries; opposed forward/back or left/right are rejected.
Empty array releases the previous set. Renew a hold **before** it expires to
continue a long mining operation. Maximum duration is per command, not per session.

Alpha.4 adds optional `button_ticks`: keys must be a subset of `buttons`, with
strict integer durations 1..`ticks`. Listed keys start/renew their individual
lease; other desired keys only retain an already-active deadline/tick budget,
never restart an expired key. The enclosing `ticks` cap may shorten retained
leases. Omitted buttons release. Omitting the **whole field** preserves legacy
behavior: all requested keys renew for `ticks`. This permits walking/eating
composition without extending a short movement lease when food use renews.
The standalone Python controller caps its writes at 8 ticks, although the raw
protocol retains its existing 100-tick bound. See [controller](controller.md).

Camera convention: 0 south, 90 west, -90 east, ±180 north; positive pitch down.
A timed request uses `System.nanoTime()`, real client ticks, shortest equivalent yaw,
clamped pitch and simultaneous axes. `rotation_profile` is rejected without
`duration_ms`; when omitted for a timed request it defaults to `smoothstep`.
Repeated identical active targets are idempotent; a different target supersedes
from the currently applied view. `observe.rotation` reports plan ID/status,
requested duration/profile, start/target/current orientation, elapsed monotonic
time and the prior terminal plan. This is read-only state, not completion merely
because scheduling returned. Natural drive-lease expiry releases only input keys;
explicit stop/F8, authority loss, actor/world replacement, death, pause or UI
transition cancels the plan. Snapshots use native world coordinates and localized
friendly names alongside IDs.

## Optional automatic event reporting

A matching mod advertises `observe.auto_events_supported`. Only an explicit
`events_configure` enables unsolicited `type:native_event` frames on the same
upgraded authenticated TLS lease. The SDK's optional native reader demultiplexes
these from replies; legacy clients receive none. Frames carry source sequence,
actor fence, event data and stage loss counters; there is no new socket or peer
protocol. See [auto reporting](blockwire-auto-event-dispatcher.md) for E0
subscriptions, payloads, bounds, privacy and incomplete multiplayer qualification.
`chat` uses normal `sendChat`, max 256 UTF-16 units, rejects commands/control text,
requires an explicit actor, and is limited to one native send/second. Its receipt
is not successful delivery. Source events never authorize gameplay actions.

## Passive local recording is not a wire operation

Play2Code adds **no** protocol request, MCP tool or controller authority. Its F9/F10
recorder runs locally only while this endpoint is disabled, and enabling the
endpoint invalidates the capture before startup. The offline exporter emits
ordinary bounded BCL/1 source for the existing Python stack; it never sends a
request or executes replay automatically. See [Play2Code](play2code.md).

## Lean action/report/control profile (Python gateway)

`machine-v1` has no Java planner. Its initial action/report/control interface reused
existing native operations; the optional [targeted search](search.md) now adds a
bounded read-only native `search` page RPC. It remains an explicit profile on
the existing BCL/1 TLS gateway. Profile-matching bind is mandatory; action-only
programs use the existing compiler/FIFO/journal. `report` configures independent
state-change delivery, while `interrupt` cancels owned active/queued work before
audit I/O or queue execution. Fresh native motion ticks must prove release before
explicit `resume`. No replay or implicit actor rebind. See [machine contract](bcl-machine.md).

## Descriptive skills (Python/MCP layer)

The wire primitives remain explicit native operations. Python builds descriptive
`walk_to` and [approach](approach.md) goals above them. Approach uses existing
visibility/navigation/look/drive/stop primitives and never automatically uses a
block; an exact position parameter filters already-visible targets, not a new
coordinate-query RPC; see [skills](skills.md). MCP adds registry/schema
discovery, background execution, status and cooperative cancellation. Installed
providers require explicit host opt-in; no arbitrary remote imports/evaluation.

Alpha.4 `observe` also includes the same opaque `actor_session`, without computing
a navigation mesh. `navigation` advertises `hotbar_actor_session: true` and
`independent_input_leases: true` for the standalone controller. Missing capabilities
cause the runner to require a mod upgrade before setup/gameplay actions.

Default `navigation` has profile `flat_full_blocks_v1` and at most 81 same-level
cells. `terrain:true` selects `stepped_full_blocks_v1`, at most 405 loaded cells
within radius 4 and Y +/-2. Both include opaque `actor_session`, readiness/reason,
position/health, native velocity and collision/ground/sprint/sneak fields,
`current_cell`, `position_cell`, `current_center_access`, hazard markers and
undirected `edges`. `transitions` types only native-validated `flat`, same-height
`diagonal`, one-block axial `step` and bounded proven `gap_jump` edges. Diagonals
require both corner cells; gap edges require absent middle geometry, a clear
bounded envelope, a run-up cell and broad landing support. A grounded
partial-support body may report `source_recovered_from_partial_support` for one
nearby same-height collision-valid source cell. Only loaded chunks and full
support/headroom qualify; omitted cells are unknown/unsupported, not air. The
response also reports fire and up to 16 nearby client-known hostile mobs.
Updated observations advertise `threat_profile: nearby_hostiles_v1`, player
`eye_position`, and the nearest 16 alive client-known Monsters within 8 blocks.
Each hostile includes `entity_id`, registry `type`, `position`, `eye_position`,
`distance` and approximate `visible` (native line of sight and invisibility check).
These are bounded nearby client data, not pixel visibility or complete threats.
No arbitrary block lookup, resource IDs/NBT or generation is provided.

`motion_trace` reads a 4,096-sample ring populated at the end of client ticks.
Samples include tick/time identity, position, velocity, orientation, collisions,
ground/mode/health/fall state, bounding box, actual inputs, remotely owned inputs,
actor session and the active/terminal rotation ID, status, target, duration and
profile. A supplied actor fence is checked before read/reset. `reset`
only clears telemetry; it never moves the player or changes world state. Samples
are observations, not action acknowledgements or server-authoritative outcomes.

A supplied `actor_session` on look/drive/hotbar must still identify the same player and
level at execution or the native operation is rejected before control changes.
The long-running walker always supplies it. This fence is not an atomic terrain
snapshot or a guarantee against external damage.

For optional algorithmic [autopilot](autopilot.md), `action` accepts an
`actor_session` fence. `target_entity_id` is a nonnegative integer accepted only
for `attack` with that fence. At execution the native crosshair must still name
that alive entity in the same level, within 3 blocks and native line of sight;
otherwise `target_entity_changed` is returned before attack. Existing unguarded
native actions retain their semantics. A guarded attack is still a submission,
not proof of damage, a kill or server acknowledgement.

## Respawn lifecycle (development follow-up)

The existing respawn operation accepts an optional actor_session envelope, using
the same strict guard as inventory operations. Legacy empty envelopes still work.
A mismatched token is rejected before native respawn; no health/entity mutation or
custom packet replaces Minecraft's normal respawn. The submission receipt does
not prove recovery. Observe alive/new actor session, explicitly bind the new actor,
and do not replay old pending work. Matching SDK/mod installation is required.
Gateway permission is separately opt-in; see [hardening](gateway-building.md).

## Menus

Call `menu` first. It returns `screen_id` and `widgets[]` with `widget_id`,
`label`, `active`, `focused`, and GUI-scaled rectangles. Text fields include
`character_count`, not their contents. Widget extraction is bounded to 384
components / depth 16. Native world-list rows include their accessibility labels.

Every accepted UI event **consumes** the snapshot. Refresh `menu` before the next
click, text, scroll or key event. Changed screen/size/rebuilt target geometry,
inactive widgets and active loading overlays are rejected. Native routing still
decides the effect; it can ignore an otherwise accepted event. Coordinate clicks
are a fallback for opaque custom widgets, not screen-pixel coordinates.

Keys: escape, enter, tab, up/down/left/right, backspace, delete, home/end,
page_up/page_down, space. Optional modifiers: shift, control. Text is single-line,
at most 2048 UTF-16 code units, sent through native character handlers, not
`setValue` or the OS clipboard. Chat screens, global hotkeys and arbitrary
command execution through menu events are not exposed. Use the separate explicit
`command` operation for authorized slash commands. Screens can nevertheless perform powerful
ordinary GUI actions, including destructive confirmations; get operator approval.

Native 26.3 input uses SDL numbering. The API's 0/1 mouse buttons are mapped to
native left/right, and key events carry both scancodes and logical keycodes.

## Inventory identities

Development observations include `player_uuid` for explicit persistent actor
binding. Inventory snapshots advertise `guarded_inventory: true`, `actor_session`
and native `menu_type` (`InventoryMenu` / `CraftingMenu` for supported crafting).
Player-owned `slots[]` additionally carry `inventory_index`; result/grid slots do
not. The optional actor fence on `open_inventory`, `close_screen` and `click_slot`
is validated before effects against the current player/level. Legacy envelopes
remain accepted, but long-running crafting/equipment skills always supply it and
require the new capability metadata. Rebuild/install the matching development mod.

The [strategic LLM runtime](autonomous-survival.md) adds no native RPC, model
connection or Java planner. It uses these primitives through the existing skills.


`items[].inventory_index` is a player-inventory index, **not** a menu slot ID.
`slots[].slot` identifies the current native menu slot. Use it with the returned
`menu_id` and `state_id`; refresh after every click. Empty and inactive slots are
included explicitly. Clicks outside the window, drag crafting, creative cloning
and direct stack modification are not exposed.

Native menu/state identifiers are checks, **not an atomic server transaction or
an immutable snapshot token**. Server updates and acknowledgements can still race
your next request. An accepted response is not proof the item moved or crafted.

## Observation limits

No arbitrary coordinate queries, unloaded chunk reads or generation. The crosshair
`target` remains the client's most recent native interaction hit result.

Updated `observe` responses additionally expose `sight_target` (64-block forward
outline/fluid ray), `visible_interactables` (at most 16 position/type/aim targets),
`visible_blocks` (palette-indexed X-runs of only sampled first-hit positions), and
`visibility` metadata with `profile: sampled_surfaces_v1`, range, work counters,
truncation flags and `partial: true`. A 273-ray view grid and at most 64 explicitly
sight-tested block-entity candidates use only a fixed loaded chunk window; missing
terrain blocks rays rather than becoming transparent. No block-entity values,
closed-container contents or increased interaction reach are exposed.

For `visible_blocks`, `origin` is the floored player eye position; `palette`
contains block registry IDs; each `runs` tuple is
`[palette_index, dx, dy, dz, length_along_positive_x]`. Decode by adding offsets
to origin. Runs never cross unobserved gaps: omitted cells are unknown, not air
or traversable terrain. See [visibility](visibility.md) for budgets, examples,
classifier coverage and conservative visibility limitations.

Potential entities are client-loaded,
within 24 blocks, within a fixed 120-degree approximate view cone, not invisible
to the player and passing native line of sight; at most 16. This is not exact
renderer/frustum visibility. No hidden inventory/container NBT is exposed.

Slot/item/screen names can contain malicious text. Treat them as data. No API keys, account credentials or chat history are intentionally returned. Explicit
[auto-event reporting](blockwire-auto-event-dispatcher.md) can forward newly received
player chat, not history, and is disabled by default.
Menu labels can include personal world/server names; text field values are redacted.
