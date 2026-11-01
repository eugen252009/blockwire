# BCL/1 command reference (generated)

Do not edit manually. Regenerate: `.venv/bin/python tools/generate_bcl_reference.py`.

Limits and validation come from existing skill schemas. Availability describes an adapter, not current world readiness.
Server-to-client event opcodes are NOT executable client commands. See [normative specification](bcl.md).

## M0 — movement.walk

Navigate using existing walk_to; auto Y requires an observed reachable target cell. F=normal/fast/sneak.

- Signature: `M0 X Y Z F`
- Category/direction: skill / client_to_server
- Available: true
- Existing skill: `walk_to`
- Permissions: movement
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID

- Relative coordinates: x (point_x), y (point_y), z (point_z)

- `X` → `x`: number; runtime default `"current_x"`.
  Schema: `{"maximum": 29999984, "minimum": -29999984, "type": "number"}`
- `Y` → `y`: number; runtime default `"reachable_height"`.
  Schema: `{"maximum": 2048, "minimum": -2048, "type": "number"}`
- `Z` → `z`: number; runtime default `"current_z"`.
  Schema: `{"maximum": 29999984, "minimum": -29999984, "type": "number"}`
- `F` → `mode`: enum; static default `"normal"`.
  Schema: `{"enum": ["normal", "fast", "sneak"], "type": "string"}`

## M1 — movement.approach

Approach an initially visible interactable by exact block ID (chest means minecraft:chest). Choose the nearest candidate with a supported local route; optional exact visible block position. Face the route and primarily walk forward on flat full-block terrain, with tiny lateral corrections. Recheck out-of-view targets at bounded stopped checkpoints; aim and confirm the exact native target. Never opens/uses it. Partial visibility/routes, at most 64 blocks; damage avoidance is best effort.

- Signature: `M1 T P E`
- Category/direction: skill / client_to_server
- Available: true
- Existing skill: `approach`
- Permissions: movement
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID

- Relative coordinates: position (voxel)

- `T` → `target`: string; static default `"minecraft:chest"`.
  Schema: `{"maxLength": 128, "minLength": 1, "pattern": "^(?:[a-z0-9_.-]+:)?[a-z0-9_./-]+$", "type": "string"}`
- `P` → `position`: json; static default `null`.
  Schema: `{"anyOf": [{"items": {"type": "integer"}, "maxItems": 3, "minItems": 3, "type": "array"}, {"type": "null"}]}`
- `E` → `terrain`: boolean; static default `false`.
  Schema: `{"type": "boolean"}`

## M2 — movement.dig_step

Excavate 1–3 descending one-block steps in a selected cardinal direction. Centers on retained support, clears only fresh exposed dry soil/stone/leaves/plants in the adjacent column, top-down, then enters ONLY if new native collision geometry proves supported floor/headroom and an edge. Appropriate equipped tool required for stone/coal. Never own support, sand/gravel, fluids or hidden voxel queries. Useful for bounded access/clearance; not an ore finder. Success verifies movement, NOT collected resource counts.

- Signature: `M2 D N`
- Category/direction: skill / client_to_server
- Available: true
- Existing skill: `dig_step`
- Permissions: mining
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID

- `D` → `direction`: enum; static default `"north"`.
  Schema: `{"enum": ["north", "south", "east", "west"], "type": "string"}`
- `N` → `steps`: integer; static default `1`.
  Schema: `{"maximum": 3, "minimum": 1, "type": "integer"}`

## C0 — crafting.item

Craft recipe batches (NOT desired output count); existing recipe and native station contracts apply.

- Signature: `C0 I N`
- Category/direction: skill / client_to_server
- Available: true
- Existing skill: `craft_item`
- Permissions: crafting
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID

- `I` → `item`: resource; required default `null`.
  Schema: `{"maxLength": 128, "minLength": 1, "pattern": "^[a-z0-9_.-]+:[a-z0-9_./-]+$", "type": "string"}`
- `N` → `batches`: integer; static default `1`.
  Schema: `{"maximum": 16, "minimum": 1, "type": "integer"}`

## C1 — crafting.gather_wood

