# Machine construction capabilities — not autonomous gameplay qualification

This extends the action-only `machine-v1` profile so an LLM can express the
mechanics needed for harvesting, native crafting and player-built structures.
It does **not** install a wood → table → tool → house progression, tree search,
route planner, building template, automatic retries or a second planner.

## Added mechanics

- `turn` / G2 accepts **either** yaw/pitch **or** an explicit world-space `point`.
  Python performs only eye-to-point angle conversion. The caller chooses the point;
  native rotation is observed before completion. No approach or target selection.
- `input_sequence` / G3: up to16 explicit phases, total requested duration≤30s,
  command deadline≤35s. Each phase supplies a complete button mask; common keys
  remain owned across phase boundaries. Each renewal is still≤6 ticks and guarded
  by actor, health, deadline and cancellation checks. There is no stop between
  phases; final cleanup releases inputs. Network/tick stalls can still interrupt
  continuity; this is not a real-time timing guarantee.
- A phase may perform one explicit camera aim OR one attack/use press. An aim must
  reach its stated angular postcondition before the next phase. A one-shot press
  cannot be combined with held attack/use keys. Optional exact block/position/face
  preconditions stop on a changed target; these are client prechecks, **not an
  atomic native target transaction or proof of placement**.
- `slot_program` / M6: up to16 explicit pickup clicks, with caller-specified slot
  and cursor **before and after** assertions. It reads fresh menu state IDs for
  each click, verifies the assertions before advancing, and never repeats a click.
  At least one asserted stack/cursor delta is required. Include native result/grid
  checks when relevant; it does not invent recipe or consumption assertions.
- Closing an inventory with an observed nonempty cursor or supported crafting grid
  is blocked. Cancellation/failure does not close or repair partial inventory state.

A crouch-placement sequence can now be expressed as: hold Sneak; aim at a chosen
support face while keeping Sneak; check that exact target and issue one use press;
release. There is no hidden equip, support substitution, movement or retry.
Long attack phases can express mining without repeated model-generated clicks;
the caller must observe block changes and actual inventory pickup separately.
A target disappearing can stop a guarded phase even when a desired block broke:
command failure/success is not the external harvesting goal.

## Native crafting, not inventory synthesis

The LLM selects a recipe and source/grid/output slots from events. `slot_program`
merely executes its explicit slot instructions and assertions. It never selects
materials, fills a grid itself, opens a workbench remotely, spawns items or computes
Minecraft's crafting result. Exact menu/state fences and Minecraft slot handling
remain authoritative. No quick-move heuristics are hidden in this primitive.

Stack assertions currently cover registry ID and count, **not arbitrary item NBT,
components or enchantments**. Menu IDs are guards, not atomic server transactions.
Client-observed postconditions can be superseded by subsequent server updates.
A precondition mismatch issues no click. An unconfirmed post-click effect stops
and quarantines execution (`inventory_effect_not_observed`); queued work must not
continue. No automatic recovery/reconnect/rollback follows.

## Independent perception and model-owned planning

`state.crafting` reports the current native menu/grid/result/cursor plus a limited,
labelled **host vanilla reference catalogue**. This is not native recipe discovery
or a complete/modded recipe database. Planks, tables, sticks, basic tools and useful
building recipes (chests, wooden doors, slabs and stairs) are descriptive data only.
The native result slot must confirm any proposed recipe before taking its output.

The machine MCP host enables initial scene/inventory/navigation/crafting reporting
itself and waits for initial snapshots. Reporting continues while actions execute.
The standalone agent consumes the same four state channels, not observation opcodes.
Neither path queries saves, NBT or arbitrary hidden world coordinates.

`remember_plan(notes)` keeps up to4096 characters of model-authored working notes:
chosen geometry, materials, observed progress and pending steps. These notes remain
unverified data, not executable code or evidence. The standalone host records them
privately and includes them in later decisions; the MCP host keeps them in its
current process. Restart does not resume old work. No default house shape is supplied.

The standalone action budget counts each slot-program click and input phase, plus
explicit phase looks/presses. Defaults remain20 model decisions/100 operations/600s;
no resource/request budget is silently raised. Longer work requires explicitly
selected limits (existing ceilings100 decisions/1000 operations/1800s), a fresh run
and operator authorization. Machine tool replies request up to4096 output tokens;
this is not a guaranteed financial/token cap. Argument/frame/queue bounds remain.

## Qualification boundary

Deterministic tests cover a model-specified five-click log-to-planks program with
observed output/consumption in a **simulated native menu**, retained-key phases,
aim completion, target/actor rejection, no click replay, uncertainty quarantine,
expanded operation accounting, automatic MCP reporting and data-only plan notes.
The integration uses real authenticated loopback TLS with a simulated backend.

Final checks: **790 Python tests PASS**, Gradle check PASS, **10 TLS checks PASS**,
**10/10 construction,14/14 machine and6/6 tool mutations killed**.
See [source-scoped contract evidence](evidence/machine-construction-contracts.json).

**A [visible real-model attempt](machine-construction-visible-test.md) completed NO-GO:**
48 model requests, two successful movement/camera programs, but no collected wood,
crafting or house. A pre-inference native tick-field mismatch was corrected; the
failed first scope was not resumed. Natural-resource construction remains unqualified.
A subsequent [explicit 64-log goal over real MCP](mcp-wood-visible-test.md) also
failed (0 logs). It exposed a nested-parameter JSON serialization defect, now
regression-tested and corrected; post-fix native gameplay remains NOT RUN.
A successful command or a model saying “finished” still cannot certify a house.
An isolated graphical acceptance must independently check natural material
progress, the chosen structure, access/interior/roof, cleanup and saved results.
The prior [machine contract evidence](evidence/bcl-machine-contracts.json) remains
historical and is not rewritten to qualify these additions.
