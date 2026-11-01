# Strategic LLM runtime — development prototype

## Persistent project follow-up

See [projects](projects.md) for the current generic project data/host, Stage-B
failure diagnosis, material/inventory arithmetic, reconciliation, explicit resume
and fixed independent acceptance. [Current scoped evidence](evidence/persistent-projects.json)
records Stage A GO (one uninterrupted supplied-material success) and Stage B
CONDITIONAL GO: actual self-acquired wood → planks → complete native shelter in
Peaceful Survival, independently proven without later construction, but original
autonomous terminal verification still failed. The bounded generic inspector and
current ProjectAgent verification then passed native integration separately.
Older trials below remain historical. A persisted
plan, model finish or successful batch is never current-world completion proof.

## BCL building / gateway follow-up (separate qualification)

The [gateway/building record](gateway-building.md) separates typed native rejections,
death/not-in-world, actor replacement and transport loss. The optional gateway now
has controller/observer roles, late-cleanup reaping and supervised bounded sender/
watcher tasks. Explicit authorized respawn uses an optional native actor fence;
observed replacement requires a NEW explicit session and never replays old actions.

A real tool-free `gpt-6.1-sol` planner generated BCL building programs over the TLS
gateway. In supplied-material Stage A it chose and constructed a 3×3 shelter shell:
14 walls, nine roof blocks, entrance; independent native surface/doorway evidence
exists for the recovered run. A fresh repeated activation built the same 23 shell
positions but exhausted its budget before completing independent goal acceptance.
These are not interchangeable with an uninterrupted reliable building qualification.
The planner's first incorrect finish and subsequent corrections are retained.

`program_verified` now explicitly means BCL subprogram postconditions ONLY;
external `objective_verified` is false until a separate goal predicate establishes
the actual shelter. Camera/placement adapters gained bounded aiming, selected
support faces and optional native-mesh-based mechanical positioning, not a hidden
house plan. Prepared Stage A cobblestone, developer pauses/snapshots and an artificial
death fixture do **not** qualify unprepared Survival building. Stage B uses a
separate empty-inventory, commands-OFF normal Survival world; see the linked current
evidence for its actual outcome. General Survival/food/farm/24×7 claims below remain
unqualified; older tables are historical evidence, not overwritten acceptance.


**First implemented and partially live-qualified slice, not a completed Survival
agent.** The full fresh-world wood → stone → food → farm acceptance scenario has
NOT PASSED. Neither unattended nor 24/7 operation is qualified.

## Repository assessment and separation

Existing foundations were retained: `Player(Backend)`, the pinned-TLS native
bridge, the strict skill registry/executor, exclusive actor ownership, the flat
navigation/feedback motor, and MCP discovery/status/cancel. Native inventory
clicks already existed; generic verified crafting and a persistent strategic LLM
runtime did not. The deterministic autopilot and campaign scaffold are not an LLM
strategy layer and are not used as one here.

```
External LLM / Decider.decide(compact_context) -> strict Decision JSON
                         |
AgentRuntime: ownership, observe/decide/act/verify, budgets, status/cancel
                         |                         |
                   existing skills          private SessionStore
                         |
                Player -> existing native bridge -> Minecraft
```

- **Execution:** Fabric owns native movement, collision, mining, menu clicks,
  crafting, consumption and damage. Python skills are bounded mechanical goals.
- **Runtime:** `agent.py` manages one activation/session, not a resource/progression
  strategy. It does not contain a wood-then-stone campaign or alternative planner.
- **Strategy:** an explicitly supplied external `Decider` chooses ONE next skill,
  wait or finish proposal from current observations and concise prior results.
  Missing materials are feedback to that LLM, not a hidden hardcoded quest chain.
- **MCP:** continues to expose the shared skills. It is not a second planner, and
  this runtime does not need MCP. Do not run competing controllers on one actor.

