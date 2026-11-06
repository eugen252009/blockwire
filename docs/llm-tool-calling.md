# Typed LLM tool calls

For the new **lean action + independent event** architecture, use
[the machine profile](bcl-machine.md), `blockwire.machine_mcp` or
`blockwire.machine_agent`. The skill-centric adapters below remain compatible
legacy interfaces; `gather_wood` and other goal skills are NOT machine primitives.

The autonomous model need not generate BCL. There are two entry points over the
same strict Python skill registry, not two planners:

- **MCP hosts:** `blockwire-mcp` advertises `skill_gather_wood`, `skill_craft_item`,
  `skill_walk_to`, etc. Each tool has the complete skill JSON Schema (types,
  required fields, bounds, enums and forbidden extra properties). Existing tools,
  including `run_skill`, BCL, status and cancel, remain compatible.
- **Standalone `blockwire-agent`:** an explicit `--llm-url` and `--model` now use
  native chat/completions function calls by default (`--model-interface tools`).
  The provider receives the host-authorized skill schemas in `tools` and returns
  exactly one call, e.g. `gather_wood` with `{"count":1}`. The adapter validates it
  and hands it to the existing AgentRuntime. It does **not** open an MCP connection;
  it uses the identical registry contracts directly. `--model-interface json`
  selects the legacy JSON-decision adapter. The mailbox interface is unchanged.

Example MCP call:

```json
{"name":"skill_gather_wood","arguments":{"count":1,"timeout_seconds":30}}
```

This starts a background job. Poll `skill_status(job_id)` for the observed result;
use `cancel_skill(job_id)` to request cancellation, then confirm terminal cleanup.
No success is inferred from a job receipt. Tool calls do not use BCL modal homes:
coordinate arguments refer to native world coordinates.

## Authority and failure boundaries

Tool definitions are generated from trusted, explicitly selected installed skills,
not game text or model-supplied schemas. No implicit plugin loading is added.
MCP's existing shared job exclusion, ownership, cancellation and native fences
remain in force. The standalone agent retains its durable pending-action journal,
identity checks, deadline/decision/failure budgets, fresh-state revalidation and
cleanup. Each model request selects at most ONE action; parallel calls are rejected
in full before any dispatch. Tools cannot provide an executable script.

The model chooses goals and ordering; the host supplies no wood/table/tool route.
`finish_session` only proposes stopping; observed postconditions are still needed
for success. `wait_for_observation(seconds)` is bounded to0.1..5 seconds.
Fresh observations and structured result history are included in each new decision.
This is a bounded, stateless provider request per decision, not a provider-managed
multi-call conversation. No provider tool-call ID is treated as action deduplication.

Refusals, truncation, unsupported provider tool calling, unknown transport results
and malformed calls fail closed. No textual/BCL fallback, automatic inference
retry, native action replay, reconnect or respawn is introduced. The previous
isolated recovery experiment is not silently merged or reused as qualification.
Model endpoint disclosure remains explicitly authorized; TLS, no redirects/proxies,
request/response bounds and credential handling are unchanged.

**Controlled MCP policy is deliberately unchanged:** the existing default private
feedback allowlist denies new `skill_*` tools, just as it denies `run_skill`.
Operators must explicitly authorize exact tool names in `InputPolicy.allowed_tools`
to use them in that profile. No alias inherits BCL permissions or bypasses denial.
MCP tools retain existing job semantics; they do not acquire the standalone agent's
durable budgets simply by being advertised. Do not substitute them into a historical
campaign ledger without a newly qualified host/admission path.

## Verification boundary

Validation on this checkout: **758 Python tests**, `./gradlew check`, TLS interop
and **6/6 isolated tool-boundary mutations killed**. This checkout does not silently
include the separately frozen Fn/recovery worktree; its earlier813-test total
belongs to that different source scope.

Contract tests exercise real MCP schema validation/dispatch, provider request shape,
strict argument rejection, single-call execution and the existing AgentRuntime's
fresh observed results. No external provider inference or graphical Minecraft run
is claimed. The prior Survival NO-GO evidence is unchanged. Tool calling removes
the BCL-generation requirement; it does not prove reliable planning or gameplay.
