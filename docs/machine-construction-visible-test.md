# Visible machine construction attempt — NO-GO

An operator-authorized visible trial used the subscription `gpt-6-luna` route,
provider-native typed calls and the `machine-v1` gateway. No high-level harvest,
crafting or building planner was injected. The goal was natural tree harvesting,
crafting and a small usable house of the model's own design.

## Startup failure retained

`visible-001` stopped during controller binding, before inference or action
admission. The adapter incorrectly expected a motion-trace field named `tick`;
Minecraft actually emits `client_tick`. The simulated backend had repeated that
same incorrect assumption, so the earlier unit tests did not catch the mismatch.
The shipped JAR's field and the Java implementation were inspected. The adapter
now validates native `client_tick` and normalizes it internally; actor fencing,
strict boolean input maps and newer-tick release proof were not relaxed.

The failed client/server were normally closed. Its world, source freeze and stopped
run remain preserved. A fresh instance/world (`visible-002`) used corrected frozen
Python. No uncertain gameplay action was retried; the first attempt admitted none.
The original aggregate request/operation caps and absolute deadlines were retained.

## Actual outcome

- **48 real provider requests**, all completed as single tool calls; no provider
  refusal, fallback or inference retry was reported.
- Decisions:36 plan-note updates,7 waits,2 action calls,2 control calls,1 finish.
- Actions: one explicit two-phase forward/left input sequence and one camera turn.
  Both programs completed with observed native input release. They reserved3
  action operations. The interruption request did not demonstrate cancellation
  of an in-flight held action; do not promote the simulated test to that native gate.
- Closed-save statistics: **8.30m walked**, net displacement about6.11m.
- **No mined blocks, crafted items, used items or pickups recorded.** Final native
  and closed-save inventories were empty. Saved mode remained Survival; health20.
- The spawn was desert. The model spent most calls updating notes about missing
  visible trees, explored only briefly, then returned `finish_session` without
  achieving the objective. This was `planner_finished_unverified`, not success.

The machinery executed the supplied movement/camera calls and delivered events,
but **autonomous tree harvesting/crafting/house construction was not achieved**.
This trial does not qualify native slot-program crafting, crouched placement,
complete building geometry, natural-resource progression or general autonomy.

## Closure and evidence

Both owned clients and all native/gateway/server ports were confirmed closed;
servers exited normally with code0. The second run reported released cleanup,
no native uncertainty and no resource-triggered stop. Resource checks retain the
80% CPU /8GiB available RAM /20GiB free disk thresholds; there is no full continuous
resource time-series or broader capacity claim.

The second replay passed integrity checks (44,046 packets;221,657ms).
**Replay Viewer playback: NOT RUN.** Closed-save checks happened only after verified
shutdown; saves were not supplied to the model. The test was fresh localhost,
offline-identity, Peaceful Survival, without starting materials, generated
structures, OP or gameplay/admin commands; no Microsoft-account qualification.

After the field correction:791 Python tests, Gradle check,10 TLS checks,
14 machine mutations and10 construction mutations passed. These remain separate
from the failed objective outcome.

Public aggregate evidence: [machine-construction-visible-test.json](evidence/machine-construction-visible-test.json).
Private prompts, identities, coordinates, worlds, source freezes and logs remain
under ignored `build/machine-construction/visible-00{1,2}/`. Both scopes are STOPPED;
no resume, replay or release was performed.
