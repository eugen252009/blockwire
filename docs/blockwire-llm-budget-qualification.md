# Subscription model-request limits — qualified operational scope

The operator's second attachment explicitly supersedes mandatory hard token/cost
reservations **for this GPT-6-luna subscription cooperation experiment only**.
This is not a qualification of financial budgeting, unlimited subscription use,
other providers, local models, or the separately blocked eight-hour soak.

## Actual integration

- Exact model: `openai-codex/gpt-6-luna`, pi `ModelRuntime.streamSimple`.
- Existing stored OAuth; pi reports `isUsingOAuth=true`,
  `isUsingSubscription=true`, auth source `stored`.
- Existing `openai-codex-responses` route:
  `https://chatgpt.com/backend-api`. No extracted/copied credentials, new API key,
  separately billed API endpoint, provider substitution, tools, extensions,
  compaction, automatic agent retries or peer-model memory.
- Two independent requests succeeded concurrently in each of two separate
  controlled cohorts: `subscription-001` and `subscription-002`, two requests each.
  Actual attempt overlap: 1,848 ms and 1,718 ms respectively; HTTP 200 and requested
  model/provider identities verified. The second cohort preserves original model
  JSON for the parent's existing duplicate-key rejection.
- Each cohort rejected an extra request **before dispatch**, retained exactly two
  charged requests, and reloaded the same persisted deadline and accounting.
- SSE is selected explicitly, provider retries are zero. Provider/quota errors
  stop the affected model scope; no fallback, reconnect or automatic retry.

**Billing qualification is conditional, not an invoice guarantee.** The supported
SDK identifies this as the existing subscription route; no new metered API access
was introduced. Account invoices, credit/top-up settings and unlimited future
quota were not audited. Returned `usage.cost` values are catalog estimates
(`totalFromProvider=false`), not evidence of additional charges or zero charges.
Provider limits remain applicable and are not bypassed.

## Central operational boundary

`python/src/blockwire/model_limits.py` adds a small opt-in `ModelLimits` and
`LimitedDecider`. One private SQLite database contains the campaign and **both**
agent scopes, immutable configuration, model reservations, optional usage
telemetry, operation admissions and bounded events. `BEGIN IMMEDIATE` covers
read/check/reserve; full synchronous commits precede dispatch. Separate threads
and processes contend for the same capacity. An agent cannot borrow its peer's
allocation. This trusted host API is **not a sandbox** against arbitrary owner
Python or a global monkeypatch of model libraries.

Configured cooperation limits:

| Limit | Per agent | Campaign |
|---|---:|---:|
| Model requests / decisions | 30 | 60 |
| BCL operations, including host subscription queries | 300 | 600 |
| Runtime | at most 30 minutes | one persistent 30-minute deadline |
| Concurrent model requests | one sequential loop | 2 |
| Reserved end-to-end inference time | 1,800,000 ms | 3,600,000 ms |

Each request reserves at most 90,000 ms and must fit before the campaign deadline.
The SDK aborts at 85 seconds; its subprocess is killed/waited at 90 seconds. This
bounds the owned host worker, **not unknowable remote compute after disconnect**.
A completed request releases only measured unused inference time; request counts
are never refunded. Timeouts, interrupted/malformed responses and uncertain
outcomes retain their maximum time charge and concurrency slot and halt that
agent. An independent healthy peer can continue within its own allocation.

Stable request IDs cannot dispatch twice or change identity/context. Duplicate
reconciliation cannot rewrite consumption. Explicit restart recovery marks
unfinished requests `UNCERTAIN`, retains charges and never replays them. Reloading
or restarting cannot reset configuration, consumption or deadline. Stop remains
available when the bounded audit fills. Storage is private, owned, nonsymlink,
rollback-journal SQLite, bounded to 16 MiB and 2,000 events.

BCL counts come from complete trusted-host compilation, not model declarations.
The existing gateway input policy independently retains its actor/session limits.
No BCL opcode, native movement, dispatcher, TLS protocol, certificate identity,
actor fence or lease was changed for this task.