`recipes.py` is a finite vanilla recipe/dependency catalogue, **not a strategy**.
Only the subset in that catalogue can be crafted. Native output must actually
appear with the expected material consumption; a catalogue entry cannot create
items or bypass the game's crafting rules.

## Implemented reusable skills

All register with the existing registry; `list_skills`/`run_skill` expose the same
schemas automatically. No second native transport or action execution stack.

| Skill | Contract / current limitation | Graphical-client evidence |
|---|---|---|
| `gather_wood` | Additional inventory logs; short actor-fenced attack leases; local flat known standing cells; upper/support restrictions | Additional two logs collected after an earlier pickup failure; not general forestry |
| `craft_item` | Empty cursor/grid, supported native 2×2/3×3 slots, ingredients, actual result, material consumption, output inventory delta | Planks, table, sticks, wooden pickaxe and wooden hoe |
| `equip_item` | Main hand/hotbar only; empty destination for inventory transfer; verify held registry ID | Wooden pickaxe and hoe |
| `interact_with_block` | Currently **crafting table only**; approach a currently observed target and verify actual workbench menu | Table opened |
| `place_block` | Currently table/cobblestone/dirt, top of an observed noninteractive support, not under own feet; block observation AND item reduction | Crafting table at `[-21,69,14]` |
| `gather_block` | Exposed stone/cobblestone/dirt/coal ore; appropriate equipped non-Silk-Touch pickaxe except dirt; shared harvesting motor | Attempt blocked: `no_reachable_exposed_blocks`; **successful stone mining NOT RUN** |
| `consume_item` | Existing enumerated ordinary foods only; stationary, empty offhand, clear upward aim; hunger gain AND food reduction | **NOT RUN**; deterministic fixtures only |

Existing `walk_to` still defaults to loaded flat full-block ground. Its separate
opt-in terrain profile now has deterministic evidence for bounded observed
full-block diagonals, one-block steps and proven short gaps; this strategic-agent
evidence does **not** establish natural cave routing, below-feet mining, swimming
or Nether traversal. Distance remains geometry-only, with unobserved terrain
unknown.
`consume_item` shares its food whitelist/consumption predicate with the existing
async controller; it does not replace Minecraft's consumption engine or create a
second strategic food policy. A brown mushroom is not directly edible here.

## State, lifecycle and failure handling

`SessionStore(path, {agent_id, world_id, player_id})` stores private, bounded JSON
in SQLite (0600), with an exclusive POSIX file lock. This strategic runner is
currently Linux/POSIX-only; Windows is unsupported/NOT RUN, unlike the existing
portable native SDK transport. The world ID is an explicit
operator namespace, **not proof of the actual world/save identity**. One genuine
Minecraft client/endpoint is required per controlled player in this alpha.

Persisted context includes the operator goal, fresh inventory/player state, eight
recent results/notes, sixteen recent events, completed-action counts, context-keyed
failed-action budgets and at most 32 observed interactable positions. Remembered
positions are explicitly **historical and require revalidation**, not a current
world map or permission to query hidden coordinates. Old inventories are replaced
by fresh observations before any resumed decision.

Before an action, its validated pending intent is committed. Interrupted pending
work is **never automatically replayed**. On restart it becomes an event and fresh
state is inspected. A carried stack or unfinished supported crafting grid stops
for explicit recovery: there is no blind rollback, dropping items or retrying an
uncertain result click. The full historical action log is not retained forever;
only compact working memory and counters are stored.

The native player UUID must match; every mutating skill request is fenced to the
bound actor session. Session replacement requires explicit `allow_rebind=True`
/ `--rebind` on a new activation. Even a deliberate dimension transition currently
needs such a future handoff policy; automatic cross-dimension continuation is not
implemented. No automatic respawn or transport reconnection. After uncertain
transport failure, no more gameplay requests/retries are made on that activation.

Per-activation duration, decisions, local-action timeout, model timeout and failure
budgets are bounded. Identical failures are budgeted relative to relevant observed
resources/position/world surfaces, allowing reconsideration after actual changes.
The scoped action adapter caps native drive leases at eight ticks. Local skills
retain cooperative cancel/deadline checks and final input cleanup. Damage/death
while awaiting the model stops the activation; this is **not autonomous retreat**.

