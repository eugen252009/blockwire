# Blockwire bundle

This is a local alpha build, not a published release. Upgrading from Block Bridge?
Read `source/docs/rename.md`: replace the old JAR, keep the existing config/TLS
identity, and uninstall the old SDK before installing the new distribution.

1. Install `mods/blockwire-0.2.0-alpha.2.jar` with Fabric API into an isolated
   Minecraft 26.3 / Java 25 instance.
2. Launch once. Configure `minecraft/config/blockwire/settings.json` as described
   in `source/docs/configuration.md` (or press F8). Keep the generated private key.
3. Make a Python 3.11+ environment and install the bundled wheel:
   `pip install 'python/blockwire-0.2.0a2-py3-none-any.whl[mcp]'`.
   pip resolves the declared dependencies; this is not an offline dependency bundle.
4. Set `BLOCKWIRE_CONFIG` to that private settings file. Local certificate
   discovery is automatic; remote clients need an out-of-band trusted public
   certificate. Never distribute the instance's private TLS identity.
5. Run `blockwire skills`, `blockwire-mcp`, or use the Python actor API.
   See `source/docs/skills.md` for goal limits and status/cancel behavior.

For the next developer/LLM: start at `source/AGENTS.md` and
`source/docs/extensions.md`. The full allowlisted project sources, tests and a
runnable extension template are included. Prefer new Python skills over Java or
transport edits.

Verify every file against SHA256SUMS. No credentials, certificates, private keys,
saved worlds, accounts, personal configs or existing profiles belong in this bundle.
Nothing in the build script uploads, tags, pushes or publishes.
