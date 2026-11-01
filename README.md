# Blockwire

A small **client-side Fabric mod** that connects Minecraft players to Python
scripts and LLM tools. **Minecraft 26.3 · Java 25 · Fabric Loader 0.20.1+ · Fabric API.**

**Alpha software, not published.** Renamed from the earlier “Block Bridge” working
name; [upgrade/compatibility notes](docs/rename.md) preserve existing configs and TLS identities.
Independent of Echoes of the Sculk. No server
installation is required. Use only in your own worlds or where server operators
explicitly permit automation.

A consolidated narrative of the implementation phases, retained failures,
rotation migration and final qualification is available in the
[development and change history](docs/development-history.md).

## Ways to use Blockwire

### 1. Python: precise, scripted actors

```python
from blockwire import Bridge, Player

with Bridge.from_env() as connection:
    player = Player(connection)
    print(player.observe()["text"])
    print(player.inventory()["items"])
    player.look(yaw=0, pitch=15)  # omitted timing preserves immediate legacy look
    player.look(yaw=90, pitch=15, duration_ms=200, rotation_profile="smoothstep")
    result = player.drive(["forward"], ticks=10)  # bounded native input, not teleport
    print(result["text"])
```

`Player` works against a small Python `Backend` protocol. `Bridge` connects to a
real graphical client; `CallableBackend` lets trusted Python integrations supply
their own entity/actor dispatcher without using WebSockets. **Server entities,
fake-player spawning and embedded Python are not implemented in this alpha.**
The shipped Python path scripts the genuine connected player.

### 2. Descriptive skills: ask for a goal, not every key press

```python
result = player.walk_to(12.5, 64, -8.5, sneak=False, avoid_damage=True)
print(result["status"], result["reason"])
```

Approach an already-visible chest without opening it:

```python
result = player.approach("chest")  # or minecraft:chest; optional exact visible block position
```

The [approach skill](docs/approach.md) selects a supported standing position,
re-observes and aims at the target, then requires the exact native interaction
hit before success. Flat ground only; graphical acceptance of this skill is NOT RUN.

MCP exposes `list_skills`, `walk_to`, `approach`, `run_skill`, `skill_status` and `cancel_skill`.
Jobs run in the background; status and cancellation stay responsive. The walker
uses loaded flat full-block ground by default; explicit `terrain=True` adds only
bounded observed full-block diagonals, one-block steps and proven short gaps.
Unsupported geometry reports blocked. `avoid_damage` is conservative,
**not immunity**. See [skills](docs/skills.md).

Another LLM/developer can add goals via the opt-in Python provider template, strict
schemas and shared registry without editing TLS or MCP core. Start at
[AGENTS.md](AGENTS.md) and [extensions](docs/extensions.md).

### Optional algorithmic autopilot (experimental)

Explicitly start `autopilot` through MCP or `player.autopilot(...)` in Python.
Select walk/run/sneak travel, optional nearby-hostile defense and creeper evasion.
The deterministic controller needs no model; it is off until invoked, bounded in
duration, observable and cancellable through the same skill jobs. Flat ground only;
**live combat/evasion acceptance NOT RUN**, and no safety guarantee.
Walk-to/approach/autopilot share a [native-feedback motor](docs/motion.md) with
short actor-fenced leases, observed-speed braking and bounded full-block
step/gap handling. In the fixed Minecraft 26.3 movement benchmark, the preserved
controller completed 176/211 repetitions and the optimized controller completed
211/211 while reducing aggregate ticks 47.6%; strict native tick parity remains
NO-GO. Native elapsed-time camera rotation now runs concurrently with movement
only on freshly proven broad support; its 100/200/400 ms qualification and final
211/211 movement rerun are documented separately in the
[rotation benchmark](docs/rotation-benchmark.md). See also the historical
[movement method and evidence](docs/movement-benchmark.md) and
[autopilot limitations](docs/autopilot.md).

Development Python SDK 0.2.0a6 additionally provides opt-in `fight` with per-mob
`fight`/`evade`/`ignore` reactions (for example zombies fight, creeper evade).
Uses native guarded attacks and bounded movement; no kill or safety guarantee.
The a5/a6 controller adds bounded stationary melee/visibility waits and avoids redundant
cooldown queries. In its live follow-up, a6 recovered visibility/range gaps and
finished a previously engaged Normal zombie in **one job**
([record](docs/evidence/fight-visibility-live.json)). Fresh full-health, group and
Hard combat remain unverified; the earlier a5 visibility stops are
[retained](docs/evidence/fight-optimization-live.json).
See [fight policy](docs/fight.md). A prior a4 supervised wooden-sword sequence killed one
Normal zombie across repeated melee jobs ([evidence](docs/evidence/armed-zombie.json));
general/autonomous combat remains unqualified. Earlier unarmed failures are
[retained](docs/evidence/fight-maps.json).
This is not included in the frozen alpha.3 SDK bundle.