Gather additional vanilla logs from initially observed exposed blocks within a six-block local radius. Known full-block routes; terrain=True enables observed one-block climbs/descents. No slabs/gaps, leaf clearing, hidden wood search or crafting. Use native mining and require inventory gain; crouching is not forced. Stops on danger, damage, replacement actor or uncollected drops. Target checks are best effort, not atomic block guards.

- Signature: `C1 N E`
- Category/direction: skill / client_to_server
- Available: true
- Existing skill: `gather_wood`
- Permissions: mining
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID

- `N` → `count`: integer; static default `1`.
  Schema: `{"maximum": 16, "minimum": 1, "type": "integer"}`
- `E` → `terrain`: boolean; static default `false`.
  Schema: `{"type": "boolean"}`

## C2 — crafting.gather_block

Mine currently exposed stone/cobblestone/dirt/coal ore within radius 6 using the shared harvesting motor. terrain=True enables bounded one-block routes. Pickaxe required per mechanics contract except soil. No Silk Touch or hidden lookup. Optional position selects ONE exact currently exposed target (count=1), not a hidden coordinate query. excavate=True with terrain=True permits observed one-block-lower SIDE cuts and entry only with newly observed supported geometry, NEVER own support. ground_soil matches exposed dirt/grass. Success requires additional expected drops in inventory, not attack receipts. Unsupported terrain stops.

- Signature: `C2 B N E D P`
- Category/direction: skill / client_to_server
- Available: true
- Existing skill: `gather_block`
- Permissions: mining
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID

- Relative coordinates: position (voxel)

- `B` → `block`: enum; required default `null`.
  Schema: `{"enum": ["minecraft:stone", "minecraft:cobblestone", "minecraft:dirt", "minecraft:grass_block", "minecraft:crafting_table", "minecraft:coal_ore", "ground_soil"], "type": "string"}`
- `N` → `count`: integer; static default `1`.
  Schema: `{"maximum": 16, "minimum": 1, "type": "integer"}`
- `E` → `terrain`: boolean; static default `false`.
  Schema: `{"type": "boolean"}`
- `D` → `excavate`: boolean; static default `false`.
  Schema: `{"type": "boolean"}`
- `P` → `position`: json; static default `null`.
  Schema: `{"anyOf": [{"items": {"type": "integer"}, "maxItems": 3, "minItems": 3, "type": "array"}, {"type": "null"}]}`

## C3 — crafting.remove_block

Remove ONE exact currently exposed dirt/grass/stone/cobblestone full cube using the shared guarded mining motor. Requires fresh native body/head clearance afterward, NOT drops or attack receipts. No hidden coordinate lookup, automatic scaffolding or pickup claim. Optional one-level cardinal side cut, never own support.

- Signature: `C3 B P D`
- Category/direction: skill / client_to_server
- Available: true
- Existing skill: `remove_block`
- Permissions: mining
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID

- Relative coordinates: position (voxel)

- `B` → `block`: enum; static default `"minecraft:dirt"`.
  Schema: `{"enum": ["minecraft:dirt", "minecraft:grass_block", "minecraft:stone", "minecraft:cobblestone"], "type": "string"}`
- `P` → `position`: json; required default `null`.
  Schema: `{"items": {"type": "integer"}, "maxItems": 3, "minItems": 3, "type": "array"}`
- `D` → `excavate`: boolean; static default `false`.
  Schema: `{"type": "boolean"}`

## I0 — inventory.inspect

Fresh observed inventory; does not open a GUI.

- Signature: `I0`
- Category/direction: skill / client_to_server
- Available: true
- Existing skill: `inspect_inventory`
- Permissions: observe
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID


## I1 — inventory.equip

Equip an inventory item, using a free hotbar slot if needed. Verify held item; fenced native inventory only.

- Signature: `I1 I`
- Category/direction: skill / client_to_server
- Available: true
- Existing skill: `equip_item`
- Permissions: inventory
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID

- `I` → `item`: resource; required default `null`.
  Schema: `{"maxLength": 128, "minLength": 1, "pattern": "^[a-z0-9_.-]+:[a-z0-9_./-]+$", "type": "string"}`

## I2 — inventory.consume

Eat an explicitly supported existing food while stationary, empty offhand and clear upward target. Fenced native hotbar/use; verify hunger gain AND item reduction. already_full means no food consumed. No food search, crafting or survival guarantee; leaves requested food selected.

