# Interactive BCL terminal and file runner

The terminal is a client of the existing BCL TLS-WebSocket gateway, **not another
BCL interpreter or Minecraft controller**. Both modes use `BCLClient`, authoritative
persistent gateway sessions, request/task correlation, BCLJobs and existing native
skills. No source is evaluated as Python or uploaded as executable code into Java.

## Install and connect

```sh
python3 -m venv .venv
.venv/bin/pip install -e python
```

The lightweight `prompt-toolkit` dependency supplies asynchronous line editing,
in-memory session history and prompt redraw around incoming output. No full-screen
TUI, persistent command history, colors or model connection is added.

Install the matching development mod, join an owned supervised test world and
enable control locally with F8. Provision a private gateway token and dedicated
TLS certificate/key according to [BCL gateway setup](bcl.md#python--mcp-usage).
The public gateway certificate must be trusted out-of-band and contain the existing
logical TLS hostname `block-bridge.invalid`. Native Minecraft and gateway trust
materials/credentials are separate. Never copy the native private PKCS12 identity.

Obtain fresh `player_uuid` and `actor_session` through the existing authorized
`Player.observe()` / MCP observation **before** handing the native connection to
the gateway. Keep the returned actor token verbatim. Choose your own world label;
it is not an inferred native world fingerprint. Stop the earlier native controller
before starting the gateway: only one host may own that native connection.

```sh
# Gateway host, using separately provisioned private gateway materials:
BLOCKWIRE_CONFIG=/trusted/native/settings.json \
  .venv/bin/python -m blockwire.bcl.gateway \
  --certificate /trusted/bcl/certificate.pem --private-key /private/bcl/key.pem \
  --token-file /private/bcl/token --state-directory /private/bcl-sessions
```

In a second terminal, substitute your authorized identities:

```sh
.venv/bin/python -m blockwire repl \
  --certificate /trusted/bcl/certificate.pem \
  --token-file /private/bcl/token \
  --world-id my-test-world \
  --player-uuid YOUR-UUID \
  --actor-session YOUR-FRESH-ACTOR-SESSION
```

Equivalent entry points: `.venv/bin/blockwire repl` and the compatibility command
`.venv/bin/blockwire-bcl` / `python -m blockwire.bcl.cli`. The latter still accepts
`--file program.bcl`. Existing native CLI commands remain unchanged.

Default URL is the local gateway `wss://127.0.0.1:8880/v1`, **not** the native mod
endpoint. `--url` selects another explicitly trusted gateway. Certificates, token
files, required binding flags and `--timeout` are shared by both modes. The client
rejects symlink/non-regular token files and, on POSIX, permissions broader than
0600. Credentials are never put into REPL history or echoed in connection
exceptions. A fresh session ID is generated unless explicitly supplied using
`--session-id`; `--agent-id`
defaults to `human`. No actor identity is guessed and no automatic rebind occurs.
After death/world/player replacement, inspect state and explicitly bind a new
session. There is no automatic respawn, reconnect or replay.

## Interactive use

Start with non-moving commands:

```text
bcl> S2 ?
bcl> S0 sync
bcl> S1 relative
bcl> E0 player.health
bcl> E2
bcl> :status
```

S0–S4 and E0–E3 are passed directly to the gateway. Setting cycles, queries and
snapshot ordering are interpreted only there. `:status` displays connection/session
information and the latest SDK modal snapshot; it does not change settings.

Ordinary input lines execute immediately. Multi-line input sends **one whole frame**:

```text
bcl> :begin
... S0 sync
... S1 relative
... S2 sneak
... S2 ?
... :end
```

The gateway compiles and statically validates the complete frame before effects.
No local parser or copied gameplay engine is involved.

| Local command | Behavior |
|---|---|
| `:help` | Show terminal help |
| `:begin` | Start an empty multiline buffer |
| `:end` / `:send` | Submit the complete buffer once |
| `:abort` | Discard buffered text |
| `:load PATH` | Load text into the buffer; **does not execute** |
| `:run PATH` | Read and immediately submit one complete file |
| `:tasks` | List task IDs received by this connection |
| `:status` | Display connection/session and modal snapshot |
| `:cancel ID` | Request cancellation of a known task |
| `:wait ID` | Wait for a known task's terminal result |
| `:quit` | Disconnect and request cancellation of connection-owned work |

Paths may contain spaces; the remainder of the command is a literal path, without
shell quotes, expansion or subprocess execution. `:end` or `:abort` is required
before replacing an existing buffer. EOF discards unfinished buffered text.

Responses distinguish `accepted`, running progress and actual terminal results.
A sync submission waits in a background response waiter while input/cancellation
remains responsive; it is never displayed as complete on mere acceptance. Async
submissions display their Task ID and later terminal response. There is no second
action scheduler: gameplay still executes serially under existing server ordering
and actor fences. At most 16 submissions are pending locally; server limits apply
independently. `:wait` itself blocks input until completion or timeout.

Subscribed events have a separate `[event]` label. The WebSocket receiver and queue
consumers continue while you type; prompt-toolkit redraws the current editable
line without dropping its content. History exists only in memory for the session.
Ctrl+C disconnects; Ctrl+D/EOF finishes already submitted work before closing.
`:quit` instead cancels immediately. None of these confirms native cleanup merely
by returning: inspect terminal results, the client and **F8** when uncertain.

## Execute a complete recording or program

```sh
.venv/bin/blockwire run recordings/human-house-001/program.bcl \
  --certificate /trusted/bcl/certificate.pem \
  --token-file /private/bcl/token --world-id my-test-world \
  --player-uuid YOUR-UUID --actor-session YOUR-FRESH-ACTOR-SESSION
```

`python -m blockwire run FILE` is equivalent. The whole UTF-8 file is read once
before connection and submitted as **one request**, never split into per-line
requests. Line endings, whitespace, comments and order are preserved exactly;
there is no optimization or format conversion. A UTF-8 BOM is also preserved and
subject to the existing compiler's rules, not silently removed. Files exceeding
16384 characters or the 32768-byte encoded-frame limit are rejected rather than
split. Invalid encodings/missing files fail before connecting. Invalid BCL is
rejected by the gateway's full-program validator.

The runner consumes events/progress while waiting and waits for actual terminal
completion even in async mode. A valid recording does not prove the current world
has its original materials, terrain or other prerequisites. Replay success is
separate from recording success. `completed` verifies only the program's existing
postconditions, not an independent free-text house/Survival objective.

## Output, errors and exit codes

Interactive output shows real status, request/task IDs, output values and available
structured diagnostics (including compiler line/column where supplied). It never
invents positions or success. `--verbose` / `--json` emits full JSON replies.
Redirected stdout defaults to JSON lines, without banners/prompts/colors, suitable
for scripts and pipelines. A TTY stdin remains cancellable when stdout is redirected;
it uses line-oriented input without emitting human UI text. Terminal control
characters in untrusted fields are escaped. No colors are used, including when
`NO_COLOR` is set.

```sh
.venv/bin/blockwire run program.bcl --certificate /trusted/bcl/certificate.pem \
  --token-file /private/bcl/token --world-id my-test-world \
  --player-uuid YOUR-UUID --actor-session YOUR-FRESH-ACTOR-SESSION \
  --json > results.jsonl
```

Exit codes: **0** for confirmed `completed` file execution (or an error-free REPL
exit with no unfinished requests); **1** for failed/rejected/cancelled/unconfirmed
execution, local input errors or quit with outstanding work; **2** for argument
errors; **130** for Ctrl+C. Failed commands retain diagnostics and allow subsequent
REPL input. Authentication/binding errors and unavailable/disconnected gateways
stop the session; detailed server-side reasons remain in private gateway logs.
Connection exceptions are not echoed verbatim because they can contain credentials.

`--timeout` defaults to 120 seconds and bounds SDK response waits (maximum 1800),
not gameplay operation budgets. Use existing S4 for supported per-operation budgets.
A timeout/disconnect is an **unconfirmed outcome**, never permission to blindly retry
an uncertain file. The idle prompt also notices receiver termination. Inspect/cancel
first; no automatic retries, rollback or replay exist. TLS verification, API-key
checks, actor fences, F8, native short input leases and cleanup are unchanged.

## Qualification and limits

Automated tests cover input/history, event reception during input, complete frames,
file preservation, invalid sources, modal queries, request correlation, async
completion, cancellation, disconnect, shutdown and exit codes. Real authenticated
TLS/WebSocket integration tests run against the actual gateway with a **simulated
native backend**, not a game world.

**Native graphical Minecraft smoke test: NOT RUN.** No running Minecraft client or
authorized isolated live fixture was available in this worktree. No other worktree,
world or historical evidence was modified. Terminal/transport tests do not qualify
new gameplay behavior, unattended operation or successful construction.

Known limitations: no desktop UI/full-screen editor; nested result details are
printed as escaped JSON; private gateway logs may be needed for binding/auth faults;
`:tasks` lists known SDK tasks, not a new server-global task-history API; `:wait`
blocks terminal input; pipe or redirected-output input is line-oriented and has no
editing/history.
