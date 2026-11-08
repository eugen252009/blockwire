package dev.blockwire;

import com.google.gson.*;
import dev.blockwire.mixin.CreativeInventoryAccess;
import dev.blockwire.mixin.PlayerJumpAccess;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.inventory.CreativeModeInventoryScreen;
import net.minecraft.client.input.CharacterEvent;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.*;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.GameType;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.Property;
import net.minecraft.world.phys.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;

/** Explicit native Creative mechanics, not a blueprint, route or scaffold planner. */
public final class CreativeBuild {
    public static final String PROFILE="grounded_creative_v1";
    public static final int MAX_WATCHES=4096;
    public static final Set<String> FULL=Set.of("minecraft:stone","minecraft:cobblestone","minecraft:stone_bricks",
        "minecraft:dirt","minecraft:grass_block","minecraft:oak_planks","minecraft:oak_log","minecraft:oak_wood");
    public static final Set<String> ITEMS;
    static {var items=new HashSet<>(FULL);items.addAll(Set.of("minecraft:oak_stairs","minecraft:glass_pane","minecraft:spruce_door"));ITEMS=Set.copyOf(items);}
    public record Request(String action,String actor,String item,int slot,String expectedItem,int expectedCount,
                          String token,BlockPos position,String ticket,Boolean open) {}
    private record Watch(List<BlockPos> positions,boolean placed,String block) {}
    private record Probe(BlockHitResult hit,BlockPlaceContext context,BlockState candidate,JsonObject value) {}
    private LocalPlayer actor;
    private ClientLevel world;
    private final Map<String,Watch> watches=new LinkedHashMap<>();

