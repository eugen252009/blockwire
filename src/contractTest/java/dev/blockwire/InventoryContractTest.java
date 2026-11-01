package dev.blockwire;

import com.google.gson.JsonObject;

/** Strict optional inventory actor envelopes; native execution is qualified separately. */
public final class InventoryContractTest {
    private static int checks;
    private static void bad(Runnable action) {
        checks++;
        try { action.run(); } catch(IllegalArgumentException expected) { return; }
        throw new AssertionError("invalid inventory envelope accepted");
    }
    private static void require(boolean condition,String label) {
        checks++;if(!condition)throw new AssertionError(label);
    }
    public static void main(String[] args) throws Exception {
        for(String op:new String[]{"open_inventory","close_screen","click_slot","respawn"}) {
            var q=new JsonObject();q.addProperty("op",op);
            Protocol.inventoryFields(q);checks++;
            q.addProperty("actor_session","fixture");Protocol.inventoryFields(q);checks++;
            q.addProperty("actor_session",1);bad(()->Protocol.inventoryFields(q));
            q.addProperty("actor_session",true);bad(()->Protocol.inventoryFields(q));
            q.add("actor_session",new JsonObject());bad(()->Protocol.inventoryFields(q));
            q.addProperty("actor_session","fixture");q.addProperty("typo",1);bad(()->Protocol.inventoryFields(q));
        }
        var click=new JsonObject();click.addProperty("actor_session","a");click.addProperty("slot",0);
        Protocol.inventoryFields(click,"slot");checks++;
        bad(()->Protocol.inventoryFields(click));
        String source=java.nio.file.Files.readString(java.nio.file.Path.of("src/main/java/dev/blockwire/Blockwire.java"));
        String open=source.substring(source.indexOf("case \"open_inventory\""),source.indexOf("case \"close_screen\""));
        String close=source.substring(source.indexOf("case \"close_screen\""),source.indexOf("case \"click_slot\""));
        String clickSource=source.substring(source.indexOf("case \"click_slot\""),source.indexOf("case \"command\""));
        require(open.contains("guardedActor(q);playing();release();"),"IV01_open_actor_guard_before_effect");
        require(close.contains("guardedActor(q);playerRequired();"),"IV02_close_actor_guard_before_effect");
        require(clickSource.contains("guardedActor(q);playerRequired();") && clickSource.indexOf("guardedActor(q)")<clickSource.indexOf("handleContainerInput"),"IV03_click_actor_guard_before_effect");
        String respawn=source.substring(source.indexOf("case \"respawn\""),source.indexOf("default ->",source.indexOf("case \"respawn\"")));
        require(respawn.contains("Protocol.inventoryFields(q);guardedActor(q);playerRequired();") && respawn.indexOf("guardedActor(q)")<respawn.indexOf("mc.player.respawn()"),"IV04_respawn_actor_guard_before_effect");
        System.out.println("BLOCKWIRE_INVENTORY_CONTRACT_PASS checks="+checks);
    }
}
