package dev.blockwire;

import com.google.gson.*;
import java.nio.file.*;

/** Parser/wiring contracts for telemetry only; NOT graphical movement acceptance. */
public final class MotionTraceContractTest {
    static int checks;
    static void check(boolean value,String label){checks++;if(!value)throw new AssertionError(label);}
    static void rejected(Runnable action,String label){try{action.run();throw new AssertionError(label);}catch(IllegalArgumentException expected){checks++;}}
    public static void main(String[] args) throws Exception {
        var q=new JsonObject();q.addProperty("op","motion_trace");
        check(MotionTrace.requestLimit(q)==MotionTrace.CAPACITY,"MT01_default_bounded_capacity");
        q.addProperty("limit",17);check(MotionTrace.requestLimit(q)==17,"MT02_explicit_limit");
        for(JsonElement value:new JsonElement[]{new JsonPrimitive(0),new JsonPrimitive(4097),new JsonPrimitive(1.5),new JsonPrimitive(true),JsonNull.INSTANCE}) {
            q.add("limit",value);rejected(()->MotionTrace.requestLimit(q),"MT03_strict_limit");
        }
        String source=Files.readString(Path.of("src/main/java/dev/blockwire/Blockwire.java"));
        check(source.contains("END_CLIENT_TICK.register") && source.contains("motionTrace.sample"),"MT04_end_tick_sampling");
        String branch=source.substring(source.indexOf("case \"motion_trace\" ->"),source.indexOf("case \"inventory\" ->"));
        check(branch.contains("Protocol.fields(q,\"limit\",\"reset\",\"actor_session\")"),"MT05_strict_envelope");
        check(branch.contains("if(q.has(\"actor_session\"))guardedActor(q);") && branch.indexOf("guardedActor")<branch.indexOf("motionTrace.reset"),"MT06_actor_fence_before_reset");
        String trace=Files.readString(Path.of("src/main/java/dev/blockwire/MotionTrace.java"));
        check(trace.contains("samples.size()==CAPACITY") && trace.contains("samples.removeFirst()"),"MT07_ring_is_bounded");
        check(trace.contains("getDeltaMovement") && trace.contains("horizontalCollision") && trace.contains("remote_owned_inputs"),"MT08_native_not_predicted_telemetry");
        System.out.println("BLOCKWIRE_MOTION_TRACE_CONTRACT_PASS checks="+checks);
    }
}
