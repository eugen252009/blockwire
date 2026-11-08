package dev.blockwire;

import com.google.gson.*;
import net.minecraft.SharedConstants;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.core.Direction;
import java.nio.file.*;

/** Schema/state/policy contracts. GUI/native placement dispatch checks are STATIC, not gameplay. */
public final class CreativeBuildContractTest {
    private static int checks;
    private static void check(boolean ok,String name){checks++;if(!ok)throw new AssertionError(name);}
    private static void bad(Runnable call,String name){try{call.run();throw new AssertionError(name);}catch(IllegalArgumentException|IllegalStateException expected){checks++;}}
    private static JsonObject request(String action){var q=new JsonObject();q.addProperty("op","creative");q.addProperty("actor_session","actor");q.addProperty("action",action);return q;}
    private static JsonObject material(){var q=request("material");q.addProperty("item","minecraft:oak_log");q.addProperty("slot",0);q.addProperty("expected_item","");q.addProperty("expected_count",0);return q;}
    private static JsonObject positional(String action){var q=request(action);q.addProperty("token","a".repeat(64));q.add("position",JsonParser.parseString("[1,64,-2]"));return q;}
    public static void main(String[] args)throws Exception{
        SharedConstants.tryDetectVersion();Bootstrap.bootStrap();
        check(CreativeBuild.request(request("probe")).action().equals("probe"),"CB01_probe");
        var supply=material();check(CreativeBuild.request(supply).slot()==0,"CB02_material");
        for(String item:new String[]{"minecraft:air","minecraft:command_block","minecraft:diamond_sword","/give", "mod:oak_log"}){
            var q=material();q.addProperty("item",item);bad(()->CreativeBuild.request(q),"CB03_material_allowlist");
        }
        for(JsonElement value:new JsonElement[]{new JsonPrimitive(true),new JsonPrimitive("1"),new JsonPrimitive(-1),new JsonPrimitive(9)}){
            var q=material();q.add("slot",value);bad(()->CreativeBuild.request(q),"CB04_slot_types_and_bounds");
        }
        var count=material();count.addProperty("expected_count",1);bad(()->CreativeBuild.request(count),"CB05_slot_assertion");
        var unknown=material();unknown.addProperty("nbt","{}");bad(()->CreativeBuild.request(unknown),"CB06_no_nbt");
        for(String action:new String[]{"probe","material","check","place","remove","remember","toggle"}){
            var q=request(action);q.remove("actor_session");bad(()->CreativeBuild.request(q),"CB07_actor_mandatory");
        }
        var actor=request("probe");actor.addProperty("actor_session",1);bad(()->CreativeBuild.request(actor),"CB08_actor_type");
        var empty=request("probe");empty.addProperty("actor_session","");bad(()->CreativeBuild.request(empty),"CB09_actor_empty");
        for(String action:new String[]{"place","remember"})check(CreativeBuild.request(positional(action)).position().getY()==64,"CB10_target");
        var toggle=positional("toggle");toggle.addProperty("open",true);check(CreativeBuild.request(toggle).open(),"CB11_toggle");
        toggle.addProperty("open","true");bad(()->CreativeBuild.request(toggle),"CB12_open_bool");
        for(JsonElement value:new JsonElement[]{JsonParser.parseString("[true,64,0]"),JsonParser.parseString("[1,2]"),JsonParser.parseString("[1,2049,0]"),JsonParser.parseString("[30000000,64,0]")}){
            var q=positional("place");q.add("position",value);bad(()->CreativeBuild.request(q),"CB13_coordinate_bound");
        }
        var token=positional("place");token.addProperty("token","guess");bad(()->CreativeBuild.request(token),"CB14_token");
        var remove=positional("remove");bad(()->CreativeBuild.request(remove),"CB15_remove_needs_owned_ticket");
        remove.addProperty("ticket","b".repeat(64));check(CreativeBuild.request(remove).ticket().length()==64,"CB16_remove");
        var read=request("check");read.addProperty("ticket","b".repeat(64));check(CreativeBuild.request(read).position()==null,"CB17_ticket_not_coordinates");
        read.add("position",JsonParser.parseString("[0,64,0]"));bad(()->CreativeBuild.request(read),"CB18_no_coordinate_read");
        bad(()->CreativeBuild.request(request("fly")),"CB19_no_fly_action");
        CreativeBuild.requireMode(true,false,true,true);checks++;
        bad(()->CreativeBuild.requireMode(false,false,true,true),"CB20_creative_only");
        bad(()->CreativeBuild.requireMode(true,true,true,false),"CB21_no_flight");
        bad(()->CreativeBuild.requireMode(true,false,false,true),"CB22_ground_for_use");
        CreativeBuild.requireMode(true,false,false,false);checks++;
        CreativeBuild.requireJump(true,true,0);CreativeBuild.requireJump(false,false,7);checks+=2;
        bad(()->CreativeBuild.requireJump(true,true,1),"CB23_native_double_tap_window");
        bad(()->CreativeBuild.requireJump(true,false,0),"CB24_no_airborne_jump_rise");
        var state=CreativeBuild.state(Blocks.OAK_LOG.defaultBlockState().setValue(BlockStateProperties.AXIS,Direction.Axis.Z));
        check(state.get("id").getAsString().equals("minecraft:oak_log") && state.getAsJsonObject("properties").get("axis").getAsString().equals("z"),"CB25_exact_native_axis");
        check(CreativeBuild.state(Blocks.SPRUCE_DOOR.defaultBlockState()).getAsJsonObject("properties").size()==5,"CB26_native_door_properties");
        String source=Files.readString(Path.of("src/main/java/dev/blockwire/CreativeBuild.java"));
        check(source.contains("ContainerInput.SWAP") && source.contains("screen.charTyped(new CharacterEvent(c))"),"CB27_STATIC_native_catalog_path");
        check(!source.contains(".setItem(") && !source.contains(".setCount(") && !source.contains(".setBlock(") && !source.contains("sendCommand("),"CB28_STATIC_no_direct_world_inventory_commands");
        check(source.contains("previous.getComponentsPatch().isEmpty()") && source.contains("previous.getCount()==r.expectedCount") && source.contains("creative_slot_changed"),"CB29_STATIC_inventory_assertions");
        check(source.contains("destination_was_air") && source.contains("world.getBlockState(dest).isAir()"),"CB30_STATIC_no_overwrite");
        check(source.contains("owner.placed") && source.contains("owner.block.equals(\"minecraft:cobblestone\")") && source.contains("cannot_remove_own_support"),"CB31_STATIC_owned_scaffold_guards");
        check(source.contains("world.hasChunkAt(p)") && source.contains("watches.size()<MAX_WATCHES"),"CB32_STATIC_watch_bounds");
        check(source.contains("useItemOn(actor,InteractionHand.MAIN_HAND,p.hit)") && source.contains("startDestroyBlock(r.position,p.hit.getDirection())"),"CB33_STATIC_native_actions");
        String dispatch=Files.readString(Path.of("src/main/java/dev/blockwire/Blockwire.java"));
        check(dispatch.contains("CreativeBuild.request(q);guardedActor(q);playing();"),"CB34_STATIC_fence_before_effect");
        check(dispatch.contains("autoEvents.disable();creativeBuild.clear();release();"),"CB35_STATIC_disconnect_and_F8_clear");
        check(dispatch.contains("CreativeBuild.guardedInput(mc,q,actor==mc.player && world==mc.level?held:Set.of(),buttons)"),"CB36_STATIC_guard_before_drive");
        check(dispatch.indexOf("CreativeBuild.guardedInput(mc,q,actor==mc.player")<dispatch.indexOf("var next=inputLeases.replace"),"CB37_STATIC_order");
        check(source.contains("!world.isOutsideBuildHeight(dest)") && source.contains("world.getWorldBorder().isWithinBounds(dest)"),"CB38_STATIC_dimension_border");
        check(source.contains("if(!result.consumesAction()){watches.remove(ticket);"),"CB39_STATIC_rejected_use_no_ownership");
        check(net.minecraft.world.entity.player.Player.class.getDeclaredField("jumpTriggerTime").getType()==int.class,"CB40_accessor_target_signature_only");
        Class<?> screen=net.minecraft.client.gui.screens.inventory.CreativeModeInventoryScreen.class;
        check(screen.getDeclaredMethod("selectTab",net.minecraft.world.item.CreativeModeTab.class).getReturnType()==void.class,"CB41_tab_invoker_signature_only");
        check(screen.getDeclaredMethod("slotClicked",net.minecraft.world.inventory.Slot.class,int.class,int.class,net.minecraft.world.inventory.ContainerInput.class).getReturnType()==void.class,"CB42_slot_invoker_signature_only");
        check(source.contains("getDeltaMovement().horizontalDistanceSqr()<.0025"),"CB43_STATIC_grounded_gravity_is_not_horizontal_motion");
        check(CreativeBuild.MAX_WATCHES==4096,"CB44_watch_budget");
        System.out.println("BLOCKWIRE_CREATIVE_BUILD_CONTRACT_PASS checks="+checks+" graphical=NOT_RUN");
    }
}
