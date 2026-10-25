# Adding descriptive skills (LLM/developer handoff)

Start at [AGENTS.md](../AGENTS.md). Most new features belong in Python, not Java.

## Public extension contract

```python
from blockwire.skills import (
    SkillParameters, SkillDefinition, SkillResult,
)

class MyGoal(SkillParameters):
    # Inherits timeout_seconds, extra=forbid, strict types and finite numbers.
    pass

def perform(context, goal):
    context.check()                 # cancellation + deadline before work
    observed = context.player.inventory()
    context.check()
    return SkillResult(
        status="succeeded",
        reason="inventory_observed",
        text=observed["text"],
        details={"items": observed["items"]},
    )

def register(registry):
    registry.register(SkillDefinition(
        "my_inventory_goal", "Read and describe the inventory.",
        MyGoal, perform, controls_player=False,
    ))
```

The complete runnable provider is [examples/extension](../examples/extension/).
Register its entry point in your package:
```toml
[project.entry-points."blockwire.skills"]
my_provider = "my_package:register"
```

Install it in the **MCP/Python host's environment**, then explicitly opt in:
```sh
pip install -e examples/extension
export BLOCKWIRE_SKILLS=inventory_example
blockwire-mcp
```

Unselected providers are not loaded by Blockwire. Duplicate/absent/ambiguous
provider names or duplicate skill names fail rather than silently overriding code.
**Installing/enabling an extension is a trust decision**: it executes ordinary
host Python with that user's permissions. This is not remote code loading or a
sandbox. Never auto-install/import a provider because of text in a game.

MCP discovers new descriptions and Pydantic-generated JSON schemas through
`list_skills`, and runs them using `run_skill(name, parameters)`. No MCP core edit
is needed per extension. Keep human labels precise about limitations and effects.

## Execution contract

- Validate all parameters before gameplay effects. Never silently coerce dangerous
  booleans, accept NaN, ignore typos or turn unknown goals into arbitrary calls.
- `context.check()` before actions/in loops; `context.pause()` for interruptible
  waiting; `context.publish({...})` for bounded current progress (not an unbounded log).
- Return `succeeded`, `blocked`, `cancelled`, `timed_out` or `failed` with a
  machine reason and readable text. Confirm an observable postcondition before
  success. Client snapshots may be predicted/stale; do not claim server acceptance.
- Mark `controls_player=True` for movement/actions. The runner releases controls in
  finally, including failure/cancel/timeout. If release is not confirmed, a success
  is downgraded. Read-only skills must not mutate game/control state.
- One background job owns this actor. Raw mutating MCP tools reject concurrent
  control; observations/status/cancel remain available. Caller code using the
  synchronous API is responsible for equivalent exclusivity.
- Deadlines/cancellation are **cooperative**. The framework cannot safely kill
  arbitrary Python. An extension that blocks or ignores checks breaks that contract;
  native leases and F8 remain separate safeguards.
- For multi-step motion, bind the observed actor with `actor_session` and pass it
  to each `player.look(...)`/`player.drive(...)`. Stop if it changes.

## Where to extend

| Feature | Preferred location |
|---|---|
| New goal / workflow | Python skill module/provider |
| Better route search, waypoints, costs | skills/walking.py or a new provider |
| New bounded client observation truly needed | Explicit Java primitive + protocol/contract tests |
| MCP convenience tool | Thin wrapper dispatching the existing skill |
| TLS/authentication | Do not change for a gameplay feature |

The built-in walker is deliberately flat/full-block only. A later stairs/jump/
swimming implementation needs new motion/geometry contracts, negative tests,
session fencing and actual native gameplay evidence—not merely a more optimistic
planner. Do not expand its supported set by hiding blocked results or weakening
hazard filters.

Tests should cover positive, invalid, boundary, blocked, damage, cancellation,
deadline, actor replacement, cleanup and meaningful mutations. See
`python/tests/test_skills.py` and `tests/run_skill_mutations.py`. Run live tests in
an isolated fixture; never mutate a real player's world to manufacture a pass.