- Signature: `I2`
- Category/direction: skill / client_to_server
- Available: true
- Existing skill: `consume_item`
- Permissions: inventory
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID


## I3 — inventory.place

Place an equipped supported block against a selected currently observed full-cube support face within 3 blocks. Verify block and inventory consumption. No hidden coordinate lookup.

- Signature: `I3 B P F A C`
- Category/direction: skill / client_to_server
- Available: true
- Existing skill: `place_block`
- Permissions: inventory
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID

- Relative coordinates: support (voxel)

- `B` → `block`: enum; static default `"minecraft:crafting_table"`.
  Schema: `{"enum": ["minecraft:crafting_table", "minecraft:cobblestone", "minecraft:dirt", "minecraft:oak_planks", "minecraft:spruce_planks", "minecraft:birch_planks", "minecraft:jungle_planks", "minecraft:acacia_planks", "minecraft:dark_oak_planks", "minecraft:mangrove_planks", "minecraft:cherry_planks", "minecraft:pale_oak_planks"], "type": "string"}`
- `P` → `support`: json; static default `null`.
  Schema: `{"anyOf": [{"items": {"type": "integer"}, "maxItems": 3, "minItems": 3, "type": "array"}, {"type": "null"}]}`
- `F` → `face`: enum; static default `"up"`.
  Schema: `{"enum": ["up", "down", "north", "south", "east", "west"], "type": "string"}`
- `A` → `auto_position`: boolean; static default `false`.
  Schema: `{"type": "boolean"}`
- `C` → `clear_plants`: boolean; static default `true`.
  Schema: `{"type": "boolean"}`

## I4 — inventory.place_at

Place ONE agent-selected block coordinate. Select support/face among currently observed dry full-cube neighbors, bounded to three pre-use candidates; delegate native positioning and verified placement. Never retry uncertain use. No structure, resource or scaffold strategy.

- Signature: `I4 B P C`
- Category/direction: skill / client_to_server
- Available: true
- Existing skill: `place_at`
- Permissions: inventory
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID

- Relative coordinates: position (voxel)

- `B` → `block`: enum; static default `"minecraft:crafting_table"`.
  Schema: `{"enum": ["minecraft:crafting_table", "minecraft:cobblestone", "minecraft:dirt", "minecraft:oak_planks", "minecraft:spruce_planks", "minecraft:birch_planks", "minecraft:jungle_planks", "minecraft:acacia_planks", "minecraft:dark_oak_planks", "minecraft:mangrove_planks", "minecraft:cherry_planks", "minecraft:pale_oak_planks"], "type": "string"}`
- `P` → `position`: json; required default `null`.
  Schema: `{"items": {"type": "integer"}, "maxItems": 3, "minItems": 3, "type": "array"}`
- `C` → `clear_plants`: boolean; static default `true`.
  Schema: `{"type": "boolean"}`

## V0 — view.observe

Fresh bounded client observation, no hidden world queries.

- Signature: `V0`
- Category/direction: skill / client_to_server
- Available: true
- Existing skill: `observe_environment`
- Permissions: observe
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID


## V1 — view.interact

Approach a currently visible crafting table and open its native 3x3 menu. Other blocks unsupported.

- Signature: `V1 T P E`
- Category/direction: skill / client_to_server
- Available: true
- Existing skill: `interact_with_block`
- Permissions: inventory
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID

- Relative coordinates: position (voxel)

- `T` → `target`: string; static default `"minecraft:crafting_table"`.
  Schema: `{"const": "minecraft:crafting_table", "type": "string"}`
- `P` → `position`: json; static default `null`.
  Schema: `{"anyOf": [{"items": {"type": "integer"}, "maxItems": 3, "minItems": 3, "type": "array"}, {"type": "null"}]}`
- `E` → `terrain`: boolean; static default `false`.
  Schema: `{"type": "boolean"}`

## V2 — view.aim

Aim native camera at a supplied world point using actor-fenced native time-based rotation. No hidden coordinate/block lookup; success is observed camera orientation.

- Signature: `V2 X Y Z`
- Category/direction: skill / client_to_server
- Available: true
- Existing skill: `aim_at`
- Permissions: movement
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID

