# Blockwire — extension handoff

Read README.md, SECURITY.md, docs/architecture.md, docs/extensions.md,
docs/skills.md, docs/protocol.md and relevant tests before implementing features.

## Intended split
- Fabric: explicit, bounded, client-known observations and native player actions.
- Python `blockwire.skills`: descriptive goals, planning, progress, cancellation.
- MCP: goal discovery/dispatch and typed convenience tools, not a second planner.
- Prefer a Python skill over changing Java or the secure transport.

## Rename compatibility
Read docs/rename.md. The old TLS service name and saved keybinding ID are deliberate
compatibility constants, not unfinished branding. Preserve old config/import/env
aliases and historical evidence; never mass-replace certificate identity strings.

## Non-negotiable boundaries
- Keep mandatory TLS, per-instance certificate trust, hostname verification,
  API-key checks, loopback defaults, F8 stop, queue bounds and native input leases.
- Never add trust-all, arbitrary command/code/file RPC, teleportation, item spawning,
  remote imports or silent plugin auto-loading.
- Native Minecraft owns movement/collision/damage/crafting. Do not replace it.
- Guard long-running actor actions against world/player replacement. Walking uses
  `actor_session` on every look/drive; never remove that fence.
- A returned input receipt is not a gameplay outcome. `succeeded` requires an
  observed goal postcondition. Damage avoidance is best effort, not immunity.
- Deadline/cancel checks must precede actions and occur in loops. Always release
  owned controls in cleanup; preserve responsive MCP status/cancel calls.
- Extension packages execute trusted host Python, not sandboxed code. Only
  explicitly selected installed entry points may load.

## Add a skill
Use `examples/extension/` or create a module under `python/src/blockwire/skills/`.
Subclass strict `SkillParameters`, define a `SkillDefinition`, return
`SkillResult`, register it, and add deterministic contract tests. MCP's
`list_skills`/`run_skill` automatically expose the description/schema.
Do not edit core TLS/transport just to add a goal. See docs/extensions.md.

## Evidence / packaging
- Keep historical docs/evidence manifests and existing evidence intact.
- Run `./gradlew check`, Python unit tests, applicable isolated mutations and
  TLS interop checks after relevant changes.
- Simulated planner tests are NOT real Minecraft acceptance. Run an isolated
  graphical-client test before claiming gameplay behavior. Mark NOT RUN honestly.
- Never include run/, build/, credentials, certificates, private keys, account
  databases or saves in a distributable. Use the allowlisted bundle builder.
- No push/tag/upload/release without separate operator authorization.
- This repository is independent of Echoes of the Sculk; its acceptance gates
  remain separate. Do not modify that project's worlds or evidence here.
