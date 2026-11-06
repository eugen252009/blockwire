# `look_around`: real-model hidden-display test

**SCOPED PASS** for missing-anchor reporting and positive sampled-block geometry.
This is not forestry, building, complete visibility or general gameplay acceptance.
[Machine-readable evidence](evidence/look-around-hidden-test.json).

## Method

Three separate fresh offline-identity Peaceful Survival clients/worlds, empty
inventories and no generated structures or gameplay/admin commands. An actual
`gpt-6-luna` subscription model selected provider-native tools discovered through
real MCP stdio; the machine gateway used mandatory authenticated TLS to Minecraft.
Only `look_around`, at most two camera `turn` calls and a host-only unverified
`report_test` were offered. No movement, mining, crafting or resource planner.

Authenticated nested displays `:109`, `:110`, `:111` had unmapped owned host
parents and no TCP listeners. Actual Minecraft JVM display/cwd/identity was checked
**before** native connection; no fallback to `:0`. Software OpenGL was used.
30 FPS in the first case and 15 FPS in the next cases: **no performance comparison**.
Each case was bounded to six model calls, three view reports, two camera actions,
480 seconds of testing and a 900-second outer lifecycle. Existing CPU/RAM/disk
admission/monitoring gates remained; no hard financial/token ceiling is claimed.

## Results

| Case | Model calls | `look_around` calls | Result |
|---|---:|---:|---|
| hidden-001 | 5 | 3 | Correctly returned `crosshair_anchor_not_observed`; one camera turn, no invented distances. |
| hidden-002 | 1 | 0 | Model omitted yaw in a pitch-only `turn`. MCP rejected it before native dispatch. Terminal failure retained. |
| hidden-003 | 4 | 2 | Model supplied yaw 0° / pitch 75°. Both reports returned two `minecraft:grass_block` samples at **2.120** and **2.344** blocks from the eye. |

The positive reports came from separate scene samples 2.4 seconds apart, both
with the requested camera orientation. Independent code decoded the captured
native surface runs and recomputed candidate membership, 30° full cone, 10×10
X/Z window, angles and distances without calling the production filter. Every
returned block belonged to the bounded source observation; all five delivered
reports passed their applicable arithmetic/missing-anchor checks. The model's
own summary was retained as unverified text, not used as acceptance evidence.

Cases 001 and 003 confirmed matching-generation input release and unchanged
player position/inventory. Case 002 remains `cleanup=not_confirmed`, `unknown=true`:
the gateway's later released state does **not** replace the missing host receipt.
All owned clients, servers, ports and nested displays subsequently closed.
Stopped cases were not resumed, replayed or silently repaired.

## Limits and evidence

This qualifies the **machine-MCP cached-event** path in these native views, not
fresh-query latency, every angle/terrain, entity reporting, arbitrary spawn
navigation or resource collection. No rendering/pixel equivalence, complete map,
reach or safety claim. Replay Viewer review: **NOT RUN**.

Private prompts, raw scene coordinates, worlds, captures and source freezes stay
under ignored `build/look-around/hidden-001/` through `hidden-003/`.
`build/look-around/audit_hidden.py` records the independent arithmetic.
No production implementation was changed during these tests. The existing
809-test Python, Gradle, TLS and isolated mutation checks remain source-scoped;
this native report adds evidence rather than rewriting older failures.
