# Changelog

## 0.2.0-alpha.3 — Unreleased local candidate

Updated mod and separate Python SDK/MCP package. See
[release notes](docs/releases/0.2.0-alpha.3.md) for current capabilities and limits.
No upload/publication or isolated graphical qualification is implied.

### Development history

- Shared Python feedback motor for approach/autopilot travel: held W overlaps
  observations and small steering on known straight routes, with 4–8-tick renewable
  native leases. Corners/checkpoints/precision positioning still stop. Session
  fences, target-memory bounds, cancellation and cleanup retained; no new RPC or
  Java physics. 82 Python tests and 43 skill mutations; live smoothness NOT RUN.

- Approach now faces its route and primarily uses W, with A/D restricted to tiny
  aligned one-tick corrections; no backward/chest-facing travel. Target checks
  use bounded out-of-view checkpoints with fresh sight confirmation rather than
  cached render hits. Per-action native/session/hazard/cleanup limits remain;
  forward-policy live retest NOT RUN.

- Corrected approach camera ping-pong: target-facing native strafe/back/forward
  combinations retain the intended route direction, with bounded camera turn
  steps and fresh lifecycle/visibility checks before movement after turning.
  Component camera regressions pass; live camera-fix retest remains NOT RUN.

- Corrected near-waypoint approach centering after a failed operator live smoke:
  single-tick centering pulses and waypoint progress checks stop oscillation instead
  of relying on displacement-only stuck detection. Faster-motion/rebound fixtures
  and regression mutations added; post-fix live retest still NOT RUN.

- Python/MCP/CLI `approach` skill for initially visible interactables: exact ID and
  optional visible block position, nearest supported local route, standing beside
  the target, re-observation and observed native reach before success. Never opens,
  uses or transfers items. Flat-ground-only, cancellable/session-fenced; graphical
  acceptance NOT RUN. No Java/transport changes required. See docs/approach.md.

- Optional Mod Menu integration with native English/German settings screen:
  live endpoint/controller status, F8-equivalent enable/stop and an explicitly
  saved startup-only preference. No credentials displayed or Mod Menu bundled.
- Private atomic startup-flag persistence, stale/symlink rejection and settings/API
  linkage contracts. Graphical Mod Menu acceptance remains NOT RUN.

- Bounded 64-block extended sight and potentially visible interactable positions
  in scene observations; native interaction reach remains unchanged.
- Compact palette/X-run sampled block surfaces, loaded-only native outline/fluid
  rays, candidate/work caps and explicit partial/truncation metadata. No closed
  container contents. Native visibility/codec contracts and targeted mutations;
  graphical acceptance remains NOT RUN. See docs/visibility.md.

- Opt-in algorithmic Python autopilot skill and MCP/Python convenience APIs:
  flat-ground walk/run/sneak, stationary monitoring, nearby-hostile defense and
  higher-priority creeper evasion, bounded duration/status/cancellation.
- Bounded typed threat observations and session/target-guarded native attacks.
- Deterministic contracts and isolated mutation checks; live graphical autopilot
  combat/evasion acceptance remains NOT RUN. See docs/autopilot.md.

## 0.2.0-alpha.2 — Historical unpublished baseline

- Corrected the product name to Blockwire: project, mod ID/assets, Java/Python
  packages, command names, provider namespace and distributable.
- Preserved legacy config directories, API keys, TLS identities, saved keybindings,
  Python imports/CLI aliases and environment/provider compatibility.
- Added rename compatibility contracts and a real packaged legacy-instance smoke.

## 0.2.0-alpha.1 — Historical unpublished baseline

- Descriptive Python skills, strict goal schemas and explicit installed-provider opt-in.
- Background MCP jobs with progress/status, cancellation and single-actor control ownership.
- Flat full-block `walk_to`, local native collision mesh and guarded actor sessions.
- Real graphical flat-world arrival, hole detour, cancellation and extension smoke evidence.
- LLM/developer handoff instructions, extension template and allowlisted local ZIP builder.
- No general terrain/jump/swim pathfinder or no-damage guarantee; see docs/skills.md.

## 0.1.0-alpha.1 — Historical unpublished baseline

### TLS transport update
- Mandatory TLS 1.2/1.3 with a persistent, per-instance self-signed EC certificate.
- Verified instance-certificate trust and hostname verification in Python/MCP;
  no plaintext or trust-all fallback. Upgrade mod and SDK together.
- Bundled Bouncy Castle certificate tooling, atomic private identity persistence,
  explicit trust enrollment/rotation and packaged graphical TLS/MCP smoke tests.

- Independent Fabric client mod targeting Minecraft 26.3 / Java 25.
- Local F8 toggle; config-enabled startup from the main menu, configurable bind IP,
  port and private MCP API key; authenticated WebSocket endpoint (loopback default).
- Python actor API, direct dispatcher adapter, CLI and optional stdio MCP facade.
- Descriptive client-known scene and inventory observations.
- Native bounded movement, camera, attack/use, inventory clicks and respawn.
- Native menu descriptions, widget clicks, keyboard/text input and scrolling.
- Transport/validation contracts, isolated mutations and scoped client smoke evidence.

Not implemented: server entity/fake-player backend, embedded Python, pathfinding,
screenshots, command RPC or public-server compatibility qualification.
