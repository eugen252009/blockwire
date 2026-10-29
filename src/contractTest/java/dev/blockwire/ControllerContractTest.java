package dev.blockwire;

import com.google.gson.*;
import java.nio.file.*;
import java.util.*;

/** Deterministic native lease/parser/wiring contracts; not graphical gameplay acceptance. */
public final class ControllerContractTest {
    private static int checks;
    private static void check(boolean ok,String name){if(!ok)throw new AssertionError(name);checks++;}
    private static void rejected(Runnable action,String name) {
        try{action.run();throw new AssertionError(name);}catch(IllegalArgumentException expected){checks++;}
    }
    public static void main(String[] args) throws Exception {
        var q=JsonParser.parseString("{\"op\":\"drive\",\"ticks\":8,\"button_ticks\":{\"forward\":1,\"use\":8}}").getAsJsonObject();
        var buttons=Set.of("forward","use");
        var parsed=Protocol.buttonTicks(q,buttons,8);
        check(parsed.equals(Map.of("forward",1,"use",8)),"CL01_independent_key_durations");
        var leases=new InputLeases();leases.reset(parsed,0);
        check(leases.expire(0).isEmpty(),"CL02_initial_hold");
        check(leases.active("forward",49_999_999L) && !leases.active("forward",50_000_000L) &&
            leases.active("use",50_000_000L),"CL23_per_key_attack_clock_not_global_food_clock");
        check(leases.expire(50_000_000L).equals(Set.of("forward")),"CL03_short_walk_expires_while_food_remains");
        check(leases.expire(399_999_999L).isEmpty(),"CL04_food_not_prematurely_released");
        check(leases.expire(400_000_000L).equals(Set.of("use")),"CL05_monotonic_deadline_bounds_food");
        check(leases.expire(500_000_000L).isEmpty(),"CL06_expiry_is_consumed");
        leases.reset(Map.of("use",8),0);
        for(int i=0;i<8;i++)check(leases.expire(0).isEmpty(),"CL07_tick_lease_remains_bounded");
        check(leases.expire(0).equals(Set.of("use")),"CL08_tick_expiry_without_clock_progress");
        leases.reset(Map.of("use",8),0);leases.reset(Map.of("forward",1),0);
        check(leases.expire(400_000_000L).equals(Set.of("forward")),"CL09_replace_does_not_retain_old_use");
        leases.reset(Map.of("use",8),0);leases.clear();
        check(leases.expire(400_000_000L).isEmpty(),"CL10_cleanup_clears_all_key_leases");
        for(String invalid:List.of("null","[]","{\"forward\":1,\"use\":8,\"attack\":1}",
                "{\"forward\":true,\"use\":8}","{\"forward\":\"1\",\"use\":8}",
                "{\"forward\":1.5,\"use\":8}","{\"forward\":0,\"use\":8}",
                "{\"forward\":1,\"use\":9}")) {
            q.add("button_ticks",JsonParser.parseString(invalid));
            rejected(()->Protocol.buttonTicks(q,buttons,8),"CL11_reject_invalid_key_lease");
        }
        q.add("button_ticks",JsonParser.parseString("{\"use\":8}"));
        check(Protocol.buttonTicks(q,buttons,8).equals(Map.of("use",8)),"CL25_sparse_map_retains_other_keys");
        leases.reset(Map.of("forward",1,"use",8),0);
        leases.replace(buttons,Map.of("use",8),49_999_999L);
        check(leases.expire(50_000_000L).equals(Set.of("forward")),"CL26_food_renewal_never_extends_short_walk");
        check(leases.replace(buttons,Map.of("use",8),60_000_000L).equals(Set.of("use")),
            "CL27_expired_walk_never_resurrected_by_food_renewal");
        leases.reset(Map.of("forward",1,"use",8),0);leases.expire(0);
        leases.replace(buttons,Map.of("use",8),0);
        check(leases.expire(0).equals(Set.of("forward")),"CL29_food_renewal_retains_walk_tick_budget");
        leases.reset(Map.of("use",8),0);leases.cap(1,10_000_000L);
        check(!leases.active("use",60_000_000L) && leases.replace(Set.of("use"),Map.of(),70_000_000L).isEmpty(),
            "CL28_enclosing_lease_shortens_retained_keys_without_resurrection");
        q.remove("button_ticks");
        check(Protocol.buttonTicks(q,buttons,8).equals(Map.of("forward",8,"use",8)),"CL12_legacy_drive_duration_unchanged");
        q.add("button_ticks",new JsonObject());
        check(Protocol.buttonTicks(q,Set.of(),1).isEmpty(),"CL13_empty_input_release");

        var hotbar=JsonParser.parseString("{\"op\":\"hotbar\",\"slot\":8,\"actor_session\":\"a\"}").getAsJsonObject();
        check(Protocol.hotbarSlot(hotbar)==8,"CL14_guarded_hotbar_boundary");
        hotbar.remove("actor_session");check(Protocol.hotbarSlot(hotbar)==8,"CL15_legacy_hotbar_unchanged");
        for(JsonElement invalid:List.of(JsonNull.INSTANCE,new JsonPrimitive(true),new JsonPrimitive(42))) {
            hotbar.add("actor_session",invalid);
            rejected(()->Protocol.hotbarSlot(hotbar),"CL16_reject_invalid_actor_token");
        }
        hotbar.remove("actor_session");hotbar.addProperty("slot",9);
        rejected(()->Protocol.hotbarSlot(hotbar),"CL17_reject_invalid_hotbar_slot");
        hotbar.addProperty("slot",0);hotbar.addProperty("typo",1);
        rejected(()->Protocol.hotbarSlot(hotbar),"CL18_reject_unknown_hotbar_field");

        // Wiring checks complement the pure contracts; they do NOT simulate a real LocalPlayer.
        String source=Files.readString(Path.of("src/main/java/dev/blockwire/Blockwire.java"));
        String selection=source.substring(source.indexOf("case \"hotbar\" ->"),source.indexOf("case \"open_inventory\" ->"));
        check(selection.contains("Protocol.hotbarSlot(q);guardedActor(q);playing();") &&
            selection.indexOf("guardedActor(q)")<selection.indexOf("setSelectedSlot"),"CL19_hotbar_actor_guard_before_effect");
        check(source.contains("var leases=Protocol.buttonTicks(q,buttons,ticks);") &&
            source.contains("inputLeases.replace(buttons,leases,System.nanoTime())") &&
            source.contains("inputLeases.cap(ticks,System.nanoTime());"),"CL20_drive_installs_validated_leases");
        check(source.contains("var expired=inputLeases.expire(System.nanoTime());") &&
            source.contains("remaining.removeAll(expired)"),"CL21_tick_releases_only_expired_keys");
        check(source.contains("held=Set.of();inputLeases.clear();"),"CL22_global_cleanup_clears_leases");
        check(source.contains("inputLeases.active(\"attack\",System.nanoTime())"),"CL24_native_mining_uses_own_key_clock");
        System.out.println("BLOCKWIRE_CONTROLLER_CONTRACT_PASS checks="+checks);
    }
}