### Standalone async controllers (development SDK a7 / mod alpha.4)

Write `setup(bot)` and `loop(bot)` in ordinary local Python. Use
`asyncio.TaskGroup` to walk and eat concurrently; one input mixer preserves
per-task controls and native short leases. Other built-in skills remain exclusive.
No MCP, model or embedded interpreter is needed. See
[the small API, explicit startup and limits](docs/controller.md) and
[the executable example](examples/controller.py). **New concurrency gameplay
acceptance is NOT RUN**; do not run unattended. Existing alpha.3 bundles stay frozen.

### BCL/1 — compact commands, modal sessions and events (development)

```bcl
S0 async
S1 relative
S2 sneak
E0 player.position
M0 1 0 0
```

For human-written BCL, use the Python-started [terminal REPL and file CLI](docs/bcl-terminal.md):
`python -m blockwire repl` / `blockwire run program.bcl`, with explicit gateway trust and actor binding.
The `blockwire-bcl` / `python -m blockwire.bcl.cli` aliases remain available.

Python compiles the whole frame before effects; the existing guarded runtime and
skills execute it. `S1 relative` is an ordered homing operation that captures a
persistent session origin; movement does not move that origin, repeated explicit
`S1 relative` re-homes, and frames/requests never do so implicitly. Modal settings,
home context and request dedup are private per session; async queues work, never
parallel Minecraft controls. MCP provides four compact
compile/execute/discovery tools and reuses skill status/cancel. An optional,
explicitly started loopback **TLS WebSocket gateway** carries requests, replies,
progress, cancellation and subscriptions on one connection. No gamemode/cheat
adapter. [Specification and SDK](docs/bcl.md), [generated registry reference](docs/bcl-reference.md),
[historical native/TLS evidence](docs/evidence/bcl-live.json), and the isolated
[stable S1 graphical qualification](docs/evidence/bcl-s1-homing.json).
[Gateway hardening and LLM building qualification](docs/gateway-building.md) adds
controller/observer isolation, late-cleanup recovery, typed lifecycle faults,
explicit fenced respawn and real model-generated placement/building evidence.
Supplied-material mechanics and unprepared Survival are assessed separately.
[Persistent projects](docs/projects.md) add typed model-authored plans, conservative
observed-world reconciliation, material arithmetic, resumable SQLite context and a
bounded external-model host (`examples/project_agent.py`), not a house generator.
The opt-in [Superflat building benchmark](docs/superflat-building.md) compares a
versioned deterministic BCL program with independently model-generated BCL against
one frozen 71-block reference, closed-snapshot resets and independent acceptance.
Its separately frozen [relative portability cohort](docs/evidence/bcl-relative-portability.json)
ran one byte-identical `S1 relative` fixture at three distinct fractional homes:
3/3 structures passed 71/71 closed-save and native access/safety checks, with
cross-request home persistence, explicit re-homing, restart/dedup recovery and the
tested Python/TLS/file-CLI/REPL interfaces all passing. This qualifies only the
coordinate adapters and fixture path exercised there; broader gameplay remains separate.

### Play2Code — record human play as conservative BCL (development)

With the control endpoint disabled, press **F9** to start a passive local recording
and **F10** to stop after a bounded world-mutation confirmation window. The recorder
observes native movement/input, hotbar changes, block-use/mining intents and stable
client-observed placement/break outcomes; it never drives the player. Export with
`blockwire-play2code export <minecraft>/recordings/<id>` to retain the raw JSONL,
explicit unsupported conversions, unoptimized compiling BCL/1 batches and a hashed
manifest. Generated BCL is **not replay qualification**. There is no recorder RPC,
new opcode, controller or planner. A small isolated native movement/placement/break
capture-and-export smoke passed, but generated-BCL replay remains **NOT RUN**. The
owner-only 71-block human-house benchmark is prepared but remains **PENDING**; no
Test-A/model output is accepted as a human baseline. See
[Play2Code architecture, format and benchmark protocol](docs/play2code.md).

### Strategic LLM agent (development prototype)

