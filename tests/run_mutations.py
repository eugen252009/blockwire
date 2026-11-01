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
    ("respawn_session", "Blockwire.java",
     "Protocol.inventoryFields(q);guardedActor(q);playerRequired();\n                if(mc.player.isAlive())",
     "Protocol.inventoryFields(q);playerRequired();\n                if(mc.player.isAlive())",
     "IV04_respawn_actor_guard_before_effect", "inventoryContractTest"),
    ("inventory_open_session", "Blockwire.java",
     "Protocol.inventoryFields(q);guardedActor(q);playing();release();mc.gui.setScreen",
     "Protocol.inventoryFields(q);playing();release();mc.gui.setScreen",
     "IV01_open_actor_guard_before_effect", "inventoryContractTest"),
    ("inventory_close_session", "Blockwire.java",
     'case "close_screen" -> {\n                Protocol.inventoryFields(q);guardedActor(q);playerRequired();',
     'case "close_screen" -> {\n                Protocol.inventoryFields(q);playerRequired();',
     "IV02_close_actor_guard_before_effect", "inventoryContractTest"),
    ("inventory_click_session", "Blockwire.java",
     "guardedActor(q);playerRequired();\n                if(!(mc.gui.screen() instanceof AbstractContainerScreen<?> screen)",
     "playerRequired();\n                if(!(mc.gui.screen() instanceof AbstractContainerScreen<?> screen)",
     "IV03_click_actor_guard_before_effect", "inventoryContractTest"),
    ("command_size", "Protocol.java", "text.length()>256", "false",
     "CMD06_reject_oversized", "commandContractTest"),
    ("command_controls", "Protocol.java", "Character.isISOControl(c)", "false",
     "CMD07_reject_controls_and_malformed_unicode", "commandContractTest"),
    ("command_session", "Blockwire.java", "String command=Protocol.command(q);guardedActor(q);playing();",
     "String command=Protocol.command(q);playing();", "CMD12_validate_and_fence_before_effect", "commandContractTest"),
    ("command_native_release", "Blockwire.java", "release();mc.player.connection.sendCommand(command);",
     "mc.player.connection.sendCommand(command);", "CMD13_release_and_native_submission", "commandContractTest"),
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
    ("play2code_remote_sample", "Play2CodeRecorder.java",
     'if(endpointRunning){endpointEnabled=true;abort("control_endpoint_enabled");return;}',
     'if(false){endpointEnabled=true;abort("control_endpoint_enabled");return;}',
     "P2C11_remote_interference_fails_before_sample", "play2CodeContractTest"),
    ("play2code_actor_fence", "Play2CodeRecorder.java", "mc.player!=actor || mc.level!=level", "false",
     "P2C12_actor_world_fence", "play2CodeContractTest"),
    ("play2code_confirmation", "Play2CodeRecorder.java", "CONFIRM_TICKS=3", "CONFIRM_TICKS=1",
     "P2C13_mutation_requires_stable_observation", "play2CodeContractTest"),
    ("play2code_endpoint_enable", "Blockwire.java", 'else {play2Code.abort("control_endpoint_enabled");startServer();}',
     'else {startServer();}', "P2C08_endpoint_enable_invalidates_recording_first", "play2CodeContractTest"),
    ("play2code_no_control", "Play2CodeRecorder.java", 'if(append("tick",event)<0)return;ticks++;',
     'InputState.set(keys.get("forward"),true);if(append("tick",event)<0)return;ticks++;',
     "P2C14_recorder_has_no_control_effects", "play2CodeContractTest"),
    ("rotation_shortest_yaw", "RotationController.java", "return normalizeYaw(target-current);", "return target-current;",
     "RT04_positive_wrap_shortest", "rotationContractTest"),
    ("rotation_smooth_profile", "RotationController.java", "return t*t*(3.-2.*t);", "return t;",
     "RT12_smoothstep_ease_in", "rotationContractTest"),
    ("rotation_duration_bound", "RotationController.java", "MAX_DURATION_MS=5000", "MAX_DURATION_MS=5001",
     "RT20_strict_bounded_duration", "rotationContractTest"),
    ("rotation_default_profile", "Protocol.java", 'return "smoothstep";', 'return "linear";',
     "RT18_default_smoothstep", "rotationContractTest"),
    ("rotation_actor_fence", "RotationController.java", "mc.player!=actor || mc.level!=level || actor==null", "mc.level!=level || actor==null",
     "RT31_actor_world_and_ui_cancel_active_plan", "rotationContractTest"),
    ("rotation_exact_endpoint", "RotationController.java",
     "if(fraction>=1.){apply(actor,new Angles(current.appliedTargetYaw,current.targetPitch));finish",
     "if(fraction>=1.){finish", "RT32_completion_applies_exact_equivalent_target", "rotationContractTest"),
    ("rotation_retarget_actual_yaw", "RotationController.java",
     "state.startYaw=actor.getYRot();state.startPitch=actor.getXRot();state.targetYaw=targetYaw",
     "state.startYaw=targetYaw;state.startPitch=actor.getXRot();state.targetYaw=targetYaw",
     "RT29_retarget_starts_at_actual_view", "rotationContractTest"),
    ("rotation_independent_input_expiry", "Blockwire.java", "if(ticksLeft--<=0 || now>=deadline){releaseInputs();return;}",
     "if(ticksLeft--<=0 || now>=deadline){release();return;}",
     "RT26_natural_input_expiry_does_not_cancel_independent_rotation", "rotationContractTest"),
    ("rotation_legacy_compatibility", "Blockwire.java", "duration==null?rotation.immediate(mc,yaw,pitch):rotation.schedule",
     "duration==null?rotation.schedule(mc,yaw,pitch,200,profile):rotation.schedule",
     "RT34_legacy_immediate_and_timed_modes_share_one_native_controller", "rotationContractTest"),
    ("navigation_diagonal_edges", "NavigationView.java", "{1,0},{0,1},{1,1},{1,-1}", "{1,0},{0,1}",
     "TR10_flat_diagonal_only", "terrainContractTest"),
    ("navigation_gap_edges", "NavigationView.java", "{2,0},{0,2},{2,2},{2,-2}", "{2,0},{0,2}",
     "TR11_gap_requires_broad_landing", "terrainContractTest"),
    ("navigation_gap_runup", "NavigationView.java", "indices.containsKey(middle) || !indices.containsKey(behind)", "indices.containsKey(middle)",
     "TR12_gap_and_runup_geometry", "terrainContractTest"),
    ("navigation_partial_support_actor", "NavigationView.java", "if(!centerAccess && actor.onGround())", "if(!centerAccess)",
     "TR13_partial_support_recovery_is_bounded", "terrainContractTest"),
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