`runtime.status()` and `runtime.cancel()` do not wait for a model response; embed
`run()` in a host worker for background operation. CLI SIGINT requests cancellation.
An uncooperative trusted model callback may leave one daemon decision worker until
it returns, but receives data, not a player facade; late replies are not executed.
Trusted Python callbacks/providers are not sandboxed or forcibly killable.

A model's `finish` is not success: without an operator-supplied trusted
`completion_check(fresh_observation) -> bool`, the result is
`stopped / planner_finished_unverified / objective_verified: false`.
A completion checker uses a fresh observation, not model text. A false predicate
feeds failure back for replanning; only a true boolean establishes
`objective_postcondition_observed`. Checkers define acceptance, not action order.
The CLI intentionally has no arbitrary-code checker argument and cannot verify a
free-text Survival objective. Exit 0 can mean a clean **unverified** planner stop;
inspect `status`, `reason` and `objective_verified`, not the process code alone.

## Explicit activation

Requires the rebuilt matching development mod (guarded inventory metadata and
scene `player_uuid`), current SDK and a live, unpaused world. The runtime does not
implicitly resume an existing pause screen. F8 remains the emergency stop.

Offline capability discovery, without a game/model connection:

```sh
.venv/bin/python -m blockwire.agent_cli --describe
```

After ordinary SDK installation, `blockwire-agent` is the equivalent entry point.
Set the existing `BLOCKWIRE_CONFIG` to the selected private Minecraft config.
Use a UUID obtained from that player's ordinary scene observation, not an account
database. Example with an explicitly chosen local OpenAI-compatible server:

```sh
.venv/bin/python -m blockwire.agent_cli \
  --state .blockwire-agent/actor-1/session.sqlite \
  --agent-id actor-1 --world-id my-survival-world --player-uuid "$PLAYER_UUID" \
  --goal 'Acquire tools and a sustainable food supply through normal Survival' \
  --model-url http://127.0.0.1:11434/v1/chat/completions --model my-selected-model \
  --duration 300 --max-decisions 20 --action-timeout 30 --model-timeout 20
```

No model endpoint is inferred from ambient agent/Pi settings. The optional model
credential defaults to `BLOCKWIRE_LLM_API_KEY`, separate from Minecraft credentials;
`--model-api-key-env` explicitly selects another environment variable. Remote
models require HTTPS **and** `--allow-remote-model`: this sends goal, identity,
current game observations and compact history to that endpoint. No redirects,
ambient HTTP proxies or automatic network retries. Native Minecraft WSS/certificate
pinning remains unchanged; localhost model HTTP is not a Minecraft transport.

`--mailbox /private/directory` instead writes a nonce-bound JSON request for an
external LLM host and waits for its matching JSON reply. This is a data handoff,
not a Python/code execution protocol. Do not share mailbox/state directories
between agents. Requests contain private game context; they need retention/rotation
policy for long operation. `--skill-provider NAME` explicitly loads selected
installed trusted extensions; default activation ignores environment provider lists.

`--pause-on-stop` is an optional **development** policy after clean stopping. It is
not part of survival strategy. Without it there is no script-managed pause.
`--stats-file /explicit/player-stats.json` adds saved totals/deltas to the CLI
report; data may lag gameplay and the CLI does not force-save the world.
Keep journals/mailboxes/stats copies out of distributables. `.blockwire-agent/`
and `build/` are ignored; the bundle builder remains allowlisted.

## Actual live qualification

See [scoped evidence](evidence/autonomous-survival-live.json). Used the isolated
Prism client and existing Default-terrain Survival/Normal, commands-off world
**Blockwire Endportal Survival**. This was NOT an autonomous fresh-world start.

1. Explicit developer skill trials collected logs and crafted planks, table,
   sticks and a wooden pickaxe; table placement and held pickaxe were observed.
   These trials tested skills, **not LLM orchestration**.
