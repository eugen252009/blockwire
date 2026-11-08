package dev.blockwire;

import com.google.gson.*;
import java.nio.file.*;
import java.util.*;

/** Pure interpolation/parser/wiring contracts; graphical timing is qualified separately. */
public final class RotationContractTest {
    static int checks;
    static void check(boolean value,String label){checks++;if(!value)throw new AssertionError(label);}
    static void close(double actual,double expected,String label){check(Math.abs(actual-expected)<1e-6,label+" actual="+actual);}
    static void rejected(Runnable action,String label){try{action.run();throw new AssertionError(label);}catch(IllegalArgumentException expected){checks++;}}
    public static void main(String[] args) throws Exception {
        close(RotationController.yawDelta(90,0),90,"RT01_quarter_turn");
        close(RotationController.yawDelta(180,90),90,"RT02_half_axis");
        close(RotationController.yawDelta(0,180),-180,"RT03_tied_half_turn_is_bounded");
        close(RotationController.yawDelta(-179,179),2,"RT04_positive_wrap_shortest");
        close(RotationController.yawDelta(179,-179),-2,"RT05_negative_wrap_shortest");
        close(RotationController.yawDelta(-90,90),-180,"RT06_opposite_direction");
        close(RotationController.yawDelta(37,37),0,"RT07_identical_yaw");
        close(RotationController.clampPitch(-120),-90,"RT08_pitch_upper_clamp");
        close(RotationController.clampPitch(120),90,"RT09_pitch_lower_clamp");

        var linear=RotationController.interpolate(0,0,90,-30,"linear",.5);
        close(linear.yaw(),45,"RT10_linear_yaw");close(linear.pitch(),-15,"RT11_linear_pitch_same_time");
        var smoothQuarter=RotationController.interpolate(0,0,90,0,"smoothstep",.25);
        close(smoothQuarter.yaw(),14.0625,"RT12_smoothstep_ease_in");
        var smoothHalf=RotationController.interpolate(0,0,90,0,"smoothstep",.5);
        close(smoothHalf.yaw(),45,"RT13_smoothstep_midpoint");
        var wrapped=RotationController.interpolate(179,0,-179,0,"linear",.5);
        close(wrapped.yaw(),180,"RT14_unwrapped_short_arc_has_no_numeric_snap");
        var wrappedEnd=RotationController.interpolate(179,0,-179,0,"linear",1.);
        close(wrappedEnd.yaw(),181,"RT15_equivalent_target_without_reverse");
        rejected(()->RotationController.curve("combat",.5),"RT16_profiles_are_explicit");

        var q=JsonParser.parseString("{\"duration_ms\":200}").getAsJsonObject();
        check(Protocol.rotationDuration(q)==200,"RT17_duration_parsed");
        check(Protocol.rotationProfile(q).equals("smoothstep"),"RT18_default_smoothstep");
        q.addProperty("rotation_profile","linear");check(Protocol.rotationProfile(q).equals("linear"),"RT19_linear_optional_profile");
        for(JsonElement invalid:List.of(new JsonPrimitive(0),new JsonPrimitive(5001),new JsonPrimitive(1.5),new JsonPrimitive(true),JsonNull.INSTANCE)) {
            q.add("duration_ms",invalid);rejected(()->Protocol.rotationDuration(q),"RT20_strict_bounded_duration");
        }
        q.remove("duration_ms");rejected(()->Protocol.rotationDuration(q),"RT21_profile_requires_duration");
        q.addProperty("duration_ms",200);q.addProperty("rotation_profile","spring");
        rejected(()->Protocol.rotationProfile(q),"RT22_reject_unknown_profile");

        String blockwire=Files.readString(Path.of("src/main/java/dev/blockwire/Blockwire.java"));
        String look=blockwire.substring(blockwire.indexOf("case \"look\" ->"),blockwire.indexOf("case \"drive\" ->"));
        check(look.contains("Protocol.fields(q,\"yaw\",\"pitch\",\"actor_session\",\"duration_ms\",\"rotation_profile\",\"grounded_creative\")") &&
              look.indexOf("guardedActor(q)")<look.indexOf("CreativeBuild.guardedInput") && look.indexOf("CreativeBuild.guardedInput")<look.indexOf("rotation.schedule") &&
              look.indexOf("rotationDuration(q)")<look.indexOf("guardedActor(q)") && look.indexOf("guardedActor(q)")<look.indexOf("rotation.schedule"),
              "RT23_validate_and_actor_fence_before_schedule");
        check(blockwire.contains("rotation.tick(mc,server!=null && server.connected());\n        if(held.isEmpty())return;"),
              "RT24_rotation_ticks_without_movement_input");
        check(blockwire.contains("rotation.cancel(mc,\"controls_released\");"),"RT25_global_stop_cancels_rotation");
        check(blockwire.contains("if(ticksLeft--<=0 || now>=deadline){releaseInputs();return;}") &&
              blockwire.contains("if(held.isEmpty()){releaseInputs();return;}"),
              "RT26_natural_input_expiry_does_not_cancel_independent_rotation");
        check(blockwire.contains("scene.add(\"rotation\",rotation.snapshot"),"RT27_rotation_state_is_observable");
        String controller=Files.readString(Path.of("src/main/java/dev/blockwire/RotationController.java"));
        check(controller.contains("if(same(current,targetYaw,targetPitch,durationMs,profile))") &&
              controller.contains("finish(\"superseded\",\"new_rotation_target\",now)"),"RT28_idempotent_or_superseded_single_controller");
        check(controller.contains("state.startYaw=actor.getYRot();state.startPitch=actor.getXRot();state.targetYaw=targetYaw"),
              "RT29_retarget_starts_at_actual_view");
        check(!controller.contains("Thread.sleep") && controller.contains("System.nanoTime()"),"RT30_monotonic_nonblocking_timebase");
        check(controller.contains("if(mc.player!=actor || mc.level!=level || actor==null)") &&
              controller.contains("if(mc.gui.screen()!=null || mc.isPaused())"),"RT31_actor_world_and_ui_cancel_active_plan");
        check(controller.contains("if(fraction>=1.){apply(actor,new Angles(current.appliedTargetYaw,current.targetPitch))"),
              "RT32_completion_applies_exact_equivalent_target");
        check(!controller.contains("KeyMapping") && !controller.contains("InputState"),"RT33_rotation_does_not_own_movement_keys");
        check(look.contains("duration==null?rotation.immediate") && look.contains("rotation.schedule"),
              "RT34_legacy_immediate_and_timed_modes_share_one_native_controller");
        String trace=Files.readString(Path.of("src/main/java/dev/blockwire/MotionTrace.java"));
        check(trace.contains("rotation.annotate(out)"),"RT35_tick_trace_contains_rotation_plan");
        System.out.println("BLOCKWIRE_ROTATION_CONTRACT_PASS checks="+checks);
    }
}
