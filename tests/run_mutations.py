#!/usr/bin/env python3
"""Isolated security/validation mutations. Never edits working sources or runs Minecraft."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("BLOCKWIRE_VERIFICATION_DIR", ROOT / "build/verification")) / "mutations"
OUT.mkdir(parents=True, exist_ok=True)
mutations = [
    ("authorization", "BridgeServer.java", "!authorized ||", "false ||", "reject_unauthorized"),
    ("browser_origin", "BridgeServer.java", 'req.headers().contains(HttpHeaderNames.ORIGIN)', "false", "reject_browser_origin"),
    ("inclusive_minimum", "Protocol.java", "n<min", "n<=min", "out_of_range: yaw"),
    ("sdl_left_button", "MenuInput.java", "case 0 -> InputConstants.MOUSE_BUTTON_LEFT", "case 0 -> 0", "native_left_button"),
    ("logical_backspace", "MenuInput.java", "case InputConstants.KEY_BACKSPACE -> 8", "case InputConstants.KEY_BACKSPACE -> 42", "native_logical_backspace"),
    ("tls_certificate_export_integrity", "TlsIdentity.java", "!MessageDigest.isEqual(exported.getEncoded(),cert.getEncoded())", "false", "export_mismatch_fails_closed", "tlsContractTest"),
    ("tls_expiry", "TlsIdentity.java", "cert.checkValidity();cert.verify", "cert.verify", "expired_certificate_fails_closed", "tlsContractTest"),
]
results = []
for mutation in mutations:
    name, filename, old, new, expected = mutation[:5]
    task = mutation[5] if len(mutation) == 6 else "contractTest"
    with tempfile.TemporaryDirectory(prefix="blockwire-mutation-") as temporary:
        target = Path(temporary)
        for file in ["build.gradle", "settings.gradle", "gradle.properties", "gradlew", "gradlew.bat", "LICENSE"]:
            shutil.copy2(ROOT / file, target / file)
        for folder in ["gradle", "src"]:
            shutil.copytree(ROOT / folder, target / folder)
        path = target / "src/main/java/dev/blockwire" / filename
        source = path.read_text()
        assert source.count(old) == 1
        path.write_text(source.replace(old, new))
        run = subprocess.run(["./gradlew", "--console=plain", task], cwd=target,
                             capture_output=True, text=True, timeout=120)
        output = run.stdout + run.stderr
        (OUT / (name + ".log")).write_text(output)
        killed = run.returncode != 0 and expected in output and "Compilation failed" not in output
        results.append({"mutation": name, "status": "KILLED" if killed else "INCONCLUSIVE",
                        "expected_detection": expected, "exit_code": run.returncode})
(OUT / "results.json").write_text(json.dumps(results, indent=2) + "\n")
print(json.dumps(results, indent=2))
if not all(row["status"] == "KILLED" for row in results):
    raise SystemExit(1)
