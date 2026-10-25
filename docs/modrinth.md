# Modrinth preparation (not publication)

Prepared project identity:
- Name: **Blockwire**
- Suggested slug: `blockwire` (availability NOT checked/reserved)
- Summary: *Connect Minecraft players to Python scripts and descriptive MCP tools through a secure local bridge.*
- Loader: Fabric; game version: **26.3 only**
- Environment: client required, server unsupported (do not install on servers)
- Version: `0.2.0-alpha.2`, release channel **alpha**
- License: MIT; bundled original icon; source JAR built separately
- Required dependency: Fabric API; Loader >=0.20.1, Java >=25
- Suggested categories: utility / library, subject to current Modrinth taxonomy

The local `dist/blockwire-0.2.0-alpha.2.zip` is an agent/developer handoff bundle,
not a Modrinth mod upload. Use its main mod JAR for any separately approved upload;
never upload the whole bundle as a mod file. Python skills/providers run outside Minecraft.

Use README as the long description, including automation permissions and the
local-control/security warning. Upload only the main JAR as primary, optionally
attach the sources JAR. The Python package/MCP host is a separate optional
installation, not something Modrinth automatically launches.

## Build a local upload kit

```sh
python3 tools/package_modrinth.py
```

This runs the Loom/Gradle build and audits the installable JAR before copying it to
`dist/modrinth/0.2.0-alpha.2/`. The folder contains:
- `blockwire-0.2.0-alpha.2.jar` — **primary Modrinth mod upload**.
- `optional-sources/` — developer source attachment; not an installable mod.
- `DESCRIPTION.md`, `RELEASE_NOTES.md`, `project-icon.png` — page/version assets.
- `modrinth-settings.json` — manual settings reference, **not an API request**.
- `packaging-report.json`, `SHA256SUMS` — inspection and integrity checks.

The build expands `fabric.mod.json`, compiles Java 25 client classes and packages
three Bouncy Castle libraries as Fabric nested JARs. Fabric API remains an external
required dependency. No `.mrpack` is generated: this project is a mod, not a modpack.
No Python runtime, agent/model, live config, certificate, private key or saved world
is embedded. The Python SDK/MCP adapter must be installed separately.

Checks reject wrong identity/version/environment/Java target, missing API metadata,
missing mixins/licenses/libraries, test/stale classes and runtime identity paths.
Run `python3 -B -m unittest discover -s tests -p test_package_modrinth.py -v` after
building to exercise those guards against isolated modified copies.

The packaged graphical qualification is reused only when the exact artifact hash
matches its retained evidence. Packaging success does not close release gates.
The standalone [page description](modrinth-description.md) still needs a real
public SDK/source location before publication.

## Before any upload

- [ ] Choose the actual project owner/authors, repository and issue/contact URLs.
- [ ] Check name/slug and dependency metadata on Modrinth.
- [ ] Review alpha verification and remaining native/multiplayer/security coverage.
- [x] Test the identical packaged JAR with Fabric API in an isolated instance
  (Linux native menus, TLS and flat-world walking only; see rename/skill evidence).
- [ ] Verify Windows/macOS token ACLs and client input behavior before claiming support.
- [ ] Confirm icon/license attribution, checksums and changelog.
- [ ] Obtain explicit publication approval.

There is deliberately **no publishing task, upload token, automatic CI release,
fabricated project URL, tag, git remote or upload action**.
