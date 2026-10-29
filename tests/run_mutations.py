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
    ("controller_key_clock", "InputLeases.java", "now>=deadlines.get(entry.getKey())", "false",
     "CL05_monotonic_deadline_bounds_food", "controllerContractTest"),
    ("controller_key_ticks", "InputLeases.java", "count<=0 ||", "false ||",
     "CL08_tick_expiry_without_clock_progress", "controllerContractTest"),
    ("controller_retained_deadline", "InputLeases.java", "deadlines.keySet().retainAll(remaining.keySet());",
     "deadlines.keySet().retainAll(remaining.keySet());remaining.forEach((key,count)->deadlines.put(key,now+Math.max(1,count)*50_000_000L));",
     "CL26_food_renewal_never_extends_short_walk", "controllerContractTest"),
    ("controller_retained_ticks", "InputLeases.java", "deadlines.keySet().retainAll(remaining.keySet());",
     "deadlines.keySet().retainAll(remaining.keySet());remaining.replaceAll((key,count)->8);",
     "CL29_food_renewal_retains_walk_tick_budget", "controllerContractTest"),
    ("controller_parent_cap", "InputLeases.java", "Math.min(deadline,now+ticks*50_000_000L)", "deadline",
     "CL28_enclosing_lease_shortens_retained_keys_without_resurrection", "controllerContractTest"),
    ("controller_hotbar_fence", "Blockwire.java", "int slot=Protocol.hotbarSlot(q);guardedActor(q);playing();",
     "int slot=Protocol.hotbarSlot(q);playing();", "CL19_hotbar_actor_guard_before_effect", "controllerContractTest"),
    ("settings_open_enables", "LocalSettingsModel.java",
     "this.backend=backend;status=backend.status();draftAutoStart=status.autoStart();",
     "this.backend=backend;status=backend.status();draftAutoStart=status.autoStart();backend.toggleRuntime();",
     "MM03_open_is_read_only", "settingsContractTest"),
    ("settings_save_enables", "LocalSettingsModel.java",
     "boolean saved=backend.saveStartup(draftAutoStart);refresh();",
     "boolean saved=backend.saveStartup(draftAutoStart);backend.toggleRuntime();refresh();",
     "MM04_save_does_not_enable_runtime", "settingsContractTest"),
    ("settings_stale_authority", "BridgeConfig.java", "if(!parse(json).equals(expected))", "if(false)",
     "MM08_stale_config_rejected", "settingsContractTest"),
    ("settings_preserve_key", "BridgeConfig.java", 'json.addProperty("enabled",enabled);',
     'json.addProperty("enabled",enabled);json.addProperty("mcp_api_key","b".repeat(64));',
     "MM07_save_changes_only_startup_flag", "settingsContractTest"),
    ("settings_private_permissions", "BridgeConfig.java", 'permissions(temporary,"rw-------");',
     'permissions(temporary,"rw-r--r--");', "MM07_saved_config_private", "settingsContractTest"),
    ("visibility_occlusion", "VisibilityView.java", "var hit=cast(blocks,eye,aim);",
     "var hit=new BlockHitResult(aim,net.minecraft.core.Direction.UP,pos,false);",
     "VIS03_occluded_chest_rejected", "visibilityContractTest"),
    ("visibility_unknown_opaque", "VisibilityView.java",
     "source.loaded(pos)?source.getBlockState(pos):Blocks.BARRIER.defaultBlockState()",
     "source.loaded(pos)?source.getBlockState(pos):Blocks.AIR.defaultBlockState()",
     "VIS04_missing_chunk_is_opaque", "visibilityContractTest"),
    ("visibility_range", "VisibilityView.java", "delta.lengthSqr()<=RANGE*RANGE", "true",
     "VIS05_range_and_view_filter", "visibilityContractTest"),
    ("visibility_compression_gap", "VisibilityView.java", " && pos.getX()==previous.getX()+1", "",
     "VIS07_roundtrip_positions_and_gaps", "visibilityContractTest"),
    ("visibility_metadata_cap", "VisibilityView.java", "if(visits==MAX_POSITIONS)", "if(false)",
     "VIS06_candidate_metadata_cap", "visibilityContractTest"),
    ("visibility_target_cap", "VisibilityView.java", "Math.min(MAX_INTERACTABLES,ordered.size())", "ordered.size()",
     "VIS06_target_cap", "visibilityContractTest"),
    ("attack_target_identity", "Protocol.java", "expected!=null && !expected.equals(actual)", "false", "changed_attack_target"),
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
        results.append({"mutation": name, "status": "KILLED" if killed else ("SURVIVED" if run.returncode == 0 else "INCONCLUSIVE"),
                        "expected_detection": expected, "exit_code": run.returncode})
(OUT / "results.json").write_text(json.dumps(results, indent=2) + "\n")
print(json.dumps(results, indent=2))
if not all(row["status"] == "KILLED" for row in results):
    raise SystemExit(1)
