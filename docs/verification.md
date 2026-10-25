# Historical pre-TLS verification — 0.1.0-alpha.1

**This page records the pre-TLS baseline.** Current TLS transport and packaged
client evidence is in [tls.md](tls.md) and [evidence/tls.json](evidence/tls.json).
The historical manifest remains unchanged; its artifact hash is not the TLS JAR.

This is an **alpha implementation with scoped empirical evidence**, not release
approval. Minecraft 26.3, Java 25, Loader 0.20.1, Fabric API 0.165.0+26.3.
The isolated graphical client ran on Linux/X11 with an RTX 2080 SUPER.
No existing profile/account database was used or changed.

## Historical baseline results

| Scope | Result | Evidence |
|---|---|---|
| Build, client metadata, sources JAR | PASS | `build/verification/final-build.log` |
| Java contracts | PASS: 54 checks | Same build log; real Netty/JDK WebSocket exchanges |
| Python SDK contracts | PASS: 11 tests | `build/verification/python-tests.log` |
| Targeted isolated mutations | PASS: 5 KILLED | `build/verification/mutations/results.json` |
| Config auto-start before a world, custom port 8877 and custom API key | PASS | `client-final-clean.log`, real MCP connection |
| 19 MCP tools over actual stdio → Python → WebSocket → graphical client | PASS | `mcp-menu-live.json`, `mcp-menu-smoke.log` |
| Native title → Options → back → world selection, search typing/replacement, selection/load → Pause → save/title | PASS | Same current menu transcript |
| Stale screen rejection; search contents redacted | PASS | Assertions in current menu smoke |
| F8 off/on from title with auto-start config still true | PASS | `menu-f8-toggle.json` |
| Normal owned-client shutdown, endpoint closed | PASS | `client-final-clean.log`; final listener check |
| LAN/wildcard remote connection, TLS, actual IPv6 listener | NOT RUN | Parsing/SDK tests are not network qualification |
| Packaged clean-instance installation | NOT RUN | Live tests used the Fabric dev client, not the built JAR |
| Two-client dedicated-server Block Bridge acceptance | NOT RUN | Earlier Echoes tests are not evidence for this mod |
| Windows/macOS, modpack compatibility, public release | NOT RUN | No publication performed |

## Contract coverage

The Java executable exercises strict numbers/types/boundaries, config defaults,
legacy migration and key persistence, private POSIX config permissions, configured
IP/port/key authority, SDL mouse/logical-key conversions, and hold/toggle input-state
release. Transport tests use a real socket server and include invalid credentials,
Origin/path rejection, exclusive controller ownership, response IDs, rejected
operations without protected effects, disconnect cleanup on the supplied game
executor, cancellation of disconnected queued work, and queued-request expiry.

Mutations deliberately remove authorization and Origin rejection, alter the
inclusive numeric boundary, mis-map native left click and mis-map Backspace.
Each is detected at the named contract assertion, not by a compilation failure.
Mutations run in disposable copies; a fresh unmodified build follows them.

The Python suite covers endpoint shape, explicitly configured remote/TLS URLs,
private credentials, wildcard destination translation, actor/menu argument
preservation, bounded durations, aim math, request identity/errors and rejection
before sending oversized/nonfinite requests.

## Earlier functional smoke, not broad current qualification

Retained earlier development-client snapshots additionally demonstrate native
camera/movement/jump, input expiration and disconnect release, the 46-slot player
inventory, stale menu rejection, and movement rejection while a GUI is open
(`live-inputs.json`). Native hand mining, naturally acquired dirt, MCP slot
pickup/placement, and actual native dirt block placement/consumption were observed
(`native-mining.json`, `native-pickup.json`, `mcp-live.json`,
`native-place.json`). These precede the final config/menu refinements and are
**not** claimed as a fresh full gameplay regression of the final artifact.

Meaningful list scrolling was observed in Key Binds
(`native-menu-scroll.json`), before the subsequent viewport-clipping refinement.
Current final menu traversal includes that clipping code, but broad list/custom
screen coverage remains open.

## Failures retained and corrected

- Initial native attack/use accessor was an abstract mixin class: a runtime cast
  failed. It is now a proper accessor interface; subsequent real mining/use worked.
- Native 26.3 uses SDL left button **1**, not the protocol's **0**. Native key
  events also require both physical scancode and logical keycode (Backspace 8,
  not scancode 42). Real menu tests exposed both; conversion contracts/mutations
  now cover them.
- A forward movement probe hit a solid stone step: no motion was the correct
  collision behavior. A jump was then tested separately; no physics bypass added.
- One attempted dev-client restart used a stale window ID, leaving a previous
  owned client alive and causing a port conflict. That run is excluded. Both
  owned clients were normally closed after identity checks, and the final run
  explicitly logged successful binding with only one client.
- The saved Survival smoke world later had nearby hostile mobs. An extra jump
  trial ended in native creeper death. The menu test now scopes menu navigation
  rather than AFK combat and handles a saved death through ordinary respawn.
  Native loading/respawn screens are polled, not mistaken for readiness.

No production-world items were spawned, no account credentials were read, no
EULA was changed, and no Echoes acceptance gate is closed by these results.

## Reproduce

```sh
./gradlew build
PYTHONPATH=python/src python3 -B -m unittest discover -s python/tests -v
python3 tests/run_mutations.py
./gradlew check --rerun-tasks
```

For a graphical smoke, use an isolated dev instance (`./gradlew runClient`).
Configure its generated private settings for auto-start and a free port. Prepare
a disposable native world. `tests/mcp_menu_smoke.py` deliberately expects the
existing isolated test world **Block Bridge Smo** (the actual native saved name);
do not run it against an unrelated profile. It does not create, delete, seed or
overwrite worlds. Set `BLOCK_BRIDGE_CONFIG` and run it with the project's
MCP-enabled Python environment.

Raw evidence is ignored local output under `build/verification/`. The public-safe
[manifest](evidence/verification.json) records selected hashes and artifact IDs;
private config/token files and game saves are excluded.
