package dev.blockwire;

import com.google.gson.*;
import net.minecraft.client.*;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.*;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.item.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.*;
import java.io.IOException;
import java.nio.file.Path;
import java.util.*;
import java.util.function.Consumer;

/** Passive local-human recorder. It observes native actions/outcomes and never writes a control. */
final class Play2CodeRecorder {
    static final int CONFIRM_TICKS=3;
    static final int PENDING_TICKS=80;
    static final int STOP_DRAIN_TICKS=20;
    static final long MAX_TICKS=216_000;
    private enum State {IDLE,RECORDING,DRAINING}
    private static final Set<String> AIR=Set.of("minecraft:air","minecraft:cave_air","minecraft:void_air");
    private static final class Pending {
        final long intentSequence;
        final String kind,hand,before,expected,heldItem;
        final BlockPos position;
        final int heldCount;
        final long expiresAt;
        String stableState;
        int stableTicks;
        Pending(long intentSequence,String kind,String hand,BlockPos position,String before,String expected,
                String heldItem,int heldCount,long expiresAt) {
            this.intentSequence=intentSequence;this.kind=kind;this.hand=hand;this.position=position.immutable();
            this.before=before;this.expected=expected;this.heldItem=heldItem;this.heldCount=heldCount;this.expiresAt=expiresAt;
        }
    }

    private final Path root;
    private final Consumer<String> notify;
    private Play2CodeCapture capture;
    private State state=State.IDLE;
    private LocalPlayer actor;
    private ClientLevel level;
    private String actorSession;
    private Vec3 origin;
    private BlockPos blockOrigin;
    private long clientTick,drainUntil;
    private int lastHotbar=-1;
    private final ArrayList<Pending> pending=new ArrayList<>();
    private boolean endpointEnabled,remoteOwned;
    private long ticks,useIntents,breakIntents,placements,breaks,changed,unconfirmed;

    Play2CodeRecorder(Path root,Consumer<String> notify){this.root=root;this.notify=notify;}
    boolean active(){return state!=State.IDLE;}
    Path lastDirectory(){return capture==null?null:capture.directory();}

