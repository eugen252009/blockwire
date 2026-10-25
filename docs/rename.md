# Blockwire rename / upgrade

The intended product name is **Blockwire**. The earlier “Block Bridge” name was a
spelling mix-up. This is a local alpha rename, not a published migration/release.

## Current identity

- Project: `blockwire/` (your local checkout directory)
- Fabric mod ID / display name: `blockwire` / **Blockwire**
- Java package: `dev.blockwire`
- Python distribution/import: `blockwire`
- Commands: `blockwire`, `blockwire-mcp`
- Skill-provider entry-point group: `blockwire.skills`
- New instance configuration: `minecraft/config/blockwire/`
- Agent variables: `BLOCKWIRE_CONFIG`, `BLOCKWIRE_URL`, `BLOCKWIRE_CERT_FILE`,
  `BLOCKWIRE_TOKEN_FILE`, `BLOCKWIRE_SKILLS`
- Bundle: `dist/blockwire-0.2.0-alpha.2.zip`

Paths beginning with `build/` or `dist/` are relative to the checkout root;
`minecraft/config/` refers to the selected Minecraft instance, not the checkout.

## Existing Minecraft instances

Replace the old mod JAR with the Blockwire JAR; **do not install both**. Fabric
metadata rejects coexistence with the old `block_bridge` mod ID. This utility
registers no gameplay item/block identities that need world conversion.

If `config/block-bridge/` already exists, Blockwire **reuses that directory in
place**, retaining the settings, API key, compatibility token and private/public
TLS identity. It does not copy, merge, delete, regenerate or silently reset them.
Fresh installations use `config/blockwire/`.

If both directories exist, startup fails closed rather than guessing which
credentials/identity are authoritative. Stop Minecraft, choose the intended
complete directory and privately archive the other. Do not merge private identities.

The TLS service identifier **`block-bridge.invalid`** deliberately stays unchanged.
It is a wire compatibility ID, not the current product name. Renaming it would
invalidate existing pinned certificates. Certificate/hostname verification,
mandatory TLS and API-key authentication remain enabled. The saved keybinding ID
`key.block_bridge.toggle` is also retained so existing rebindings survive; its
visible label/category now says Blockwire.

## Python / MCP hosts

For an existing environment, uninstall the old SDK **before** installing the new
wheel, to avoid two distributions owning the same compatibility files:
```sh
pip uninstall block-bridge
pip install 'python/blockwire-0.2.0a2-py3-none-any.whl[mcp]'
```

Use `from blockwire import Bridge, Player` and the new command/env names for new
integrations. Compatibility modules preserve `block_bridge`, its client/skills
imports, `python -m block_bridge.cli`, and the `block-bridge` /
`block-bridge-mcp` command aliases.

Legacy `BLOCK_BRIDGE_*` connection/skill variables remain fallback aliases;
new `BLOCKWIRE_*` values take precedence when both are present. Existing
`block_bridge.skills` providers remain discoverable **only with explicit opt-in**.
New providers should declare the new group and `blockwire` dependency; do not
register the same provider under both groups (ambiguous providers are rejected).

Point the config variable at whichever actual settings file your instance uses,
including the legacy directory on upgrades. The project folder moved: update
absolute launcher/MCP config paths that pointed to the previous project directory.
No unrelated host configs or account databases are rewritten automatically.
When working from an old editable checkout, stale `block_bridge*.egg-info`
metadata can make an extension appear under both provider groups. Archive that
old generated metadata and reinstall the renamed packages; do not relax the
ambiguous-provider guard to hide it.

## Evidence and limits

The pre-rename sources, artifacts and handoff ZIP were preserved under
`build/qualification/pre-blockwire/`. Historical evidence/manifests keep their
old names and hashes; they are not rewritten to pretend they tested a new artifact.

Current checks: [evidence/rename.json](evidence/rename.json). An existing owned
superflat fixture was launched with the renamed packaged mod, its unchanged legacy
API key/certificate, and legacy environment configuration. Native menus and a
descriptive walking job succeeded. Config/token/private identity/certificate bytes
were verified unchanged. This is scoped compatibility evidence, not broader
Survival/two-client/release qualification.
