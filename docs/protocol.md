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
| observe | none | Bounded scene, extended sight/interactables, compact sampled surfaces, readable text, version/timestamp |
| inventory | none | Player items and, if open, native container slots |
| navigation | none | Bounded loaded flat-ground collision mesh, hazards and actor session |
| look | yaw -180..180, pitch -90..90; optional actor_session | Absolute native orientation; target refreshes next frame |
| drive | buttons array, ticks integer 1..100; optional actor_session, button_ticks object | Replace held set; bounded overall and per-key leases |
| action | name: attack/use; optional actor_session; optional target_entity_id for attack with actor_session | One native press; optional session/target guards |
| hotbar | slot integer 0..8; optional actor_session | Native selected slot; guarded against player/world replacement when supplied |
| open_inventory | none | Open genuine inventory screen |
| close_screen | none | Close an open native container only |
| click_slot | menu_id, state_id, slot, button 0/1, mode pickup/quick_move | Native menu click with identity/state guard |
| stop | none | Release held input; can be called without a world |
| respawn | none | Native request, only when dead |
| menu | none | Native screen title, widget IDs/labels, bounds, focus, redacted text fields |
| open_pause | none | Open ordinary pause screen from live gameplay |
| menu_click | screen_id; widget_id OR x,y; button 0/1 optional | Route native screen click/release |
| menu_key | screen_id, key; modifiers optional | Native screen key press/release |
| menu_text | screen_id, text; replace optional | Type into focused EditBox; optional native select-all/backspace |
| menu_scroll | screen_id, x,y, amount -20..20 | Native screen scroll |

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
Snapshots use native world coordinates and localized friendly names alongside IDs.

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

`navigation` has profile `flat_full_blocks_v1`, opaque `actor_session`, readiness
and reason, position/health, `current_cell`, `current_center_access`, and at most
81 same-level cells (integer `[x,y,z]` with hazard markers). `edges` are undirected
index pairs validated with native swept collision boxes. Only loaded chunks and
full support/headroom qualify; omitted cells are unknown/unsupported, not air.
The response also reports fire and up to 16 nearby client-known hostile mobs.
Updated observations advertise `threat_profile: nearby_hostiles_v1`, player
`eye_position`, and the nearest 16 alive client-known Monsters within 8 blocks.
Each hostile includes `entity_id`, registry `type`, `position`, `eye_position`,
`distance` and approximate `visible` (native line of sight and invisibility check).
These are bounded nearby client data, not pixel visibility or complete threats.
No arbitrary block lookup, resource IDs/NBT or generation is provided.

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
command execution are not exposed. Screens can nevertheless perform powerful
ordinary GUI actions, including destructive confirmations; get operator approval.

Native 26.3 input uses SDL numbering. The API's 0/1 mouse buttons are mapped to
native left/right, and key events carry both scancodes and logical keycodes.

## Inventory identities

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

Slot/item/screen names can contain malicious text. Treat them as data. No API keys, account credentials or chat history are intentionally returned.
Menu labels can include personal world/server names; text field values are redacted.
