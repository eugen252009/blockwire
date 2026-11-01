package dev.blockwire;

import com.google.gson.*;
import java.nio.file.*;
import java.util.*;

/** Parser and source wiring contracts only, not graphical command acceptance. */
public final class CommandContractTest {
    private static int checks;
    private static void check(boolean ok,String name){if(!ok)throw new AssertionError(name);checks++;}
    private static JsonObject request(String command) {
        var q=new JsonObject();q.addProperty("op","command");q.addProperty("command",command);return q;
    }
    private static void rejected(JsonObject q,String name) {
        try{Protocol.command(q);throw new AssertionError(name);}catch(IllegalArgumentException expected){checks++;}
    }
    public static void main(String[] args) throws Exception {
        check(Protocol.command(request("/time set day")).equals("time set day"),"CMD01_strip_one_slash");
        check(Protocol.command(request("/x "+"a".repeat(253))).length()==255,"CMD02_maximum_boundary");
        check(Protocol.command(request("/x 😀")).equals("x 😀"),"CMD03_unicode_preserved");
        check(Protocol.command(request("/x a/b; c")).equals("x a/b; c"),"CMD04_no_split_or_rewrite");
        for(String text:List.of("","/","time set day","//time","/ time","/\u00a0time"))
            rejected(request(text),"CMD05_explicit_slash_command");
        rejected(request("/"+"a".repeat(256)),"CMD06_reject_oversized");
        for(String text:List.of("/x\nstop","/x\rstop","/x\tstop","/x\0stop","/x\u007f",
                "/x\u0085","/x§a","/x\u2028stop","/x\u2029stop","/x\ud800","/x\udc00","/x\ud800a"))
            rejected(request(text),"CMD07_reject_controls_and_malformed_unicode");
        for(JsonElement value:List.of(JsonNull.INSTANCE,new JsonPrimitive(true),new JsonPrimitive(2),new JsonArray())) {
            var q=request("/help");q.add("command",value);rejected(q,"CMD08_strict_string");
        }
        var q=request("/help");q.addProperty("typo",true);rejected(q,"CMD09_unknown_field");
        q=request("/help");q.addProperty("actor_session",false);rejected(q,"CMD10_strict_actor_token");
        q=request("/help");q.addProperty("actor_session","a");
        check(Protocol.command(q).equals("help"),"CMD11_optional_actor_token");
        String source=Files.readString(Path.of("src/main/java/dev/blockwire/Blockwire.java"));
        String command=source.substring(source.indexOf("case \"command\" ->"),source.indexOf("case \"respawn\" ->"));
        check(command.contains("Protocol.command(q);guardedActor(q);playing();") &&
            command.indexOf("playing();")<command.indexOf("sendCommand(command)"),"CMD12_validate_and_fence_before_effect");
        check(command.contains("release();mc.player.connection.sendCommand(command);"),"CMD13_release_and_native_submission");
        check(command.contains("receipt.addProperty(\"submitted\",true)") && !command.contains("\"succeeded\""),
            "CMD14_submission_not_success");
        System.out.println("BLOCKWIRE_COMMAND_CONTRACT_PASS checks="+checks);
    }
}
