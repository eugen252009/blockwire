#!/usr/bin/env python3
"""Isolated Python skill mutations; no live game, secrets or working-source changes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("BLOCKWIRE_VERIFICATION_DIR", ROOT / "build/skills-verification")) / "skill-mutations"
OUT.mkdir(parents=True, exist_ok=True)
mutations = [
    ("hazard_filter", "walking.py", "if not (avoid_damage and cell[\"hazards\"])", "if True",
     "test_hazard_detour_and_opt_out"),
    ("observed_arrival", "walking.py", "if distance <= .3:", "if True:",
     "test_flat_arrival_is_observed_and_releases"),
    ("actor_identity", "walking.py", 'if session != state["actor_session"]:', "if False:",
     "test_session_replacement_stops_before_new_actor_input"),
    ("cleanup", "core.py", "                player.stop()", "                pass",
     "test_flat_arrival_is_observed_and_releases"),
    ("deadline", "core.py", "if self.clock() >= self.deadline:", "if False:",
     "test_stuck_and_timeout"),
    ("single_owner", "core.py", "if self._active is not None:", "if False:",
     "test_background_job_status_cancel_and_exclusive_control"),
]
results = []
for name, filename, before, after, expected in mutations:
    with tempfile.TemporaryDirectory(prefix="blockwire-skill-mutation-") as folder:
        copied = Path(folder) / "blockwire"
        shutil.copytree(ROOT / "python/src/blockwire", copied, ignore=shutil.ignore_patterns("__pycache__"))
        path = copied / "skills" / filename
        source = path.read_text()
        assert source.count(before) == 1
        path.write_text(source.replace(before, after))
        environment = dict(os.environ, PYTHONPATH=folder)
        run = subprocess.run([str(ROOT / ".venv/bin/python"), "-B", "-m", "unittest",
                              "discover", "-s", str(ROOT / "python/tests"), "-p", "test_skills.py", "-v"],
                             env=environment, cwd=ROOT, text=True, capture_output=True, timeout=20)
        output = run.stdout + run.stderr
        (OUT / f"{name}.log").write_text(output)
        killed = run.returncode != 0 and f"FAIL: {expected}" in output
        results.append({"mutation": name, "status": "KILLED" if killed else "INCONCLUSIVE"})
(OUT / "results.json").write_text(json.dumps(results, indent=2)+"\n")
print(json.dumps(results, indent=2))
if not all(result["status"] == "KILLED" for result in results):
    raise SystemExit(1)