- Relative coordinates: x (point_x), y (point_y), z (point_z)

- `X` → `x`: number; required default `null`.
  Schema: `{"maximum": 29999984, "minimum": -29999984, "type": "number"}`
- `Y` → `y`: number; required default `null`.
  Schema: `{"maximum": 2048, "minimum": -2048, "type": "number"}`
- `Z` → `z`: number; required default `null`.
  Schema: `{"maximum": 29999984, "minimum": -29999984, "type": "number"}`

## F0 — combat.fight

Explicit bounded combat against zombies, skeletons, spiders and creepers with per-mob fight/evade/ignore policies. Evade wins. Uses selected vanilla sword/axe (unarmed only by opt-in), guarded native attacks and short flat-ground pursuit. Bounded stationary waits retain the job/cooldown after knockback, target height or temporary visibility loss; no blind attacks or vertical movement. Low health terminates after at most one safe retreat pulse. Creeper fighting hits then backs off; no fuse prediction or immunity. Success means selected enemies absent from bounded observations, NEVER confirmed kills. Cancel releases controls.

- Signature: `F0 D H U`
- Category/direction: skill / client_to_server
- Available: true
- Existing skill: `fight`
- Permissions: combat
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID

- `D` → `duration_seconds`: number; static default `20.0`.
  Schema: `{"maximum": 120, "minimum": 0.1, "type": "number"}`
- `H` → `min_health`: number; static default `8.0`.
  Schema: `{"maximum": 20.0, "minimum": 1.0, "type": "number"}`
- `U` → `allow_unarmed`: boolean; static default `false`.
  Schema: `{"type": "boolean"}`

## S0 — execution_mode

Modal setting: get with ?/status; set value; omitted cycles ordered enum.

- Signature: `S0 V`
- Category/direction: setting / client_to_server
- Available: true
- Existing skill: `None`
- Permissions: settings
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID

Setting: `{"cyclic": true, "default": "sync", "name": "execution_mode", "values": ["sync", "async"]}`

- `V` → `value`: enum; runtime default `"cycle"`.
  Schema: `{"enum": ["sync", "async", "?", "status"], "type": "string"}`

## S1 — coordinate_mode

Select global coordinates or capture a persistent session home at execution time. Explicit relative assignments re-home; omitted toggles; ?/status are side-effect-free.

- Signature: `S1 V`
- Category/direction: setting / client_to_server
- Available: true
- Existing skill: `None`
- Permissions: settings
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID

Setting: `{"cyclic": true, "default": "absolute", "description": "Select global coordinates or capture a persistent session home at execution time. Explicit relative assignments re-home; omitted toggles; ?/status are side-effect-free.", "name": "coordinate_mode", "values": ["absolute", "relative"]}`

- `V` → `value`: enum; runtime default `"cycle"`.
  Schema: `{"enum": ["absolute", "relative", "?", "status"], "type": "string"}`

## S2 — movement_mode

Modal setting: get with ?/status; set value; omitted cycles ordered enum.

- Signature: `S2 V`
- Category/direction: setting / client_to_server
- Available: true
- Existing skill: `None`
- Permissions: settings
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID

Setting: `{"cyclic": true, "default": "normal", "name": "movement_mode", "values": ["normal", "fast", "sneak"]}`

- `V` → `value`: enum; runtime default `"cycle"`.
  Schema: `{"enum": ["normal", "fast", "sneak", "?", "status"], "type": "string"}`

## S3 — error_mode

Modal setting: get with ?/status; set value; omitted cycles ordered enum.

- Signature: `S3 V`
- Category/direction: setting / client_to_server
- Available: true
- Existing skill: `None`
- Permissions: settings
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID

Setting: `{"cyclic": true, "default": "stop", "name": "error_mode", "values": ["stop", "continue"]}`

- `V` → `value`: enum; runtime default `"cycle"`.
  Schema: `{"enum": ["stop", "continue", "?", "status"], "type": "string"}`

## S4 — timeout_seconds

Modal setting: get with ?/status; set value; omitted cycles ordered enum.

- Signature: `S4 V`
- Category/direction: setting / client_to_server
- Available: true
- Existing skill: `None`
- Permissions: settings
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID

