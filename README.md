# Blockwire

A small **client-side Fabric mod** that connects Minecraft players to Python
scripts and LLM tools. **Minecraft 26.3 · Java 25 · Fabric Loader 0.20.1+ · Fabric API.**

**Alpha software, not published.** Renamed from the earlier “Block Bridge” working
name; [upgrade/compatibility notes](docs/rename.md) preserve existing configs and TLS identities.
Independent of Echoes of the Sculk. No server
installation is required. Use only in your own worlds or where server operators
explicitly permit automation.

## Ways to use Blockwire

### 1. Python: precise, scripted actors

```python
from blockwire import Bridge, Player

with Bridge.from_env() as connection:
    player = Player(connection)
    print(player.observe()["text"])
    print(player.inventory()["items"])
    player.look(yaw=0, pitch=15)
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

MCP exposes `list_skills`, `walk_to`, `run_skill`, `skill_status` and `cancel_skill`.
Jobs run in the background; status and cancellation stay responsive. The first
walker supports **loaded flat full-block ground only** and reports blocked reasons
for unsupported situations. `avoid_damage` is conservative, **not immunity**.
See [skills](docs/skills.md).

Another LLM/developer can add goals via the opt-in Python provider template, strict
schemas and shared registry without editing TLS or MCP core. Start at
[AGENTS.md](AGENTS.md) and [extensions](docs/extensions.md).

### 3. WebSocket / MCP: descriptive, LLM-friendly interaction

Ask an MCP agent to **describe surroundings**, **show inventory**, **look at a
known position**, **hold inputs**, or **click an inventory slot**.

Observations come from internal client game data, not OCR:
- Friendly item names **and** stable registry IDs, counts, durability, enchantments.
- Health, hunger, dimension, biome, position and eye coordinates.
- Native crosshair target and a bounded, approximate potentially-visible entity list.
- Open-container slots, coordinates, carried stack and native menu/state IDs.

Each observation has readable `text` plus structured JSON. No arbitrary NBT,
hidden-container inspection, server-world scanning, shell execution or command
execution endpoint. Names supplied by worlds/servers are **untrusted data**.

## Install and connect

1. Build with Java 25: `./gradlew build`.
2. Install `build/libs/blockwire-0.2.0-alpha.2.jar` and Fabric API into an
   **isolated test instance** first. Do not install the sources JAR.
3. Launch Minecraft. The first-run default is disabled. **Press F8 to enable/disable**;
   rebind under Controls if needed. The toggle works in the main menu and other screens.
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
It creates `dist/blockwire-0.2.0-alpha.2.zip` with mod + sources JARs, Python
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

- Movement/jump/sneak/sprint, camera, attack/use, hotbar selection.
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
- Normal reach, collision, crafting, combat, cooldowns and server authority remain
  in Minecraft. Python skills can plan bounded routes; there is no teleportation,
  item spawning, custom damage engine or crafting shortcut.
- For unattended singleplayer use, disable vanilla **Pause on lost focus**
  (F3+P). The bridge deliberately refuses world actions in menus/paused gameplay.
- Receipts mean **submitted**, not successful gameplay. Refresh observations;
  never blindly retry a timed-out inventory/use action.
- No screenshots, visual object recognition or chat sending. Native screen event
  navigation is supported; custom mod menus may need coordinate/keyboard fallback.
  Text field contents are redacted. Potential visibility is not pixel-perfect.
