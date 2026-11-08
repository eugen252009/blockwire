# Model-owned Survival gameplay: hidden-001

**Result: NO-GO — 0/8 logs; no harvesting or inventory gain.**

This was an actual graphical Minecraft run with 40 real `gpt-6-luna` requests,
not a simulated planner test. The model chose its own observations, camera
points, movement and stopping decision. No route or action sequence was
prescribed, and no host planner selected resources or performed gameplay.

## Scope

Fresh normally generated, localhost-only, whitelisted Peaceful Survival world;
empty inventory; no fixture, selected spawn, relocation, item grants, rescue or
respawn. An authenticated hidden display with an owned unmapped parent was
verified against the actual JVM before native connection; no TCP display
listener or visible fallback. The matching development JAR was installed only
in the owned instance.

The first milestone was **eight unprocessed logs in the player's inventory**,
not merely visible logs or input receipts. Limits: 1,800 gameplay seconds,
100 model decisions, 1,000 counted operations and a 2,400-second outer envelope.
Each search reserves 34 pages against the same operation budget as primitive
actions. CPU/RAM/disk admission and ongoing gates remained active, including
the tight 20-GiB free-disk floor. These limits are not financial/token guarantees.

Production code was unchanged. The working tree was not a pristine checkout;
existing independent work and earlier evidence were preserved. Private helpers
used the production machine agent and a narrowly adapted MCP client, not a
second gameplay planner. Native actions/search crossed external MCP stdio →
`machine-v1` TLS → Minecraft. The two cached `look_around` reports were derived
by the production agent from MCP-delivered events, not fresh MCP/native queries.

## Observed execution

| Item | Result |
|---|---:|
| Actual model requests | 40 |
| Native primitive programs | 5: four turns, one forward input sequence |
| Forward-input duration | 1.5 seconds |
| Targeted searches | 29; all `target_not_seen` |
| Cached overview reports / waits / finish | 2 / 3 / 1 |
| Native search pages / reported rays | 986 / 93,035 |
| Distinct native search view tokens | 4 |
| Reserved search pages + action operations | 986 + 5 = 991 |
| Operations remaining at finish | 9 |
| Saved walking statistic | 447 cm = 4.47 blocks |
| Net 3-D displacement | 4.8662 blocks |
| Saved inventory / mined blocks / picked-up items | empty / none / none |
| Final mode / health | Survival / 20 |

Every search used model-selected `target="logs"`, `range=64`,
`cone_degrees=90`, `timeout_seconds=30`. The model repeatedly searched without
material progress. It eventually requested `finish_session` itself, citing the
remaining budget and lack of a sufficient basis to collect eight logs. This was
**not** a forced budget error or an assertion that the goal had succeeded. The
host did not substitute a route, aim point or mining action to rescue the run.

The five program completions establish their bounded action postconditions,
not harvesting success. Negative sampled searches do **not** prove that logs
were absent, invisible in pixels, or unreachable elsewhere.

## Verification and closure

Ten private offline/real-stdio host contracts passed, including production-agent
search/action budget accounting, nested parameter transport, pre-dispatch guards,
in-flight search cancellation and no reconnect. Three isolated adapter guard
mutations were killed. A provider-route probe used zero inference calls. These
host simulations are separate from the graphical run.

After verified shutdown, an independent auditor reconciled:

- Source/JAR/helper freezes and the actual hidden JVM identity.
- All 40 provider replies against dispatched decision arguments and the goal.
- Search-page identity, order, counters, empty aggregation and durable budget
  reservations; **not** every world-ray collision or proof of absence.
- Native initial/final inventory against the closed player save, saved movement,
  mining and pickup statistics, Survival mode and health.
- Normal overworld generation/no bonus chest and absence of setup commands.

Inventory stayed empty. The model's own report was not acceptance evidence.
Input cleanup was `released`, uncertainty was false, and all owned client/server
processes, ports and the hidden display closed. The server exited normally.
Replay finalization/integrity passed (63,392 packets; 276,023 ms); interactive
Replay Viewer review was **NOT RUN**. The scope is `STOPPED`, never resumed.

This run does not qualify autonomous forestry, arbitrary-spawn exploration,
crafting, building, ordinary-MCP graphical search, live held-input interruption,
or the historical 64-natural-log goal. Earlier positive stationary perception
results remain separate: [model-selected perception](search-model-test.md).

Public manifest: [evidence/mcp-play-hidden-test.json](evidence/mcp-play-hidden-test.json).
Private worlds, coordinates, identity, prompts and captures remain under ignored
`build/mcp-play/hidden-001/`. No push, release or general client deployment.
