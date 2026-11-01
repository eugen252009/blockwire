# Local wood harvesting (experimental)

`gather_wood` is the first implemented **subgoal**, not the complete
`survival_prepare_overworld` stage or a working End-portal campaign.
It uses existing Python skills and native actions; no new Java primitive, command,
item spawning, world query or movement/mining engine is added.

```python
with Bridge.from_env() as bridge:
    player = Player(bridge)
    result = player.gather_wood(count=1, timeout_seconds=60)
    print(result)
```

MCP exposes its strict schema through `list_skills` and accepts
`run_skill("gather_wood", {"count": 1, "timeout_seconds": 60})`.
The End-portal example also has an explicitly selected one-shot mode:

```sh
# Join/resume the authorized world first. The example pauses after the attempt.
.venv/bin/python examples/end_portal.py --gather-wood 1 --duration 60
```

Add `--no-pause` to omit this example's final development pause; input cleanup
still runs. It does not resume an already paused game or guarantee safety while
the world keeps running.

This mode does not skip a campaign stage or assert that Overworld preparation is
finished. `--run` still refuses to start the full campaign with missing skills.
Reload the Python/MCP host after updating the SDK; no Minecraft JAR update is needed.

## Contract and limits

- `count`: strict integer 1–16, default 1: **additional** logs observed in inventory.
  Existing logs, an attack receipt or a changed crosshair target cannot satisfy it.
- `scan`: strict boolean, default true. At most 17 stopped observations around
  four actor-fenced native 90° elapsed-time targets per search. Repeated samples
  do not restart an identical active target. No executable world text.
- `timeout_seconds`: inherited strict cooperative .1–120-second budget.
- Exact vanilla unstripped log IDs: oak, spruce, birch, jungle, acacia, dark oak,
  mangrove, cherry, pale oak. No translated-name matching or arbitrary mod blocks.
- Candidates come only from sampled visible surfaces, extended sight or native
  crosshair hits. No hidden log search and no interpreting omitted cells as air.
- Stay within six blocks of the activation position on the same flat full-block
  level. Standing destinations must be connected in the loaded native mesh,
  cardinally adjacent to the target column (not diagonally adjacent) and within
  conservative three-block eye reach. Diagonal mining reach alone does not ensure
  pickup proximity; native collection is still independently observed.
  Never stand inside a trunk or mine a support log below feet.
- Travel uses the shared feedback motor and native timed rotation, upright unless
  explicitly changed by another policy; this skill never requests sneak. Stop
  before aiming/mining.
- Require both exact native block target and fresh sight ID/position before
  renewing native attack. Attack holds expire after **six ticks / 300 ms**;
  re-observe between renewals, stop on target loss, give each block at most 12
  cooperative seconds, then require native item pickup within two seconds.
- No leaf clearing, stairs, descent/climbing, jump, swimming, shelter, tool
  selection, crafting or drop chasing over unknown ground. An obstructed aim is
  skipped, not attacked. Inventory cursor/container must be clear.
- Check actor session, grounding/readiness, known danger, initial health and
  cancellation/deadline throughout. Every look/drive is actor-fenced; all terminal
  paths attempt cleanup through the standard skill runner. Damage avoidance is
  best effort, not immunity. No automatic respawn or transport retry.

**Block-target checks are not atomic execution guards.** Another player, human
mouse input, an entity or a block change can occur between observation and native
attack execution. This is a short, supervised local harvesting experiment, not a
promise never to touch an adjacent block/entity. Native Minecraft owns reach,
block hardness, tool effects, physics, drops and pickup.

On `no_reachable_exposed_logs`, details include up to 16 nearest observed log
positions from that stopped scan. These are diagnostic visible observations, not
a persistent world map, a supported route or permission to move over unknown
terrain. Other blocked reasons include `wood_not_collected`, `mining_not_observed`,
`damage_observed`, `known_danger_nearby`, and `actor_session_changed`.

## Qualification

`python/tests/test_woodcutting.py` covers positive simulated mining/collection,
existing inventory, missing pickup, stale/occluded/wrong-position hits, support
protection, no route, actor replacement, health/danger/fire, cancellation/deadline,
strict validation, sparse run decoding and stopped scanning. These fixtures do
**not** establish real Minecraft harvesting.

In **Blockwire Endportal Survival**, a real attempt scanned from the unchanged
spawn `[-18.5,77,10.5]`, discovered distant lower logs and returned
`blocked/no_reachable_exposed_logs`. Inventory remained empty, health remained 20,
no drive input was submitted, controls released and the final menu was PauseScreen.
That prior trial confirmed discovery/unsupported-route stopping, **not successful
wood harvest**; its [evidence](evidence/gather-wood-live.json) is preserved.

In a later separately authorized live test with death explicitly permitted, a raw
native descent probe fell from Y77 to Y69 and caused five damage without death.
This was **not** supported/automatic terrain navigation. A ten-second wood attempt
then timed out, and a subsequent ground attempt returned `wood_not_collected`.
After restricting standing cells to cardinal adjacency, a separately inspected
trial observed inventory growth from zero to **one dark oak log**, with 28 native
attack holds, no movement during that successful activation, health 20, released
controls and a final PauseScreen. The successful target differed from the failed
pickup target, so this is not a controlled causal comparison. Collection is
verified; exact attribution to the last block versus an earlier dropped log is not.
See [follow-up evidence](evidence/gather-wood-followup-live.json).

This establishes one supervised native collection, not repeated harvesting,
autonomous descent/recovery, crafting, Nether progression or no-pause completion.
General terrain navigation remains a campaign blocker; the skill's flat-ground,
health and supported-route guards were not weakened.
