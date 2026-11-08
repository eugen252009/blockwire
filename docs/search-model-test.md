# Search — model-chosen tests in a fresh natural world

**SCOPED PASS: model-chosen, stationary natural-world perception.** Unlike the
previous prescribed [fixture sequence](search-hidden-test.md), this run gave the
real LLM a testing objective and limits, **not a tool order, camera angle, search
parameters, target coordinates or expected hits**. The model chose its own tests.

## Fresh scope and bounds

`build/search/model-001/` used a fresh normal-world server, fresh offline identity
and an owned authenticated hidden display. The seed property was left blank;
closed-save settings confirmed normal noise generation, not the flat fixture.
There was no console setup, chosen spawn, relocation, placed test block, granted
item or gameplay intervention. The model was limited to perception and camera
rotation: no walking, harvesting or building. The actual owned JVM/display was
verified before connection, with no visible fallback or unrelated window action.

The production runtime/JAR was unchanged from the qualified `a7462ff` feature
baseline. Private harness changes removed the fixture and fixed test sequence,
exposed remaining budgets/already-cached scene metadata, allowed two camera turns
and checked the remaining deadline before tool dispatch. Eight offline host tests
and three isolated guard mutations passed before launch. The provider-route probe
made zero inference calls. Source/JAR/harness freezes and raw captures are private.

Limits:480seconds test time /900seconds outer lifecycle; six model calls, three
searches (102 reserved-page maximum), two turns and one `look_around`. CPU≤80%,
RAM≥8GiB and disk≥20GiB gates remained active. No hard financial/token ceiling.

## What the LLM actually chose

Five real `gpt-6-luna` requests used real MCP stdio→machine-v1 TLS→native Minecraft,
without provider retries or action replay. Arguments were passed through unchanged.

| Model decision | Observed result |
|---|---|
| `look_around()` | Cached report: no central anchor |
| `search("logs", range=64, cone_degrees=90, timeout_seconds=20)` |13 `minecraft:spruce_log` blocks, surface distances12.676–21.739 blocks |
| `turn(yaw=45, pitch=0, duration_ms=300)` | Native angular/release postcondition observed |
| Same search parameters from the new view |18 spruce-log blocks, distances10.530–39.717 blocks; **five additional distinct blocks** |
| `report_test` | Model ended with its own explicitly unverified German summary |

The union was **18 distinct log blocks**, not31 blocks,18 trees or18 harvested
items. Each search traversed34 pages: **68 pages and6,417 native rays** total
(3,209 then3,208). Native sampling intervals were4.692s and4.800s, not a general
performance claim.

The underlying coarse sample did contain four log positions, despite the filtered
`look_around` report lacking its required central anchor. Ten of the first search's
13 positions were absent from that cached coarse sample. The samples have different
timestamps; this is not exhaustive coverage or a guaranteed dense-sample superset.

## Independent reconciliation and limits

After verified shutdown, the audit matched provider responses to actual decisions,
page arguments, actor/view identity, aggregation and source times. It independently
checked positive-hit distances, cone membership, full-cube log surfaces/faces and
all18 block IDs/positions against the closed save. Native cached angular state
sampled after release independently confirmed the camera result. The model's
summary was **not** acceptance evidence.

The offline auditor needed three corrections: decode Java-properties colon
escaping; recognize Minecraft26.3's compact empty-key compound palette entries;
and check native camera angles rather than assuming its quantized view vector
exactly matches Python trigonometry. Initial failures and auditor versions remain
retained; the palette decoder passed three synthetic unit tests. **No gameplay
run, production source or frozen capture was altered/replayed.** The existing
shared Anvil helper was not silently modified.

Unlike the synthetic fixture audit, this audit does **not** reconstruct every
world collision/ray or establish pixel-complete visibility. It qualifies the
reported positive observations for this one model-chosen stationary case, not
absence, natural-tree provenance, reachability, walking/exploration, harvesting,
64 logs, crafting or building. Ordinary-MCP graphical acceptance, live search
interruption and interactive Replay Viewer review remain **NOT RUN**.

Native and saved positions were unchanged, inventory empty, health20; saved
walking/mining counters were zero. Controls were released, `unknown=false`, and
all owned client/server processes, ports and the hidden display were closed.
The scope is **STOPPED**, not resumable. Historical evidence is unchanged.

[Redacted evidence and hashes](evidence/search-model-test.json).
