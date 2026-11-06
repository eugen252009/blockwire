# Explicit 64-log goal over MCP — NO-GO

The operator requested a clearer Minecraft task over MCP. A fresh visible
Peaceful Survival world and isolated client were used; no stopped world or ledger
was resumed. The model received a direct German execution goal: collect at least
64 natural, unprocessed logs in its inventory, actively explore observed traversable
terrain, do not repeatedly rewrite notes, and do not craft or build yet. A tool
receipt or a ground drop does not satisfy the inventory goal. Safety stops and
unknown/no-retry handling remained unchanged.

The route was real: provider-native tool calls → bounded host → external Python
MCP `ClientSession` over stdio → `blockwire.machine_mcp` → authenticated `machine-v1`
TLS gateway → native Minecraft. The host discovered the MCP tools and compared
primitive schemas before admission. It consumed independent reports through the
MCP event inbox; it did not plan routes or replay actions. Limits were 30 minutes,
100 model calls and 1,000 action operations, with the existing resource gates/F8.

## Observed result

- 41 real `gpt-6-luna` requests:38 action decisions and3 waits; no plan-note calls.
- Requested actions: 36 turns, 1 five-second attack hold and 1 input sequence.
- 37 programs were admitted. The final input sequence failed before BCL JSON
  transmission.39 operation units were reserved, including that failed admission.
- The model repeatedly aimed at an observed acacia trunk about13.6m away instead
  of approaching it. Extended sight was explicitly labelled as not interaction
  reach. No causal claim about the model's internal reasoning is made.
- Closed-save inventory: **empty, 0/64 logs**. No mined blocks or pickups were
  recorded. Walk distance and net displacement were0m; Survival mode and health20
  were retained.

The sharper goal eliminated the note-writing loop in this attempt, but did not
produce resource collection. Different world conditions and the MCP interface
mean this is not a controlled prompt-effect experiment.

## MCP defect and correction

FastMCP preserves nested Pydantic values in handler keyword arguments. The machine
facade passed `InputPhase` instances directly to the BCL client's JSON encoder,
which raised `TypeError: Object of type InputPhase is not JSON serializable`.
A new MCP-handler + real-TLS regression test reproduced the failure without
Minecraft or inference. The facade now validates parameters against the same
registry model and converts them with `model_dump(mode='json')` before sending.
Strict validation, action bounds, actor fencing and transport security remain.

After correction: 792 Python tests, Gradle check, 10 TLS checks, 14 machine mutations
and 10 construction mutations passed. **Post-fix real gameplay: NOT RUN.** The
failed live sequence was not retried, and the frozen trial sources remain intact.

The host did not obtain its final release receipt and retained its unknown/no-retry
classification. The gateway later recorded session release on disconnect; this
must not erase the missing host receipt. Owned client and server processes and
all three ports were confirmed closed; the server exited normally. Saved-state
inspection was read-only after shutdown. Replay Viewer playback: NOT RUN.

[Aggregate evidence](evidence/mcp-wood-visible-test.json). Private goal, discovery,
MCP request log, prompts, source freezes and world remain under ignored
`build/mcp-wood/visible-001/`; checks are under `build/mcp-wood/checks/`.
