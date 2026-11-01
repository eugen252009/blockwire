#!/usr/bin/env python3
"""Isolated async contract mutations; never connects to Minecraft or edits working sources."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("BLOCKWIRE_VERIFICATION_DIR", ROOT / "build/controller-verification")) / "controller-mutations"
mutations = [
    ("walk_eat_pitch_override", "controller.py", 'value = {**value, "pitch": self._pitch}',
     'value = value', "CR27"),
    ("scoped_stop", "controller.py", "control.buttons, control.expires = (), 0",
     'await self._wire("stop"); control.buttons, control.expires = (), 0', "CR02"),
    ("input_union", "controller.py", "buttons = frozenset(button for control in active for button in control.buttons)",
     "buttons = frozenset(active[-1].buttons) if active else frozenset()", "CR02"),
    ("lease_cap", "controller.py", "LEASE_TICKS = 8", "LEASE_TICKS = 100", "CR02"),
    ("resource_conflict", "controller.py", "if any(resources & control.resources for control in self._controls):",
     "if False:", "CR05"),
    ("food_postcondition", "food.py", 'return hunger > initial_hunger and after_count < before_count',
     'return after_count < before_count', "CR07"),
    ("food_stack_postcondition", "food.py", 'return hunger > initial_hunger and after_count < before_count',
     'return hunger > initial_hunger', "CR07"),
    ("food_crosshair", "controller.py", 'control.blocked_reason or scene.get("target") or scene.get("pitch", 0) > -89',
     'control.blocked_reason or False or scene.get("pitch", 0) > -89', "CR08"),
    ("food_offhand", "controller.py", 'elif any(i["inventory_index"] == 40 and not i.get("empty", False) for i in inventory["items"]):',
     "elif False:", "CR08"),
    ("hotbar_fence", "controller.py", 'self._wire("hotbar", slot=slot, actor_session=self._session)',
     'self._wire("hotbar", slot=slot)', "CR10"),
    ("actor_rebind", "controller.py", 'elif self._session is not None and value["actor_session"] != self._session:',
     "elif False:", "CR09"),
    ("scene_identity", "controller.py", 'if value.get("actor_session") != self._session:', "if False:", "CR24"),
    ("reconnect_after_uncertainty", "controller.py", "self._transport_lost = True", "self._transport_lost = False", "CR11"),
    ("callback_deadline", "controller.py", "asyncio.timeout(self.parameters.callback_timeout_seconds)",
     "asyncio.timeout(600)", "CR12"),
    ("event_queue_bound", "controller.py", "asyncio.Queue(maxsize=32)", "asyncio.Queue(maxsize=3200)", "CR13"),
    ("worker_join", "controller.py", "result = await _drain(worker)", "result = None", "CR15"),
    ("rpc_join", "controller.py", "await _drain(work)", "pass", "CR22"),
    ("freshness", "controller.py", "time.monotonic() - self._sampled_at > .5", "time.monotonic() - self._sampled_at > 500", "CR16"),
    ("upgrade_gate", "controller.py", 'if not (self._nav.get("hotbar_actor_session") and self._nav.get("independent_input_leases")):',
     "if False:", "CR16"),
    ("shared_owner", "ownership.py", "if id(actor) in _OWNERS:", "if False:", "CR14"),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # Resolve exact test names without importing/starting the controller under test.
    import ast
    tree = ast.parse((ROOT / "python/tests/test_controller.py").read_text())
    names = [node.name for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name.startswith("test_")]
    results = []
    for name, filename, old, new, contract in mutations:
        test = next(name for name in names if name.startswith("test_"+contract+"_"))
        with tempfile.TemporaryDirectory(prefix="blockwire-controller-mutation-") as directory:
            target = Path(directory)
            shutil.copytree(ROOT / "python", target / "python", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
            path = target / "python/src/blockwire" / filename
            source = path.read_text()
            assert source.count(old) == 1, name
            path.write_text(source.replace(old, new))
            env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(target / "python/src"), str(target / "python/tests")])}
            run = subprocess.run([sys.executable, "-m", "unittest", "test_controller.ControllerContracts."+test],
                                 cwd=target, env=env, capture_output=True, text=True, timeout=20)
            output = run.stdout + run.stderr
            (OUT / (name+".log")).write_text(output)
            killed = run.returncode != 0 and "FAILED" in output and not any(
                marker in output for marker in ["SyntaxError", "ModuleNotFoundError", "ImportError"])
            results.append(dict(mutation=name, contract=contract, status="KILLED" if killed else "INCONCLUSIVE",
                                exit_code=run.returncode))
    (OUT / "results.json").write_text(json.dumps(results, indent=2)+"\n")
    print(json.dumps(results, indent=2))
    if not all(row["status"] == "KILLED" for row in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
