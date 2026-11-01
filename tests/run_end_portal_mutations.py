#!/usr/bin/env python3
"""Isolated campaign-example mutations; no Minecraft connection or source edits."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("BLOCKWIRE_VERIFICATION_DIR", ROOT / "build/end-portal-verification")) / "mutations"
MUTATIONS = [
    ("stage_entry_dimension", 'if before.get("dimension") != stage.dimension_before:', 'if False:', "EP16"),
    ("stage_exit_dimension", 'stage.dimension_after and scene.get("dimension") != stage.dimension_after',
     'False', "EP17"),
    ("final_observation_cancel", 'stop = guard()  # Reads and verification may have consumed the remaining budget.',
     'stop = None', "EP14"),
    ("campaign_no_pause", 'if pause_on_stop and player.observe().get("in_world")',
     'if True and player.observe().get("in_world")', "EP08"),
    ("wood_no_pause", 'if not args.no_pause and player.observe().get("in_world")',
     'if True and player.observe().get("in_world")', "EP13"),
    ("credits_native_screen", 'scene["completion_screen_type"] = player.menu().get("type")',
     'scene["completion_screen_type"] = "WinScreen"', "EP09"),
    ("no_silent_unpause", 'if not pause_on_stop and player.menu().get("type") == "PauseScreen":',
     'if False:', "EP11"),
    ("missing_preflight", '    if check["missing_skills"]:', '    if False:', "EP01"),
    ("observed_postcondition", 'or not stage.verify(scene, inventory)', 'or False', "EP02"),
    ("actor_fence", '(scene["actor_session"] != session and not transition)', 'False', "EP04"),
    ("native_portal_identity", 'target.get("id") == identifier', 'True', "EP06"),
    ("native_portal_reach", 'math.dist(eye, [v+.5 for v in position]) <= 4.5', 'True', "EP06"),
    ("deadline", 'deadline = clock()+duration_seconds', 'deadline = clock()+1e12', "EP05"),
    ("pause_after_attempt", '\n                if pause_on_stop and player.observe().get("in_world") and not player.menu().get("screen_open"):',
     '\n                if False:', "EP02"),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for name, before, after, contract in MUTATIONS:
        with tempfile.TemporaryDirectory(prefix="blockwire-end-portal-mutation-") as directory:
            target = Path(directory)
            (target / "examples").mkdir()
            (target / "python/tests").mkdir(parents=True)
            source = (ROOT / "examples/end_portal.py").read_text()
            assert source.count(before) == 1, name
            (target / "examples/end_portal.py").write_text(source.replace(before, after))
            shutil.copy2(ROOT / "python/tests/test_end_portal_example.py", target / "python/tests")
            environment = dict(os.environ, PYTHONPATH=str(ROOT / "python/src"))
            run = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s",
                                  str(target / "python/tests"), "-v", "-k", "test_"+contract],
                                 cwd=target, env=environment, text=True, capture_output=True, timeout=20)
            output = run.stdout+run.stderr
            (OUT / (name+".log")).write_text(output)
            killed = (run.returncode != 0 and "Ran 1 test" in output and "FAIL:" in output
                      and not any(marker in output for marker in ("SyntaxError", "ImportError", "ModuleNotFoundError")))
            results.append({"mutation": name, "status": "KILLED" if killed else "INCONCLUSIVE"})
    (OUT / "results.json").write_text(json.dumps(results, indent=2)+"\n")
    print(json.dumps(results, indent=2))
    return 0 if all(row["status"] == "KILLED" for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