    public void clear(){watches.clear();actor=null;world=null;}
    private void bind(Minecraft mc){if(actor!=mc.player || world!=mc.level){clear();actor=mc.player;world=mc.level;}}
    private static void need(boolean condition,String reason){if(!condition)throw new IllegalStateException(reason);}
    private static String bounded(JsonObject q,String field,int length){
        String value=Protocol.string(q,field);
        if(value.isEmpty() || value.length()>length)throw new IllegalArgumentException("invalid_"+field);
        return value;
    }
    private static String digestField(JsonObject q,String field){
        String value=bounded(q,field,64);
        if(!value.matches("[a-f0-9]{64}"))throw new IllegalArgumentException("invalid_"+field);
        return value;
    }
    private static BlockPos position(JsonObject q){
        if(!q.has("position") || !q.get("position").isJsonArray() || q.getAsJsonArray("position").size()!=3)
            throw new IllegalArgumentException("expected_block_position");
        var a=q.getAsJsonArray("position");var row=new JsonObject();
        row.add("x",a.get(0));row.add("y",a.get(1));row.add("z",a.get(2));
        return new BlockPos(Protocol.integer(row,"x",-29999984,29999984),Protocol.integer(row,"y",-2048,2048),Protocol.integer(row,"z",-29999984,29999984));
    }
    public static Request request(JsonObject q){
        String action=bounded(q,"action",16),session=bounded(q,"actor_session",128);
        String item=null,old=null,token=null,ticket=null;int slot=-1,count=-1;BlockPos pos=null;Boolean open=null;
        switch(action){
            case "probe" -> Protocol.fields(q,"action","actor_session");
            case "material" -> {
                Protocol.fields(q,"action","actor_session","item","slot","expected_item","expected_count");
                item=bounded(q,"item",128);old=Protocol.string(q,"expected_item");
                if(!ITEMS.contains(item) || !(old.isEmpty() || ITEMS.contains(old)))throw new IllegalArgumentException("unsupported_creative_item");
                slot=Protocol.integer(q,"slot",0,8);count=Protocol.integer(q,"expected_count",0,64);
                if(old.isEmpty() != (count==0))throw new IllegalArgumentException("invalid_slot_assertion");
            }
            case "place","remember","toggle" -> {
                Protocol.fields(q,action.equals("toggle")?new String[]{"action","actor_session","token","position","open"}:
                    new String[]{"action","actor_session","token","position"});
                token=digestField(q,"token");pos=position(q);
                if(action.equals("toggle")){if(!q.has("open"))throw new IllegalArgumentException("expected_open");open=Protocol.bool(q,"open",false);}
            }
            case "check" -> {Protocol.fields(q,"action","actor_session","ticket");ticket=digestField(q,"ticket");}
            case "remove" -> {
                Protocol.fields(q,"action","actor_session","ticket","token","position");
                ticket=digestField(q,"ticket");token=digestField(q,"token");pos=position(q);
            }
            default -> throw new IllegalArgumentException("unsupported_creative_action");
        }
        return new Request(action,session,item,slot,old,count,token,pos,ticket,open);
    }
    public static void requireMode(boolean creative,boolean flying,boolean ground,boolean requireGround){
        need(creative,"creative_mode_required");need(!flying,"flight_not_allowed");
        need(!requireGround || ground,"grounded_player_required");
    }
    public static void requireJump(boolean rising,boolean grounded,int nativeDoubleTapTimer){
        need(!rising || (grounded && nativeDoubleTapTimer==0),"flight_toggle_risk");
    }
    public static void guardedInput(Minecraft mc,JsonObject q,Set<String> held,Set<String> wanted){
        if(!Protocol.bool(q,"grounded_creative",false))return;
        bounded(q,"actor_session",128);
        requireMode(mc.gameMode.getPlayerMode()==GameType.CREATIVE,mc.player.getAbilities().flying,mc.player.onGround(),false);
        need(!mc.player.isFallFlying() && !mc.player.isPassenger(),"unsupported_grounded_travel");
        if(wanted!=null){
            need(Protocol.integer(q,"ticks",1,100)<=8 && !wanted.contains("attack") && !wanted.contains("use"),"grounded_input_bound");
            requireJump(wanted.contains("jump") && !held.contains("jump"),mc.player.onGround(),
                ((PlayerJumpAccess)(Object)mc.player).blockwire$jumpTriggerTime());
        }
    }
    private void grounded(Minecraft mc){
        requireMode(mc.gameMode.getPlayerMode()==GameType.CREATIVE,mc.player.getAbilities().flying,mc.player.onGround(),true);
        need(!mc.player.isPassenger() && !mc.player.isFallFlying(),"unsupported_grounded_travel");
        // A grounded vanilla player can retain the ordinary gravity Y velocity.
        need(mc.player.getDeltaMovement().horizontalDistanceSqr()<.0025,"settled_player_required");
    }
    private static String id(BlockState state){return BuiltInRegistries.BLOCK.getKey(state.getBlock()).toString();}
    private static String itemId(ItemStack stack){return stack.isEmpty()?"":BuiltInRegistries.ITEM.getKey(stack.getItem()).toString();}
    private static <T extends Comparable<T>> void property(JsonObject out,BlockState state,Property<T> key){out.addProperty(key.getName(),key.getName(state.getValue(key)));}
    public static JsonObject state(BlockState state){
        need(state.getProperties().size()<=32,"creative_state_property_budget");
        var out=new JsonObject();out.addProperty("id",id(state));var props=new JsonObject();
        state.getProperties().stream().sorted(Comparator.comparing(Property::getName)).forEach(key->property(props,state,key));
        out.add("properties",props);return out;
    }
    private static JsonArray vector(BlockPos p){var a=new JsonArray();a.add(p.getX());a.add(p.getY());a.add(p.getZ());return a;}
    private static String hash(String value){
        try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8)));}
        catch(java.security.NoSuchAlgorithmException e){throw new IllegalStateException(e);}
    }
    private JsonObject envelope(String session){
        var out=new JsonObject();out.addProperty("profile",PROFILE);out.addProperty("actor_session",session);
        out.addProperty("actor_tick",actor.tickCount);return out;
    }
    private void loaded(BlockPos p){need(world.hasChunkAt(p),"creative_observation_unloaded");}
    private Probe probe(Minecraft mc,String session){
        var out=envelope(session);out.addProperty("hit",false);out.addProperty("placement_available",false);
        // Native player-eye ray, normal reach capped at three blocks; no arbitrary origin.
        var hit=actor.pick(Math.min(3.,actor.blockInteractionRange()),1,false);
        if(!(hit instanceof BlockHitResult block) || hit.getType()!=HitResult.Type.BLOCK)return new Probe(null,null,null,out);
        BlockPos p=block.getBlockPos();loaded(p);BlockState support=world.getBlockState(p);
        out.addProperty("hit",true);out.add("position",vector(p));out.addProperty("face",block.getDirection().getName());out.add("state",state(support));
        var aim=new JsonArray();aim.add(block.getLocation().x);aim.add(block.getLocation().y);aim.add(block.getLocation().z);out.add("aim_position",aim);
        String pose=actor.position()+"/"+actor.getYRot()+"/"+actor.getXRot()+"/"+actor.getEyeHeight();
        String hitToken=hash(session+"/"+pose+"/"+p+"/"+block.getDirection()+"/"+block.getLocation()+"/"+state(support));out.addProperty("hit_token",hitToken);
        ItemStack stack=actor.getMainHandItem();BlockPlaceContext context=null;BlockState candidate=null;
        if(FULL.contains(id(support)) && support.getFluidState().isEmpty() && support.isCollisionShapeFullBlock(world,p)
            && ITEMS.contains(itemId(stack)) && stack.getComponentsPatch().isEmpty() && stack.getItem() instanceof BlockItem item){
            context=item.updatePlacementContext(new BlockPlaceContext(actor,InteractionHand.MAIN_HAND,stack,block));
            if(context!=null){
                BlockPos dest=context.getClickedPos();loaded(dest);
                boolean empty=world.getBlockState(dest).isAir() && !world.isOutsideBuildHeight(dest) && world.getWorldBorder().isWithinBounds(dest);
                if(itemId(stack).equals("minecraft:spruce_door")){loaded(dest.above());empty &= world.getBlockState(dest.above()).isAir() && !world.isOutsideBuildHeight(dest.above());}
                if(empty && context.canPlace())candidate=item.getBlock().getStateForPlacement(context);
                if(candidate!=null && (!candidate.canSurvive(world,dest) || !world.isUnobstructed(candidate,dest,net.minecraft.world.phys.shapes.CollisionContext.of(actor))))candidate=null;
                if(candidate!=null){
                    out.addProperty("placement_available",true);out.add("destination",vector(dest));out.add("candidate",state(candidate));
                    out.addProperty("destination_was_air",true);
                    // The token deliberately excludes actor_tick: a newer tick is allowed,
                    // but pose, ray, held stack and native placement prediction must agree.
                    out.addProperty("placement_token",hash(session+"/"+pose+"/"+p+"/"+block.getLocation()+"/"+block.getDirection()+"/"+
                        state(support)+"/"+dest+"/"+state(candidate)+"/"+itemId(stack)+"/"+stack.getCount()));
                }
            }
        }
        return new Probe(block,context,candidate,out);
    }
    private String watch(List<BlockPos> positions,boolean placed,String block){
        need(watches.size()<MAX_WATCHES,"creative_watch_budget");
        String ticket=hash(UUID.randomUUID().toString());watches.put(ticket,new Watch(List.copyOf(positions),placed,block));return ticket;
    }
    private JsonObject check(String session,String ticket){
        Watch watched=watches.get(ticket);need(watched!=null,"unknown_creative_ticket");
        var out=envelope(session);out.addProperty("source","explicit_client_known_watch_v1");out.addProperty("ticket",ticket);
        out.addProperty("placed_by_this_controller",watched.placed);out.addProperty("visual_observation",false);
        var rows=new JsonArray();
        for(BlockPos p:watched.positions){
            loaded(p);need(actor.position().distanceToSqr(Vec3.atCenterOf(p))<=64*64,"creative_watch_out_of_range");
            var row=state(world.getBlockState(p));row.add("position",vector(p));rows.add(row);
        }
        out.add("states",rows);return out;
    }
    private JsonObject material(Minecraft mc,Request r){
        ItemStack previous=actor.getInventory().getItem(r.slot);
        need(itemId(previous).equals(r.expectedItem) && previous.getCount()==r.expectedCount && previous.getComponentsPatch().isEmpty(),"creative_slot_changed");
        need(actor.containerMenu==actor.inventoryMenu && actor.containerMenu.getCarried().isEmpty(),"clean_inventory_required");
        for(int i=1;i<=4;i++)need(actor.inventoryMenu.getSlot(i).getItem().isEmpty(),"clean_crafting_grid_required");
        var screen=new CreativeModeInventoryScreen(actor,world.enabledFeatures(),false);
        mc.gui.setScreen(screen);
        var access=(CreativeInventoryAccess)(Object)screen;
        access.blockwire$selectTab(CreativeModeTabs.searchTab());
        // Native text input and native Creative SWAP, not setItem/setCount, custom
        // packets, /give, or direct stack injection into the player inventory.
        for(int c:r.item.codePoints().toArray())screen.charTyped(new CharacterEvent(c));
        var menu=screen.getMenu();
        var source=menu.slots.stream().limit(45).filter(s->s.isActive() && itemId(s.getItem()).equals(r.item)
            && s.getItem().getComponentsPatch().isEmpty()).findFirst();
        need(source.isPresent(),"creative_catalog_item_not_visible");
        need(mc.player==actor && mc.level==world && mc.gui.screen()==screen,"creative_screen_changed");
        grounded(mc);
        access.blockwire$slotClicked(source.get(),source.get().index,r.slot,ContainerInput.SWAP);
        need(menu.getCarried().isEmpty() && actor.inventoryMenu.getCarried().isEmpty(),"creative_cursor_requires_recovery");
        screen.onClose();
        var out=envelope(r.actor);out.addProperty("submitted",true);out.addProperty("text","Native Creative catalog selection submitted; inventory readback required.");return out;
    }
    public JsonObject dispatch(Minecraft mc,Request r){
        bind(mc);grounded(mc);
        if(r.action.equals("material"))return material(mc,r);
        if(r.action.equals("check"))return check(r.actor,r.ticket);
        Probe p=probe(mc,r.actor);
        if(r.action.equals("probe"))return p.value;
        need(p.hit!=null,"creative_target_not_seen");
        if(r.action.equals("place")){
            need(p.candidate!=null && p.context.getClickedPos().equals(r.position) &&
                p.value.get("placement_token").getAsString().equals(r.token),"creative_placement_changed");
            need(watches.size()<MAX_WATCHES,"creative_watch_budget");
            String item=itemId(actor.getMainHandItem());
            List<BlockPos> cells=item.equals("minecraft:spruce_door")?List.of(r.position,r.position.above()):List.of(r.position);
            String ticket=watch(cells,true,item);
            var result=mc.gameMode.useItemOn(actor,InteractionHand.MAIN_HAND,p.hit);
            if(!result.consumesAction()){watches.remove(ticket);throw new IllegalStateException("native_placement_not_accepted");}
            var out=envelope(r.actor);out.addProperty("submitted",true);out.addProperty("ticket",ticket);out.addProperty("destination_was_air",true);return out;
        }
        need(p.hit.getBlockPos().equals(r.position) && p.value.get("hit_token").getAsString().equals(r.token),"creative_target_changed");
        if(r.action.equals("remember")){
            var out=envelope(r.actor);out.addProperty("ticket",watch(List.of(r.position),false,p.value.getAsJsonObject("state").get("id").getAsString()));return out;
        }
        if(r.action.equals("toggle")){
            need(id(world.getBlockState(r.position)).equals("minecraft:spruce_door") && !actor.isShiftKeyDown(),"door_target_required");
            String value=p.value.getAsJsonObject("state").getAsJsonObject("properties").get("open").getAsString();
            boolean changed=!value.equals(r.open.toString());
            if(changed)mc.gameMode.useItemOn(actor,InteractionHand.MAIN_HAND,p.hit);
            var out=envelope(r.actor);out.addProperty("submitted",changed);return out;
        }
        Watch owner=watches.get(r.ticket);
        need(owner!=null && owner.placed && owner.block.equals("minecraft:cobblestone") && owner.positions.equals(List.of(r.position)),"owned_scaffold_required");
        need(id(world.getBlockState(r.position)).equals("minecraft:cobblestone") && itemId(actor.getMainHandItem()).equals("minecraft:cobblestone"),"scaffold_changed");
        need(!actor.getBoundingBox().move(0,-.1,0).intersects(new AABB(r.position)),"cannot_remove_own_support");
        need(mc.gameMode.startDestroyBlock(r.position,p.hit.getDirection()),"native_scaffold_break_not_accepted");
        var out=envelope(r.actor);out.addProperty("submitted",true);out.addProperty("ticket",r.ticket);return out;
    }
}
