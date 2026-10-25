# Blockwire

Connect a Minecraft player to Python scripts and descriptive MCP tools through an
authenticated, encrypted WebSocket bridge.

**Client-side Fabric mod · Minecraft 26.3 · Java 25 · Fabric API required · Alpha**

## Features

- Native movement, aiming, mining/use, hotbar selection and inventory interactions.
- Readable client-known scene/inventory data, with registry IDs and structured JSON.
- Native menu navigation: buttons, text fields, keyboard input and scrolling.
- Python/MCP goals with progress, cancellation and opt-in trusted skill extensions.
- Initial `walk_to` support for loaded, flat, full-block ground.
- Mandatory TLS with a persistent per-instance certificate and separate API key.

The mod is **client-only**. Do not install it on a dedicated Minecraft server.

## Installation

1. Install Fabric Loader 0.20.1 or newer for Minecraft 26.3.
2. Install Fabric API and the main Blockwire JAR in the client's mods folder.
3. Launch once. Access is disabled by default; **F8 enables/disables it**.
4. For startup from the main menu, set `enabled: true` in the generated private
   `config/blockwire/settings.json`. IP, port and API key are configurable.
5. Install the **separate Python SDK/MCP adapter** to use scripts or an LLM host.
   Minecraft/Modrinth does not install or launch Python, an LLM or its MCP host.

An SDK wheel and developer handoff bundle are companion artifacts. A public
SDK/source download location must be supplied by the project owner before
publishing this description; no public repository/package URL is claimed here.

## Security and permissions

Each instance creates its TLS identity on first startup. Local adapters can find
the public certificate next to the configuration. Remote adapters need a trusted
out-of-band copy of that certificate. **Never share the private identity or API key.**
Use trusted clients and a firewall; this alpha is not a hardened public service.

Automation has the power of ordinary native GUI/player actions, including
destructive menu confirmations. Use only in your own worlds or where server
operators explicitly permit automation. Server rules and anti-cheat still apply.

## Current limitations

Navigation is currently flat/full-block only: no stairs, jumping, swimming or
general-world pathfinding. `avoid_damage` is best effort, not immunity. Full
Survival/two-client, cross-platform and modpack compatibility qualification remain
open. No account credentials, cloud model or embedded Python runtime are bundled.

## Upgrading from the early “Block Bridge” name

Replace the old JAR; do not install both. Existing `config/block-bridge/`
credentials and certificates are reused, and legacy Python/env aliases remain
supported. If old and new config directories both exist, startup refuses to
guess which identity to use.

MIT-licensed. Bouncy Castle certificate libraries are included with license notices;
Fabric API is a separate required dependency.