`blockwire-agent` / `python -m blockwire.agent_cli` adds an explicitly selected LLM
above the existing skills: observe → typed decision → bounded native skill →
verification → replan. Private per-agent SQLite memory, ownership, cancellation,
model/action limits and non-replayed pending intents remain separate from strategy.
No model endpoint or paid cloud connection is selected automatically.

Native trials crafted planks, a table, sticks and a wooden pickaxe. One real
external-LLM/mailbox run replanned after blocked stone gathering, crafted and
equipped a wooden hoe, then stopped **unverified**. This is **not completed Survival**:
stone access/tools, food supply, farming, death recovery and 24/7 operation remain
unqualified or unimplemented. See [architecture, activation and exact gates](docs/autonomous-survival.md)
and [scoped evidence](docs/evidence/autonomous-survival-live.json).

### Complete-game goal (scaffold only)

`examples/end_portal.py --plan` describes a Survival campaign through the
Ender Dragon to the native credits, ultimately without scripted pauses.
`--no-pause` disables this example's development pause, not F8 or input cleanup.
**The required full Survival stages are not implemented**; the stock SDK
reports blocked before gameplay effects. This is not a working playthrough bot.
The first experimental subgoal is `player.gather_wood(count=1)` (or
`examples/end_portal.py --gather-wood 1`): local flat-ground log harvesting with
inventory confirmation. After an initial unsupported-route stop and a separately
authorized damaging native descent, a live follow-up collected one log. General
terrain navigation and autonomous recovery remain unimplemented. See
[wood harvesting](docs/gather-wood.md) and [campaign limits](docs/end-portal.md).

### Estimate visible distance (read-only, no X-ray)

`player.estimate_distance("minecraft:grass_block")` measures only currently
observed blocks, with horizontal distance and height reported separately. Hidden
or unobserved targets remain unknown. No damage or survival prediction is emitted;
risk assessment belongs to the calling agent/report. CLI/MCP use the same skill;
see [distance estimation and limits](docs/estimate-distance.md).

### Run statistics (read-only, saved counters)

`examples/report_statistics.py /explicit/path/player-statistics.json` reports
deaths, mob kills, movement distances, play time, damage and mining/crafting.
`examples/end_portal.py --stats-file ...` and `blockwire-agent --stats-file ...`
include these in their JSON reports.
No cheats/scoreboard commands are needed. Saved values can lag live play; missing
files remain unknown, not zero. See [statistics and freshness](docs/statistics.md).

### 3. WebSocket / MCP: descriptive, LLM-friendly interaction

Ask an MCP agent to **describe surroundings**, **show inventory**, **look at a
known position**, **hold inputs**, or **click an inventory slot**.

Observations come from internal client game data, not OCR:
- Friendly item names **and** stable registry IDs, counts, durability, enchantments.
- Health, hunger, dimension, biome, position and eye coordinates.
- Native crosshair target and a bounded, approximate potentially-visible entity list.
- Extended block sight and up to 16 potentially visible interactables within 64 blocks;
  sampled block surfaces use a compact palette/run encoding, not a full world map.
  See [visibility and its limits](docs/visibility.md). Detection does not extend action reach.
- Open-container slots, coordinates, carried stack and native menu/state IDs.

Each observation has readable `text` plus structured JSON. No arbitrary NBT,
hidden-container inspection, server-world scanning or shell execution.
Explicit Minecraft slash-command submission is available; see [commands](docs/commands.md). Names supplied by worlds/servers are **untrusted data**.

## Minecraft commands (development checkout)

Submit a single explicitly authorized command through the native client:

```python
player.command("/time set day")  # requires the server's normal permissions
```

CLI: `blockwire command '/time set day'`. MCP: `run_command(command="/time set day")`.
Requires rebuilding/installing the mod and updating the SDK/MCP host together.
This can irreversibly change worlds; the receipt is submission only, without
command output or success confirmation. No automatic retries or permission elevation.
Graphical command acceptance is **NOT RUN**. See [commands](docs/commands.md).

## Install and connect

1. Build with Java 25: `./gradlew build`.
2. Install `build/libs/blockwire-0.2.0-alpha.4.jar` and Fabric API into an
   **isolated test instance** first. Do not install the sources JAR.