Setting: `{"cyclic": false, "default": 30.0, "name": "timeout_seconds", "values": []}`

- `V` → `value`: setting_number; required default `null`.
  Schema: `{"anyOf": [{"maximum": 120, "minimum": 0.1, "type": "number"}, {"enum": ["?", "status"], "type": "string"}]}`

## E0 — events.subscribe

Own-session event subscription control.

- Signature: `E0 T`
- Category/direction: event_control / client_to_server
- Available: true
- Existing skill: `None`
- Permissions: events
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID

- `T` → `event`: string; required default `null`.
  Schema: `{"type": "string"}`

## E1 — events.unsubscribe

Own-session event subscription control.

- Signature: `E1 T`
- Category/direction: event_control / client_to_server
- Available: true
- Existing skill: `None`
- Permissions: events
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID

- `T` → `event`: string; required default `null`.
  Schema: `{"type": "string"}`

## E2 — events.subscriptions

Own-session event subscription control.

- Signature: `E2`
- Category/direction: event_control / client_to_server
- Available: true
- Existing skill: `None`
- Permissions: events
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID


## E3 — events.clear

Own-session event subscription control.

- Signature: `E3`
- Category/direction: event_control / client_to_server
- Available: true
- Existing skill: `None`
- Permissions: events
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID


## E100 — event.player.position

Server-originated observation event; clients cannot emit it.

- Signature: `E100`
- Category/direction: event_out / server_to_client
- Available: true
- Existing skill: `None`
- Permissions: events
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID


## E101 — event.player.health

Server-originated observation event; clients cannot emit it.

- Signature: `E101`
- Category/direction: event_out / server_to_client
- Available: true
- Existing skill: `None`
- Permissions: events
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID


## E102 — event.inventory.changed

Server-originated observation event; clients cannot emit it.

- Signature: `E102`
- Category/direction: event_out / server_to_client
- Available: true
- Existing skill: `None`
- Permissions: events
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID


## E103 — event.command.completed

Server-originated observation event; clients cannot emit it.

- Signature: `E103`
- Category/direction: event_out / server_to_client
- Available: true
- Existing skill: `None`
- Permissions: events
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID


## E104 — event.player.dead

Server-originated observation event; clients cannot emit it.

- Signature: `E104`
- Category/direction: event_out / server_to_client
- Available: true
- Existing skill: `None`
- Permissions: events
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID


## E105 — event.player.respawned

Server-originated observation event; clients cannot emit it.

- Signature: `E105`
- Category/direction: event_out / server_to_client
- Available: true
- Existing skill: `None`
- Permissions: events
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID


## E106 — event.player.not_in_world

Server-originated observation event; clients cannot emit it.

- Signature: `E106`
- Category/direction: event_out / server_to_client
- Available: true
- Existing skill: `None`
- Permissions: events
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID


## E107 — event.transport.disconnected

Server-originated observation event; clients cannot emit it.

- Signature: `E107`
- Category/direction: event_out / server_to_client
- Available: true
- Existing skill: `None`
- Permissions: events
- Preconditions: authorized actor/session, fresh native observations, skill preconditions
- Return: verified SkillResult / fresh observation
- Errors: UNKNOWN_COMMAND, UNKNOWN_NAMESPACE, UNKNOWN_PARAMETER, INVALID_ARGUMENT, INVALID_ENUM_VALUE, MISSING_REQUIRED_ARGUMENT, DUPLICATE_ARGUMENT, INVALID_STRING, PROGRAM_LIMIT, EMPTY_PROGRAM, PERMISSION_DENIED, UNSUPPORTED_CAPABILITY, UNREACHABLE_TARGET, EXECUTION_TIMEOUT, EXECUTION_CANCELLED, POSTCONDITION_FAILED, ACTOR_MISMATCH, INTERRUPTED_SESSION, COORDINATE_HOME_UNAVAILABLE, COORDINATE_CONTEXT_MISMATCH, INVALID_COORDINATE_HOME, UNSUPPORTED_VERSION, DIRECTION_DENIED, REQUEST_CONFLICT, STALE_REQUEST, INVALID_REQUEST_ID
