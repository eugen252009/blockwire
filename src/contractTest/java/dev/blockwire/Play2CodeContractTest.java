package dev.blockwire;

import com.google.gson.*;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.*;

/** File/lifecycle/wiring contracts only; graphical human recording is a separate native smoke. */
public final class Play2CodeContractTest {
    private static int checks;
    private static void check(boolean value,String label){checks++;if(!value)throw new AssertionError(label);}
    public static void main(String[] args) throws Exception {
        Path root=Files.createTempDirectory("blockwire-play2code-");
        try {
            var start=new JsonObject();start.addProperty("control_endpoint_running",false);start.addProperty("actor_session","actor-a");
            var capture=Play2CodeCapture.start(root,start);Path directory=capture.directory();
            var tick=new JsonObject();tick.addProperty("client_tick",0);tick.add("remote_owned_inputs",new JsonArray());
            check(capture.append("tick",tick)==1,"P2C01_append_only_sequence");
            var stop=new JsonObject();stop.addProperty("requested",true);
            var metadata=new JsonObject();metadata.addProperty("no_remote_controller_interference",true);
            capture.finish("completed","user_requested",stop,metadata);
            var lines=Files.readAllLines(directory.resolve("raw-timeline.jsonl"));
            check(lines.size()==3,"P2C02_start_tick_stop_timeline");
            for(int i=0;i<lines.size();i++) {
                var event=JsonParser.parseString(lines.get(i)).getAsJsonObject();
                check(event.get("schema").getAsString().equals(Play2CodeCapture.EVENT_SCHEMA) &&
                      event.get("sequence").getAsLong()==i,"P2C03_typed_ordered_events");
            }
            var sealed=JsonParser.parseString(Files.readString(directory.resolve("capture.json"))).getAsJsonObject();
            check(sealed.get("schema").getAsString().equals(Play2CodeCapture.CAPTURE_SCHEMA) &&
                  sealed.get("status").getAsString().equals("completed") && sealed.get("timeline_sealed").getAsBoolean() &&
                  sealed.get("event_count").getAsLong()==3,"P2C04_sealed_metadata");
            if(FileSystems.getDefault().supportedFileAttributeViews().contains("posix")) {
                check(Files.getPosixFilePermissions(directory).equals(PosixFilePermissions.fromString("rwx------")),"P2C05_private_directory");
                check(Files.getPosixFilePermissions(directory.resolve("raw-timeline.jsonl")).equals(PosixFilePermissions.fromString("rw-------")),"P2C06_private_timeline");
                Path link=root.resolve("link");Files.createSymbolicLink(link,directory);
                try {Play2CodeCapture.start(link,new JsonObject());throw new AssertionError("symlink root accepted");}
                catch(java.io.IOException expected){checks++;}
            }
        } finally {TlsContractTest.deleteTree(root);}

        check(Play2CodeCapture.MAX_EVENTS==300_000 && Play2CodeCapture.MAX_BYTES==256L*1024*1024 &&
              Play2CodeCapture.MAX_EVENT_BYTES==128*1024,"P2C17_capture_bounds_are_explicit");
        String blockwire=Files.readString(Path.of("src/main/java/dev/blockwire/Blockwire.java"));
        check(blockwire.contains("InputConstants.KEY_F9") && blockwire.contains("InputConstants.KEY_F10") &&
              blockwire.contains("play2Code.sample(client,session,held,currentKeys,server!=null)"),"P2C07_local_keys_and_end_tick_sampling");
        check(blockwire.contains("else {play2Code.abort(\"control_endpoint_enabled\");startServer();}"),"P2C08_endpoint_enable_invalidates_recording_first");
        check(blockwire.contains("Blockwire.toggleKey(key)") || Files.readString(Path.of("src/main/java/dev/blockwire/mixin/MinecraftInputMixin.java")).contains("Blockwire.toggleKey(key)"),
              "P2C09_F8_path_retained");
        check(!blockwire.contains("case \"play2code") && !blockwire.contains("case \"recording_"),"P2C10_no_remote_recorder_RPC");
        String recorder=Files.readString(Path.of("src/main/java/dev/blockwire/Play2CodeRecorder.java"));
        check(recorder.contains("if(endpointRunning){endpointEnabled=true;abort(\"control_endpoint_enabled\");return;}") &&
              recorder.contains("if(!remotelyOwned.isEmpty())") && recorder.indexOf("if(endpointRunning)")<recorder.indexOf("append(\"tick\""),
              "P2C11_remote_interference_fails_before_sample");
        check(recorder.contains("mc.player!=actor || mc.level!=level") && recorder.contains("actor_or_world_replaced"),"P2C12_actor_world_fence");
        check(Play2CodeRecorder.CONFIRM_TICKS>=3 && recorder.contains("client_world_state_stable_"),"P2C13_mutation_requires_stable_observation");
        check(!recorder.contains("InputState.set") && !recorder.contains("player.drive") && !recorder.contains("setSelectedSlot") &&
              !recorder.contains("blockwire$attack") && !recorder.contains("blockwire$use"),"P2C14_recorder_has_no_control_effects");
        String mixin=Files.readString(Path.of("src/main/java/dev/blockwire/mixin/Play2CodeInteractionMixin.java"));
        check(mixin.contains("startDestroyBlock") && mixin.contains("useItemOn") && mixin.contains("@At(\"HEAD\")"),"P2C15_native_interaction_correlation_hooks");
        String mixins=Files.readString(Path.of("src/main/resources/blockwire.mixins.json"));
        check(mixins.contains("Play2CodeInteractionMixin"),"P2C16_mixin_registered");
        System.out.println("BLOCKWIRE_PLAY2CODE_CONTRACT_PASS checks="+checks);
    }
}
