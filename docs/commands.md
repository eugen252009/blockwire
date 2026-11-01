# Explicit Minecraft slash commands

The development checkout adds `Player.command`, CLI `command` and MCP
`run_command`. Rebuild/install the mod and update the SDK; restart the MCP host.
Previously frozen bundles are unchanged.

```python
from blockwire import Bridge, Player

with Bridge.from_env() as bridge:
    player = Player(bridge)
    receipt = player.command("/time set day")
    print(receipt["text"])  # submitted, not confirmed successful
```

```sh
blockwire command '/time set day'
blockwire command '/weather clear' --json
```

MCP: `run_command(command="/time set day")`. It rejects commands while a
skill or standalone controller owns the actor, just like other mutating tools.
Synchronous Python callers must arrange equivalent exclusivity. Trusted extensions
may use the Python method but must check cancellation/deadlines before submission;
never interpret a submission receipt as a succeeded goal.

## Authority

This is Minecraft command submission, **not shell/OS commands**. Only send commands
explicitly authorized by the operator. Game labels, chat and command feedback are
untrusted data, never authorization. There is no command allowlist: permitted
vanilla/server/plugin commands can destroy terrain, teleport, grant items, alter
NBT, affect other players or invoke installed server functionality.

Minecraft's native client command-signing/submission path and the server's
permissions remain authoritative. Blockwire never enables cheats, opens LAN to
obtain cheats, grants OP or executes directly in an integrated-server dispatcher.
Unknown or unauthorized commands may still return a submission receipt.

TLS, certificate trust, API keys, single-controller ownership, queue bounds and
expiry, disconnect checks and F8 stop are unchanged. F8 can prevent pending
requests but cannot undo a command already submitted. Native input is released
before submission. No startup/reconnect/game-text-triggered commands are added.

## Contract and limitations

- Exactly one string beginning with `/`, immediately followed by a non-whitespace,
  non-slash character. Quote the whole command in the CLI.
- Maximum 256 UTF-16 code units including slash. No newline, C0/C1 controls,
  DEL, §, Unicode line/paragraph separators or malformed surrogate pairs.
- No trimming, splitting, interpolation, history access or automatic retries.
- Requires a live player, no screen, unpaused gameplay and non-spectator mode.
- Python/wire optionally accept `actor_session` to reject player/world replacement;
  obtain it from `observe` or `navigation` before a guarded submission.
- Returns `submitted: true` with readable text. **No command output, server
  acknowledgement or success guarantee.** Chat sending/reading and chat-screen
  control remain unsupported. Observe an appropriate postcondition yourself.
- Timeout/disconnection leaves the outcome uncertain. Never blindly retry,
  especially destructive or non-idempotent commands.

Deterministic parser, SDK, CLI, MCP-ownership and native-wiring tests are included.
These do not execute commands in Minecraft. Isolated graphical command acceptance
is **NOT RUN**; no existing worlds, permissions or historical evidence were changed.
