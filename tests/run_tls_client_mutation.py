#!/usr/bin/env python3
"""Prove the real TLS interop checks detect disabling Python peer verification."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("BLOCKWIRE_VERIFICATION_DIR", ROOT / "build/tls-verification"))
OUT.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="blockwire-client-mutation-") as folder:
    copied = Path(folder) / "blockwire"
    shutil.copytree(ROOT / "python/src/blockwire", copied)
    path = copied / "client.py"
    source = path.read_text()
    old = "context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)"
    assert source.count(old) == 1
    path.write_text(source.replace(old, "context = ssl._create_unverified_context()"))
    environment = dict(os.environ, PYTHONPATH=folder)
    run = subprocess.run([str(ROOT / ".venv/bin/python"), "-B", str(ROOT / "tests/tls_interop.py")],
                         cwd=ROOT, env=environment, text=True, capture_output=True, timeout=90)
    output = run.stdout + run.stderr
    (OUT / "client-verification-mutation.log").write_text(output)
    killed = run.returncode != 0 and "certificate_and_hostname_verification_enabled" in output
    result = {"mutation": "unverified_python_tls", "status": "KILLED" if killed else "INCONCLUSIVE"}
    (OUT / "client-verification-mutation.json").write_text(json.dumps(result, indent=2)+"\n")
    print(result)
    if not killed:
        raise SystemExit(1)
