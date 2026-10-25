# Blockwire Python

Program real-player scripts with `Bridge` + `Player`, or expose descriptive
MCP tools through `blockwire-mcp`. Set `BLOCKWIRE_CONFIG` to the private
instance settings file; the adapter reads its IP, port and API key. Native menu
navigation is available before joining a world when config auto-start is enabled.
See the repository README and docs.

The `blockwire.skills` package adds declarative goals, strict schemas, cooperative
background jobs and explicitly selected provider extensions. `Player.walk_to(...)`
currently supports loaded flat full-block ground only. Read `docs/skills.md` and
`docs/extensions.md` in the project for safety limits and extension contracts.

The Python package does not embed Python into Minecraft. Scripts run outside the
game. `Backend` / `CallableBackend` allow trusted in-process integrations to
reuse the actor API; no server entity or fake-player implementation ships yet.