2. A separate real runtime used an external LLM host via per-request mailbox
   replies. The LLM attempted stone collection; it was blocked by observed terrain.
3. From a fresh context it chose a different useful goal: open the observed
   workbench, craft a wooden hoe using two planks/two sticks, equip it.
4. It stopped explicitly **unverified/incomplete**, not as a finished Survival bot.
   SQLite recorded four action results and `pending: null`.
5. Obsolete actor sessions were separately rejected for inventory open/close/click,
   leaving the paused menu unchanged. Mod replacement preserved config/token/TLS
   identity hashes. No cheats, teleportation or item spawning were used.

The final native observation showed health 20, hunger 17, wooden pickaxe, wooden
hoe (held), one plank and one brown mushroom. A development Save/Quit subsequently
flushed native saved statistics: **world totals**, not attributable run deltas,
were 0 deaths/kills, 8.22 m walked, 1.50 m sprinted, 8 m fallen, 5 HP damage,
4 blocks mined and 19 crafted items. The fall/damage totals include prior probes.
Play time was 212.35 nominal game seconds. Current test client is at TitleScreen;
the world is saved. Save/Quit was operator test cleanup, not an LLM gameplay goal.

This qualifies limited native crafting plus one real LLM replanning slice, **not**
HTTP-provider unattended operation, stone tools, food acquisition/consumption,
farming, independent survival or a no-pause End campaign.

## Automated verification snapshot

- `./gradlew check`: PASS, including inventory protocol/source-order contracts.
- `.venv/bin/python -m unittest discover -s python/tests -q`: **245 PASS**.
- `tests/run_mutations.py`: **32 KILLED** in isolated Java copies.
- `tests/run_skill_mutations.py`: **114 KILLED** (including runtime, model/mailbox,
  crafting output/material proofs, actor guards, durable intent and placement).
- `tests/run_controller_mutations.py`: **20 KILLED**, including the shared food
  consumption contract. `tests/run_end_portal_mutations.py`: **14 KILLED**.
- `tests/tls_interop.py`: **10 PASS**; `git diff --check`: clean.

These 180 targeted mutations are not exhaustive correctness/safety proof. Crafting,
stone-pickaxe and food fixtures are simulated; they do not qualify real stone/food
play. Live artifacts predate subsequent compact-memory/checker/preflight hardening;
those newer boundaries are unit-tested, not a final-source unattended playthrough.
The initial cancellation-check mutant survived redundant child cancellation;
a stronger test now checks that cancellation does not continue observation/decision
cycles. Both the initial result and final killed result remain under the ignored
verification directory. Gameplay pickup failures are also retained, not replaced
by their successful follow-ups.

## Remaining acceptance gates / next implementation order

1. Bounded supported uneven-terrain/step navigation and exposed stone access;
   qualify wooden pickaxe → stone → stone tools in the actual world. Do not remove
   actor fences/support guards simply to get past the current blocker.
2. Food acquisition and actual consumption; hazard-aware retreat/replanning,
   recovery/respawn and resumption after death without replaying uncertain effects.
3. Farming primitives: observed suitable ground/water, native till/plant, visible
   growth state, harvest/replant and independently observed food production.
   **All remain unimplemented**, not merely waiting for a successful demo.
4. Fresh-world LLM wood → stone → food → farm qualification, then longer repeated
   tests of day/night, hostile mobs, terrain changes and interruption recovery.
5. Operational supervision: model outages/cost budgets, state/mailbox retention,
   deliberate actor/dimension handoff, reconnect reconciliation, telemetry freshness,
   process restarts, multi-client isolation and long-duration soak tests.

Furnace creation is a catalogue recipe, not a smelting workflow. General shelter,
resource-aware farming, iron progression and every full Nether/End campaign stage
remain missing. Future multi-agent use requires separate legitimate native actors;
server-side fake-player/entity integration is not supplied by this work.
