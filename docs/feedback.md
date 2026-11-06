# Feature feedback and controlled LLM inputs

Opt-in host-side Blockwire service, not Java-side planning or a new transport.
Minecraft/Fabric still owns observations, native actions and input leases.
Python owns descriptive requests, admission policy and private audit persistence.

## What a request means

An LLM can submit a strict `feature_request`, `capability_gap` or `failure_report`
with a title (120 characters), description (2048), optional capability name (128)
and optional claimed evidence request ID. Unknown fields are rejected.
The description is **untrusted data**, not code, BCL, a shell command, permission,
an installation instruction, or proof of a gameplay outcome. Do not include secrets.

A committed SQLite ticket starts at `pending_review`. Only a local operator CLI
can mark it `planned` or `declined`; neither changes code, capabilities, budgets,
plugins or Minecraft. No automatic feature generation/install/deployment is added.
There is no operator-review MCP tool, peer broker, shared LLM context or relay.

## Enable a gateway

```python
from blockwire.bcl.gateway import BCLGateway
from blockwire.feedback import InputPolicy

gateway = BCLGateway(player, token, state_directory,
    feedback_directory=private_instance_directory / 'feedback',
    input_policy=InputPolicy(max_session_operations=300,
                             max_actor_operations=1000))
```

Or pass `--feedback-directory /explicit/private/path` to the existing gateway CLI.
The final directory must be private (0700); the SQLite file is 0600. This is a
per-instance store: its aggregate operation budget spans **all** session, agent
and world labels in that store, so a client cannot reset it by inventing labels.
Do not point independent instances at one directory unless that shared budget is
intentional. Storage/identity selection is trusted operator configuration, never
an LLM-supplied path. This is not a sandbox for trusted Python.

The normal authenticated TLS gateway lease/bind is required. Bind advertises
`feedback_supported` and `input_policy`. Native UUID/actor checks precede writing.
No new socket or BCL opcode/grammar is introduced:

```python
receipt = await client.request_feature('tree-access-01', {
    'category': 'capability_gap',
    'title': 'Cannot reach observed logs',
    'description': 'Report the observed limitation and desired bounded behavior.',
    'requested_capability': 'tree_access',
})
status = await client.feedback_status('tree-access-01')
```

These use control envelopes `feedback` / `feedback_status`, with ordinary
`request_id` response correlation and a separate scoped `feedback_id`. The latter
is the durable proposal deduplication key, not a BCL action request ID. Same
proposal/key returns its existing ticket; changed content conflicts. Another
agent/session cannot query it. No missed messages/events/actions are replayed.
An uncertain connection is terminal **UNKNOWN_NO_RETRY**: do not reconnect/resend
blindly; an explicitly authorized new activation may reconcile via a read.

## Input accounting and control

Enabled gateways privately record bound client inputs, including raw bounded BCL
source, proposal bodies, admission/rejection and asynchronous BCL terminal status.
Only selected control fields are retained, never authorization headers/keys.
Oversized audit bodies are replaced with a digest/size marker, not silently clipped.
Compiler permissions and complete-frame validation still precede effects.
An optional opcode allowlist and limits of 32 operations/frame, 300/session and
1000/store apply before scheduling. Accepted reservations persist before dispatch,
including conservative charges for work that subsequently fails; they are **not
executed-action or gameplay-success counts**. Same request/source is charged once;
changed-source reuse conflicts. Reconnect, new labels and modal reset do not erase
the aggregate budget. Existing actor fences/deadlines/leases remain unchanged.

Storage is bounded: 10,000 audit records, 1000 proposals, 20 proposals/session and
32 MiB SQLite page budget (plus bounded SQLite transaction overhead). Full or
unavailable audit storage fails closed for new work. Cancel and own feedback
status remain usable; native F8 is independent. There is no model-accessible
reset/rotation/unlimited-budget switch. Archive/review and explicitly select a
new activation/store when an operator intends a new budget.

## MCP

Opt in with trusted `create_server(feedback_directory=..., feedback_identity=...)`;
identity has exact `agent_id`, operator `world_id` and expected native `player_id`.
For stdio CLI use `BLOCKWIRE_FEEDBACK_DIRECTORY`, `BLOCKWIRE_AGENT_ID`,
`BLOCKWIRE_WORLD_ID`, `BLOCKWIRE_PLAYER_ID`. Native TLS config remains separate.
Without opt-in, feedback tools report disabled and existing controls are unchanged.

`request_feature` requires the current explicit `actor_session` and checks a fresh
native UUID/session snapshot. `feedback_status()` without an ID describes policy;
with an ID it reads only this configured agent's request. Requests never pause an
active task or trigger another model call.

Enabled MCP audits validated tool calls and schema/unknown-tool rejections. Raw
menu text, slash commands and chat text are represented by digest/length, not
retained plaintext. Feature descriptions and BCL source are retained privately;
these are **not** a complete native keyboard/action or server-outcome recorder.
The default controlled profile allows BCL discovery/execution, observations,
feedback, status/cancel and stop, but denies raw commands, menu automation and raw
mutating convenience tools. BCL identity must equal the configured identity.
Operator-selected immutable `allowed_tools` / `allowed_opcodes` can narrow authority;
explicit `allowed_tools=None` retains broader existing MCP tool authority.
BCL operation budgets apply to `execute_bcl`, not individual internal native pulses.
Stop/cancel/status remain available when audit capacity is exhausted. No reduction
of authority of separately authorized raw native clients is claimed.

## Operator review

```sh
PYTHONPATH=python/src .venv/bin/python -m blockwire.feedback --directory /private/feedback
PYTHONPATH=python/src .venv/bin/python -m blockwire.feedback --directory /private/feedback --inputs --limit 20
PYTHONPATH=python/src .venv/bin/python -m blockwire.feedback --directory /private/feedback \
  --ticket TICKET --review planned --note 'Reviewed; implementation requires separate work'
```

Protect/exclude databases, model inputs, identities, worlds and recordings from
Git/distribution. Review is local JSON data display only, not an instruction to
execute proposed code. Old evidence and source freezes are never regenerated.

## Qualification

`python/tests/test_feedback.py` covers persistence/dedup/scope/schema/privacy,
per-frame/session/aggregate admission, raw-tool denial, actor replacement, task
coexistence and cancel under audit exhaustion. TLS tests use a **simulated** native
backend, not Minecraft acceptance. Long-term autonomy and uninterrupted two-hour
or overnight gameplay are separate gates; a deadline is an upper bound and never
suppresses failure/resource stops. The [early implementation/native evidence](evidence/feedback-system.json)
records the first real actor-bound tickets and independently model-generated
requests, not a completed two-hour verdict. Live/final per-agent results are under
`build/feedback-system/trial-R01/agent-*/result-private.json`; the supervisor closes
only the owned clients/server and never force-kills a save.