3. Launch Minecraft. The first-run default is disabled. **Press F8 to enable/disable**;
   rebind under Controls if needed. The toggle works in the main menu and other screens.
   Development builds also register local **F9/F10** Play2Code start/stop keys;
   recording requires the endpoint to be disabled and never enables it.
   Optional **Mod Menu 21.x for Minecraft 26.3** adds **Mods → Blockwire → Configure**:
   live control status, immediate enable/stop and an explicitly saved startup preference.
   Mod Menu is not bundled or required. See [configuration](docs/configuration.md#optional-mod-menu-screen).
4. The mod generates private `config/blockwire/settings.json` with `enabled`,
   `server_ip`, `port` and a random `mcp_api_key`. Set **`enabled: true`** there to
   start the endpoint automatically at launch, **before joining a world**.
   See [configuration](docs/configuration.md). Changes apply after restart.
   The private `token` file is retained as a legacy SDK compatibility mirror.
   A unique TLS identity is generated on first startup in `config/blockwire/tls/`.
5. Set up the external Python environment:

```sh
python3 -m venv .venv
.venv/bin/pip install -e 'python[mcp]'
export BLOCKWIRE_CONFIG="/path/to/instance/minecraft/config/blockwire/settings.json"
# Optional remote/client address override:
# export BLOCKWIRE_URL="wss://192.168.1.20:8765/v1"
# For a remote instance, securely copy ONLY its public certificate, then set:
# export BLOCKWIRE_CERT_FILE="/trusted/path/certificate.pem"
.venv/bin/blockwire inventory
.venv/bin/blockwire-mcp  # stdio; normally launched by your MCP client
```

Use [examples/mcp-config.json](examples/mcp-config.json) in an MCP-compatible host,
replacing absolute paths. MCP is optional; Python-only installation is
`pip install -e python`. No cloud account, API key or model is bundled.

For two clients use **separate game directories and ports**, e.g. 8765/8766,
and separate Python connections or MCP server entries. One controller per client.
Bind IP is configurable, including LAN/wildcard IPs. **TLS is mandatory**, including
loopback. The SDK trusts only the selected instance certificate and verifies its
TLS service name before sending the API key. Keep firewall/trusted-client restrictions.
Restart Minecraft after changing configuration. Never share instance directories.

## Local handoff bundle

Run `python3 tools/build_bundle.py` (Java 25 and `uv` or Python `build` required).
It creates `dist/blockwire-0.2.0-alpha.4.zip` with mod + sources JARs, Python
wheel/sdist, full allowlisted sources/tests/docs, extension template and checksums.
No game directories, credentials, certificates or saves are copied. This builds
locally only—nothing is published. See [bundle install](docs/bundle-install.md).

## Encrypted connections

Use `wss://`, not `ws://`; update the mod and Python package together. Local MCP
configuration automatically finds the instance certificate. Remote clients need
an out-of-band trusted copy of `tls/certificate.pem` plus their API credential.
Never copy `tls/identity.p12` (the private key). There is no trust-all or plaintext
fallback. See [TLS and certificate trust](docs/tls.md).

## Controls and limitations

- Movement/jump/sneak/sprint; immediate or actor-bound elapsed-time camera
  rotation; attack/use and hotbar selection.
- Native menu descriptions, widget/coordinate clicks, text typing, keyboard
  navigation and scrolling: title screen, options, world selection and pause menu.
  These can also trigger destructive native confirmations; authorize actions carefully.
- Genuine native inventory opening/closing and pickup/shift-click slot actions.
- Native respawn request when dead.
- Input holds expire after at most 100 ticks / 5 seconds; refresh explicitly for
  longer tasks. Disconnect, death, world/player replacement or opening a screen
  releases held input as the game thread advances.
- F8 disables the endpoint and releases inputs. Bridge ownership of a held key
  can override a simultaneous human press of that key; stop automation first.
- Play2Code is passive and local-only. F9 refuses to record while the endpoint is
  enabled; enabling it during a capture invalidates that capture before startup.
- Normal reach, collision, crafting, combat, cooldowns and server authority remain
  in Minecraft. Python skills use native movement, not teleportation or item spawning.
  Explicit slash commands can change the world if the server grants permission; they
  do not grant cheats/OP or replace native gameplay engines.
- For unattended singleplayer use, disable vanilla **Pause on lost focus**
  (F3+P). The bridge deliberately refuses world actions in menus/paused gameplay.
- Receipts mean **submitted**, not successful gameplay. Refresh observations;
  never blindly retry a timed-out inventory/use action.
- No screenshots, visual object recognition or chat sending. Native screen event
  navigation is supported; custom mod menus may need coordinate/keyboard fallback.
  Text field contents are redacted. Potential visibility is not pixel-perfect.