    void start(Minecraft mc,String session,boolean endpointRunning) {
        if(active()){notify.accept("Play2Code is already recording.");return;}
        if(endpointRunning){notify.accept("Play2Code requires the Blockwire control endpoint to be disabled first (F8).");return;}
        if(mc.player==null || mc.level==null || mc.gameMode==null || !mc.player.isAlive() || mc.gameMode.isSpectator() ||
           mc.gui.screen()!=null || mc.gui.overlay()!=null || mc.isPaused()) {
            notify.accept("Play2Code requires live, unpaused, non-spectator gameplay with no screen open.");return;
        }
        reset();actor=mc.player;level=mc.level;actorSession=session;origin=actor.position();blockOrigin=actor.blockPosition().immutable();
        var start=new JsonObject();start.addProperty("profile","native_local_human_timeline_v1");
        start.addProperty("source","local_human_input");start.addProperty("control_endpoint_running",false);
        start.addProperty("actor_session",actorSession);start.addProperty("player_uuid",actor.getUUID().toString());
        start.addProperty("dimension",level.dimension().identifier().toString());
        start.addProperty("game_mode",mc.gameMode.getPlayerMode().getName());
        start.add("origin_position_absolute",vector(origin.x,origin.y,origin.z));start.add("origin_block_absolute",position(blockOrigin));
        start.add("position_absolute",vector(actor.getX(),actor.getY(),actor.getZ()));
        start.add("position_relative",vector(0,0,0));start.addProperty("yaw",actor.getYRot());start.addProperty("pitch",actor.getXRot());
        start.addProperty("selected_hotbar",actor.getInventory().getSelectedSlot());start.add("main_hand",Observations.item(actor.getMainHandItem()));
        start.addProperty("coordinate_contract","Player positions are absolute feet coordinates; block positions are integer voxels. Relative player coordinates use the exact start position; relative block coordinates use its floored block position.");
        try {
            capture=Play2CodeCapture.start(root,start);state=State.RECORDING;lastHotbar=actor.getInventory().getSelectedSlot();
            notify.accept("Play2Code recording started: "+capture.id()+". F10 stops after a bounded confirmation window.");
        } catch(IOException error) {reset();notify.accept("Play2Code could not create a private recording ("+error.getMessage()+").");}
    }
    void requestStop() {
        if(state==State.IDLE){notify.accept("Play2Code is not recording.");return;}
        if(state==State.DRAINING){notify.accept("Play2Code is already stopping.");return;}
        state=State.DRAINING;drainUntil=clientTick+STOP_DRAIN_TICKS;
        var event=new JsonObject();event.addProperty("client_tick",clientTick);event.addProperty("pending_mutations",pending.size());
        if(append("recording_stop_requested",event)<0)return;
        notify.accept("Play2Code stop requested; waiting briefly for observed block confirmations.");
    }
    void abort(String reason) {
        if(!active())return;
        if(reason.equals("control_endpoint_enabled"))endpointEnabled=true;
        finish("invalid",reason,false);
    }
    void sample(Minecraft mc,String session,Set<String> remotelyOwned,Map<String,KeyMapping> keys,boolean endpointRunning) {
        if(!active())return;
        if(endpointRunning){endpointEnabled=true;abort("control_endpoint_enabled");return;}
        if(!remotelyOwned.isEmpty()){remoteOwned=true;abort("remote_owned_input_observed");return;}
        if(mc.player!=actor || mc.level!=level || !Objects.equals(actorSession,session)){abort("actor_or_world_replaced");return;}
        if(actor==null || !actor.isAlive()){abort("player_not_alive");return;}
        if(ticks>=MAX_TICKS){abort("recording_tick_limit");return;}
        var event=new JsonObject();event.addProperty("client_tick",clientTick);event.addProperty("actor_tick",actor.tickCount);
        event.addProperty("game_time",level.getGameTime());event.addProperty("actor_session",actorSession);
        event.add("position_absolute",vector(actor.getX(),actor.getY(),actor.getZ()));
        event.add("position_relative",vector(actor.getX()-origin.x,actor.getY()-origin.y,actor.getZ()-origin.z));
        var block=actor.blockPosition();event.add("block_position_absolute",position(block));event.add("block_position_relative",relative(block));
        Vec3 velocity=actor.getDeltaMovement();event.add("velocity",vector(velocity.x,velocity.y,velocity.z));
        event.addProperty("yaw",actor.getYRot());event.addProperty("pitch",actor.getXRot());event.addProperty("on_ground",actor.onGround());
        event.addProperty("sprinting",actor.isSprinting());event.addProperty("sneaking",actor.isShiftKeyDown());
        event.addProperty("health",actor.getHealth());event.addProperty("selected_hotbar",actor.getInventory().getSelectedSlot());
        event.add("main_hand",Observations.item(actor.getMainHandItem()));event.add("off_hand",Observations.item(actor.getOffhandItem()));
        var inputs=new JsonObject();keys.forEach((name,key)->inputs.addProperty(name,key.isDown()));event.add("inputs",inputs);
        event.add("remote_owned_inputs",new JsonArray());event.addProperty("screen_open",mc.gui.screen()!=null);
        if(append("tick",event)<0)return;ticks++;
        int selected=actor.getInventory().getSelectedSlot();
        if(selected!=lastHotbar) {
            var hotbar=new JsonObject();hotbar.addProperty("client_tick",clientTick);hotbar.addProperty("from",lastHotbar);hotbar.addProperty("to",selected);
            hotbar.add("held",Observations.item(actor.getMainHandItem()));
            if(append("hotbar_selected",hotbar)<0)return;lastHotbar=selected;
        }
        pollPending();if(!active())return;clientTick++;
        if(state==State.DRAINING && clientTick>=drainUntil) {
            expireAll("stop_confirmation_window_elapsed");finish("completed","user_requested",true);
        } else if(state==State.DRAINING && pending.isEmpty() && clientTick+CONFIRM_TICKS>=drainUntil) {
            finish("completed","user_requested",true);
        }
    }
    void breakIntent(BlockPos supplied,Direction face) {
        if(!active() || actor==null || level==null)return;
        if(state==State.DRAINING){unsupportedAfterStop("attack",supplied);return;}
        BlockPos pos=supplied.immutable();String before=blockId(level.getBlockState(pos));
        var event=interaction("break",pos,face,InteractionHand.MAIN_HAND,actor.getMainHandItem());event.addProperty("before_block",before);
        long intent=append("break_intent",event);if(intent<0)return;breakIntents++;
        if(!AIR.contains(before))pending.add(new Pending(intent,"break","main_hand",pos,before,null,
            itemId(actor.getMainHandItem()),actor.getMainHandItem().getCount(),clientTick+PENDING_TICKS));
    }
    void useIntent(LocalPlayer supplied,InteractionHand hand,BlockHitResult hit) {
        if(!active() || supplied!=actor || level==null)return;
        if(state==State.DRAINING){unsupportedAfterStop("use",hit.getBlockPos());return;}
        ItemStack stack=actor.getItemInHand(hand);BlockPos target=hit.getBlockPos().immutable();BlockState targetState=level.getBlockState(target);
        String expected=stack.getItem() instanceof BlockItem item?BuiltInRegistries.BLOCK.getKey(item.getBlock()).toString():null;
        var event=interaction("use",target,hit.getDirection(),hand,stack);event.addProperty("target_block",blockId(targetState));
        if(expected!=null)event.addProperty("expected_placed_block",expected);
        var candidates=new JsonArray();var positions=new LinkedHashSet<BlockPos>();
        if(targetState.canBeReplaced())positions.add(target);positions.add(target.relative(hit.getDirection()));
        for(BlockPos pos:positions) {
            var candidate=new JsonObject();candidate.add("position_absolute",position(pos));candidate.add("position_relative",relative(pos));
            candidate.addProperty("before_block",level.isLoaded(pos)?blockId(level.getBlockState(pos)):"UNKNOWN");candidates.add(candidate);
        }
        event.add("candidates",candidates);long intent=append("use_on_block",event);if(intent<0)return;useIntents++;
        if(expected==null) {
            var unsupported=new JsonObject();unsupported.addProperty("intent_sequence",intent);unsupported.addProperty("reason","held_item_is_not_a_block");
            append("interaction_unsupported",unsupported);return;
        }
        String handName=hand==InteractionHand.MAIN_HAND?"main_hand":"off_hand";
        for(BlockPos pos:positions)if(level.isLoaded(pos)) {
            String before=blockId(level.getBlockState(pos));
            pending.add(new Pending(intent,"placement",handName,pos,before,expected,itemId(stack),stack.getCount(),clientTick+PENDING_TICKS));
        }
    }
    private JsonObject interaction(String action,BlockPos pos,Direction face,InteractionHand hand,ItemStack stack) {
        var event=new JsonObject();event.addProperty("client_tick",clientTick);event.addProperty("action",action);
        event.addProperty("source","local_human_input");event.addProperty("hand",hand==InteractionHand.MAIN_HAND?"main_hand":"off_hand");
        event.add("target_position_absolute",position(pos));event.add("target_position_relative",relative(pos));event.addProperty("face",face.getName());
        event.add("held",Observations.item(stack));event.addProperty("selected_hotbar",actor.getInventory().getSelectedSlot());
        event.add("player_position_absolute",vector(actor.getX(),actor.getY(),actor.getZ()));
        event.add("player_position_relative",vector(actor.getX()-origin.x,actor.getY()-origin.y,actor.getZ()-origin.z));
        event.addProperty("yaw",actor.getYRot());event.addProperty("pitch",actor.getXRot());return event;
    }
    private void pollPending() {
        var resolved=new HashSet<Long>();var expired=new ArrayList<Pending>();
        for(Pending p:pending) {
            if(resolved.contains(p.intentSequence))continue;
            if(clientTick>=p.expiresAt){expired.add(p);continue;}
            if(!level.isLoaded(p.position))continue;
            String current=blockId(level.getBlockState(p.position));
            if(current.equals(p.before)){p.stableState=null;p.stableTicks=0;continue;}
            if(current.equals(p.stableState))p.stableTicks++;else {p.stableState=current;p.stableTicks=1;}
            if(p.stableTicks<CONFIRM_TICKS)continue;
            String type;
            if(p.kind.equals("placement") && current.equals(p.expected))type="block_placed";
            else if(p.kind.equals("break") && AIR.contains(current))type="block_broken";
            else type="block_changed";
            var event=new JsonObject();event.addProperty("client_tick",clientTick);event.addProperty("intent_sequence",p.intentSequence);
            event.addProperty("source","local_human_input");event.addProperty("hand",p.hand);
            event.add("position_absolute",position(p.position));event.add("position_relative",relative(p.position));
            event.addProperty("before_block",p.before);event.addProperty("after_block",current);
            if(p.expected!=null)event.addProperty("expected_block",p.expected);
            event.addProperty("held_item",p.heldItem);event.addProperty("held_count_before",p.heldCount);
            ItemStack after=p.hand.equals("off_hand")?actor.getOffhandItem():actor.getMainHandItem();
            event.addProperty("held_count_after",itemId(after).equals(p.heldItem)?after.getCount():0);
            event.addProperty("inventory_consumption_observed",itemId(after).equals(p.heldItem) && after.getCount()<p.heldCount);
            event.addProperty("confirmation","client_world_state_stable_"+CONFIRM_TICKS+"_end_ticks");
            event.addProperty("confirmed_stable_ticks",p.stableTicks);if(append(type,event)<0)return;
            if(type.equals("block_placed"))placements++;else if(type.equals("block_broken"))breaks++;else changed++;
            resolved.add(p.intentSequence);
        }
        for(Pending p:expired)if(!resolved.contains(p.intentSequence))unconfirmed(p,"confirmation_timeout");
        if(!resolved.isEmpty())pending.removeIf(p->resolved.contains(p.intentSequence));
        if(!expired.isEmpty())pending.removeAll(expired);
    }
    private void expireAll(String reason) {
        var seen=new HashSet<Long>();for(Pending p:new ArrayList<>(pending))if(seen.add(p.intentSequence))unconfirmed(p,reason);pending.clear();
    }
    private void unconfirmed(Pending p,String reason) {
        var event=new JsonObject();event.addProperty("intent_sequence",p.intentSequence);event.addProperty("kind",p.kind);
        event.add("position_absolute",position(p.position));event.add("position_relative",relative(p.position));event.addProperty("reason",reason);
        append("interaction_unconfirmed",event);unconfirmed++;
    }
    private void unsupportedAfterStop(String action,BlockPos pos) {
        var event=new JsonObject();event.addProperty("client_tick",clientTick);event.addProperty("action",action);
        event.add("position_absolute",position(pos));event.add("position_relative",relative(pos));event.addProperty("reason","stop_already_requested");
        append("interaction_unsupported",event);
    }
    private void finish(String status,String reason,boolean requested) {
        if(!active() || capture==null)return;
        if(!pending.isEmpty())expireAll(reason);
        if(!active() || capture==null)return;
        var stop=new JsonObject();stop.addProperty("client_tick",clientTick);stop.addProperty("actor_session",actorSession);
        stop.addProperty("requested",requested);stop.addProperty("status",status);stop.addProperty("reason",reason);
        if(actor!=null) {
            stop.add("position_absolute",vector(actor.getX(),actor.getY(),actor.getZ()));
            stop.add("position_relative",vector(actor.getX()-origin.x,actor.getY()-origin.y,actor.getZ()-origin.z));
            stop.addProperty("health",actor.getHealth());stop.addProperty("alive",actor.isAlive());
        }
        var metadata=new JsonObject();metadata.addProperty("profile","native_local_human_timeline_v1");
        metadata.addProperty("player_uuid",actor==null?"":actor.getUUID().toString());metadata.addProperty("dimension",level==null?"":level.dimension().identifier().toString());
        metadata.addProperty("actor_session",actorSession);metadata.add("origin_position_absolute",vector(origin.x,origin.y,origin.z));
        metadata.add("origin_block_absolute",position(blockOrigin));metadata.addProperty("export_required",true);
        metadata.addProperty("no_remote_controller_interference",status.equals("completed") && !endpointEnabled && !remoteOwned);
        var remote=new JsonObject();remote.addProperty("endpoint_disabled_at_start",true);remote.addProperty("endpoint_enabled_during_recording",endpointEnabled);
        remote.addProperty("remote_owned_input_observed",remoteOwned);metadata.add("remote_control",remote);
        var summary=new JsonObject();summary.addProperty("ticks",ticks);summary.addProperty("use_intents",useIntents);
        summary.addProperty("break_intents",breakIntents);summary.addProperty("confirmed_placements",placements);
        summary.addProperty("confirmed_breaks",breaks);summary.addProperty("other_confirmed_changes",changed);
        summary.addProperty("unconfirmed_interactions",unconfirmed);metadata.add("summary",summary);
        metadata.addProperty("privacy","Contains player UUID, positions and gameplay timeline. Keep private; never bundle automatically.");
        Path directory=capture.directory();
        try {capture.finish(status,reason,stop,metadata);notify.accept("Play2Code recording "+status+": "+directory+". Export with blockwire-play2code.");}
        catch(IOException error){notify.accept("Play2Code recording could not be sealed ("+error.getMessage()+"): "+directory);}
        finally {reset();}
    }
    private long append(String type,JsonObject event) {
        if(capture==null)return -1;
        try{return capture.append(type,event);}
        catch(IOException error){
            Path path=capture.directory();try{capture.close();}catch(IOException ignored){}
            capture=null;state=State.IDLE;pending.clear();
            notify.accept("Play2Code stopped after a write failure ("+error.getMessage()+"): "+path);return -1;
        }
    }
    private void reset() {
        capture=null;state=State.IDLE;actor=null;level=null;actorSession=null;origin=null;blockOrigin=null;
        clientTick=drainUntil=ticks=useIntents=breakIntents=placements=breaks=changed=unconfirmed=0;
        lastHotbar=-1;pending.clear();endpointEnabled=false;remoteOwned=false;
    }
    private JsonArray relative(BlockPos pos) {
        return position(new BlockPos(pos.getX()-blockOrigin.getX(),pos.getY()-blockOrigin.getY(),pos.getZ()-blockOrigin.getZ()));
    }
    private static String blockId(BlockState state){return BuiltInRegistries.BLOCK.getKey(state.getBlock()).toString();}
    private static String itemId(ItemStack stack){return stack.isEmpty()?"minecraft:air":BuiltInRegistries.ITEM.getKey(stack.getItem()).toString();}
    private static JsonArray position(BlockPos pos){var out=new JsonArray();out.add(pos.getX());out.add(pos.getY());out.add(pos.getZ());return out;}
    private static JsonArray vector(double x,double y,double z){var out=new JsonArray();out.add(x);out.add(y);out.add(z);return out;}
}
