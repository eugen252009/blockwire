# Explicit extended machine runs and the first 1,000-call allocation

## Configuration, not a financial quota

An operator-authorized `extended_run=True` / `--extended-run` permits up to
**1,000 model decisions, 1,000,000 counted operations and 86,400 seconds**.
Ordinary defaults/limits remain unchanged. The flag alone does not enlarge the
configured values. External machine MCP can explicitly allow up to1,000 lifetime
task IDs with `--max-session-tasks 1000`; its default remains128.

See [machine-v1](bcl-machine.md#explicit-extended-runs). FIFO/event/wire bounds,
per-action deadlines, native short leases, TLS, actor identity, F8, interrupt,
release confirmation and no uncertain replay remain unchanged. Concurrent MCP
admissions share the lifetime bound without blocking interrupt/status. Neither
configuration is an automatic resource, route, crafting or building planner.
The model still has an explicit `finish_session` tool and can finish early.

The operator stated that prolonged Luna use does not change their budget. This
scope imposed **no monetary/token spending quota**. Per-request timeout/payload
bounds remain; no provider availability or billing behavior is certified here.

## Storage and preservation

The operator authorized `/mnt/4t` for data. New private files use
`/mnt/4t/blockwire/mcp-play/extended-001/`, also reachable through the ignored
`build/mcp-play/extended-001` compatibility link. The new owned Prism instance,
world, recordings, captures and freezes are on that mounted data volume; a scoped
per-launch Flatpak filesystem grant was verified, not a global permission change.
Mount identity and free space on **both** filesystems are checked during the run.

The already stopped prior `hidden-001` scope was relocated to
`/mnt/4t/blockwire/archives/mcp-play/hidden-001/`: **1,645 files /158,194,879 bytes**
were verified byte-for-byte before replacing the original directory with a link.
Historical file contents, evidence hashes and original logical paths remain intact.
No unrelated files, worlds or evidence were deleted.

## Graphical allocation `extended-001`: ended early, milestone not reached

The fresh normal Peaceful Survival world had no setup commands, selected spawn,
relocation, gifts or rescue. Hidden authenticated display identity, ownership and
actual JVM environment were checked before native connection. Native Java/Fabric
sources and JAR were unchanged. Runtime settings were client heap6GiB, server
heap4GiB, configured30FPS, and the existing six-CPU Minecraft affinity pool
(**not exclusive CPU reservation**). CPU≤80%, available RAM≥8GiB and both
free-disk floors≥20GiB remained active.

The declared envelope was1,000 model calls /1,000,000 operations /24h, with a
24h10m outer lifecycle. Eight raw logs were only an initial milestone, not an
automatic stop; subsequent model-chosen crafting/building was allowed.

**Actual result:** the model requested `finish_session` after **18 actual
`gpt-6-luna` calls**, with **982 calls and999,992 operations unused**. More than
86,000 seconds remained in its final decision context. There was **no resource,
decision-budget, operation-budget or eight-log-milestone stop**.

- Eight action programs: two turns, four attack holds and two attack presses.
- Seven waits, one explicit interrupt, one explicit resume and one finish.
- Seven programs completed; one was cancelled. Receipts do not certify gameplay.
- No search, movement, inventory crafting or building calls.
- Closed player statistics record **one `minecraft:oak_log` mined**, no pickups,
  zero walking, unchanged position, Survival mode and final health20.
- Native final inventory and the subsequently closed player file were both empty:
  **0/8 collected logs**. The model's statement about a nearby dropped log was not
  used to certify collection or natural-tree provenance.

Its stopping explanation was that inventory remained empty and it preferred to
stop rather than claim unobserved success. That is evidence of an early model
stopping decision, **not evidence that more actions were impossible**. A generous
allocation did not itself make the model continue or collect the drop. No second
scope, replay, reconnect, respawn or implicit continuation was started.

## Shutdown caveat — retained, not repaired into a pass

Input cleanup was confirmed `released`; the original host recorded
`unknown=false` for that control path. The Minecraft client closed and ReplayMod
finalization/integrity passed (75,204 packets;112,306ms). Viewer review was NOT RUN.

However, the server's save/stop exceeded the owner's **120-second wait**. The
owner exited1, and automatic finalization correctly reported
`Normal server close unconfirmed`. Later server log entries show continued world
saving; the Java process subsequently exited without a host force-kill, but its
exit status was no longer available. **Normal server exit is therefore unconfirmed.**
This lifecycle uncertainty is separate from, and does not overwrite, the original
input-release result. No cause or general storage-performance claim is inferred
from one save timeout on this new storage layout.

The retrospective auditor first verified that the owned host, JVMs, ports and
hidden display were all gone. Only then did it read the saved player/statistics
and verify their agreement with the final native position/inventory. The timeout,
failed automatic finalization and unknown Java exit code remain intact. The scope
is now `STOPPED`, with no resumption. Full world-save integrity is not certified.

## Source-scoped checks

- **836 Python tests**, including nine new extended-envelope tests, PASS.
- `./gradlew --no-daemon check` and **10 TLS interoperability checks**, PASS.
- **57 isolated mutations killed**: extended8, machine14, construction10, search25.
- Private host:13 contracts,3 isolated adapter mutations, and a zero-inference
  provider-route probe passed; scoped Flatpak storage visibility was verified.
- Tests exercise a1,000-decision **simulated** search loop and1,000 simulated MCP
  admissions, old defaults, budget persistence, deadline checks, admission races,
  interrupt responsiveness, cancellation, no replay and explicit CLI forwarding.

These tests do **not** establish1,000 real provider calls, a24-hour graphical soak,
reliable independent exploration/forestry, crafting/building, or64 natural logs.
The real allocation used18 calls. Model arguments and the goal were reconciled
against actual provider captures without using the model report as acceptance.
The dirty working-tree snapshot and private harness were frozen separately;
no pristine-checkout, release, push or general deployment claim is made.

Manifest: [evidence/machine-extended-runs.json](evidence/machine-extended-runs.json).
The previous small-budget result remains [separate](mcp-play-hidden-test.md).