## Token accounting: deliberately not hard-qualified

The actual Codex adapter did **not** send an output-token ceiling despite the SDK
`maxTokens: 2048` option: observed `max_output_tokens` was absent. Hard output-token
and financial enforcement are therefore **NOT QUALIFIED**, not silently inferred
from bytes or elapsed time. Input/output usage is optional telemetry. The host
bounds serialized input to 128 KiB, streamed text to 16 KiB, time and requests;
these are **not token limits**. Missing token metadata does not block this
explicit subscription exception. Paid/local hard-budget support is not claimed.

## Request-path audit and integration scope

- `llm.OpenAIJSONDecider`: explicit HTTP-compatible request.
- `command_decider.CommandJSONDecider`: reviewed installed command.
- `mailbox.MailboxDecider`: bounded nonce publication to an external model host.
- `AgentRuntime` and `ProjectAgent`: invoke an injected decider;
  `ContextDecider` decorates observations, not a second provider.
- CLI/examples select those adapters. Native Java, skills, event callbacks and MCP
  goal dispatch do not independently initiate inference.
- The new cooperation supervisor exposes **only `LimitedDecider`** to both model
  loops. Its one-request reviewed pi SDK child cannot launch tools, agent trees,
  compaction or retries. Every probe/campaign inference is reserved before launch.

Legacy directly instantiated library/CLI adapters remain available to trusted
operators; they are **not retroactively globally intercepted**. Generic composition
is available, but only this fixed subscription SDK subprocess path has the stated
live operational qualification. No metered-adapter budgeting is certified.

## Deterministic and mutation evidence

- **25 new public deterministic tests**: thread/process contention, exact request
  and time bounds, independent exhaustion, cancellation, unknown usage, partial or
  malformed results, duplicate/conflicting IDs, persistence, crash recovery,
  foreign identities, overflow/invalid policies and audit-full emergency stop.
- **17/17 targeted operational mutations killed**. An earlier expanded run had
  two survivors: probabilistic-only atomicity coverage and insufficient explicit
  recovery-state assertions. That run is retained. Tests now check the held
  transaction before admission reads and the exact `UNCERTAIN` recovery state;
  production guards were not loosened to pass.
- **709 Python regressions**, Gradle check, **10 TLS interop checks**, and **123
  applicable mutations** pass (50 BCL, 14 gateway, 12 automatic-event, 17 model
  limits, 14 soak, 16 feedback).
- The corrected private supervisor additionally passes **6 deterministic integration
  tests** and **2/2 targeted mutations**: real SDK numeric wire-ID allocation,
  raw duplicate-key preservation, stream text bounds, known-task cancellation,
  uncertain receipts, empty decisions and authority-injection rejection.

These simulated tests are not Minecraft cooperation acceptance. The separate
[cooperation report](blockwire-cooperation-qualification.md) records native
preflight failures, actual autonomy, world effects, recordings and shutdown.

| Area | Qualification |
|---|---|
| Atomic global/per-agent request/time reservations | GO, operational subscription scope |
| Persistence / restart / conservative timeout charge | GO |
| BCL admission counts | GO, compiled host input |
| Actual independent concurrent GPT-6-luna requests | GO, two separate small cohorts |
| Strict provider output-token ceiling | NOT QUALIFIED — field absent |
| Monetary ceiling | NOT IMPLEMENTED / CONDITIONAL subscription route, not billing audit |
| All legacy callers globally forced through this boundary | NOT CLAIMED |
| Eight-hour soak / arbitrary providers | NOT RUN / NOT QUALIFIED |

Private evidence is ignored under `build/llm-budget-qualification/subscription-*`
and `build/blockwire-multiplayer/cooperation-*`; public machine-readable evidence
contains summaries/hashes only. No commit, push, upload, deployment, release or
bundle rebuild is authorized or performed.
