package dev.blockwire;

import com.google.gson.*;
import com.mojang.blaze3d.platform.InputConstants;
import dev.blockwire.mixin.MinecraftActions;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.*;
import net.fabricmc.fabric.api.client.keymapping.v1.KeyMappingHelper;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.client.*;
import net.minecraft.client.gui.screens.inventory.*;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.Identifier;
import net.minecraft.world.inventory.ContainerInput;
import org.slf4j.*;
import java.util.*;

public final class Blockwire implements ClientModInitializer {
    private static final Logger LOG=LoggerFactory.getLogger("blockwire");
    private static Blockwire instance;
    private BridgeServer server;
    private KeyMapping toggle,play2CodeStart,play2CodeStop;
    private Play2CodeRecorder play2Code;
    private int ticksLeft;
    private BridgeConfig config;
    private java.nio.file.Path configDirectory;
    private TlsIdentity tls;
    private final MenuBridge menus=new MenuBridge();
    private final NavigationView navigation=new NavigationView();
    private final MotionTrace motionTrace=new MotionTrace();
    private final AutoEvents autoEvents=new AutoEvents();
    private final CreativeBuild creativeBuild=new CreativeBuild();
    private boolean groundedCreativeLease;
    private long lastChatSend;
    private final RotationController rotation=new RotationController();
    private final InputLeases inputLeases=new InputLeases();
    private long deadline, generation;
    private net.minecraft.client.player.LocalPlayer actor;
    private net.minecraft.client.multiplayer.ClientLevel world;
    private Set<String> held=Set.of();
    private final Minecraft mc=Minecraft.getInstance();

    public void onInitializeClient() {
        instance=this;
        try {
            configDirectory=BridgeConfig.directory(FabricLoader.getInstance().getConfigDir());
            config=BridgeConfig.load(configDirectory);
            tls=TlsIdentity.load(configDirectory); // Generate once, even while remote control is disabled.
        } catch(Exception e) {LOG.error("Blockwire disabled: could not initialize private configuration ({})",e.getClass().getSimpleName());return;}
        var category=KeyMapping.Category.register(Identifier.parse("blockwire:controls"));
        toggle=KeyMappingHelper.registerKeyMapping(new KeyMapping("key.block_bridge.toggle",InputConstants.Type.KEYBOARD,InputConstants.KEY_F8,category));
        play2CodeStart=KeyMappingHelper.registerKeyMapping(new KeyMapping("key.blockwire.play2code.start",InputConstants.Type.KEYBOARD,InputConstants.KEY_F9,category));
        play2CodeStop=KeyMappingHelper.registerKeyMapping(new KeyMapping("key.blockwire.play2code.stop",InputConstants.Type.KEYBOARD,InputConstants.KEY_F10,category));
        play2Code=new Play2CodeRecorder(FabricLoader.getInstance().getGameDir().resolve("recordings"),this::message);
        net.fabricmc.fabric.api.client.message.v1.ClientReceiveMessageEvents.CHAT.register(
            (text,message,sender,parameters,received)->autoEvents.chat(mc,text,message,sender));
        ClientTickEvents.START_CLIENT_TICK.register(client->tick());
        ClientTickEvents.END_CLIENT_TICK.register(client->{
            String session=navigation.actorSession(client);var currentKeys=keys();
            motionTrace.sample(client,session,held,currentKeys,rotation);
            autoEvents.tick(client);
            play2Code.sample(client,session,held,currentKeys,server!=null);
        });
        ClientLifecycleEvents.CLIENT_STOPPING.register(client->{play2Code.abort("client_stopping");stop();});
        ClientLifecycleEvents.CLIENT_STARTED.register(client->{if(config.enabled())startServer();});
        LOG.info("Blockwire configured; auto-start {}. F8 toggles local control; F9/F10 start/stop passive Play2Code recording.",config.enabled());
    }
    /** No Mod Menu types or secrets cross this boundary; all mutations use the existing client-thread paths. */
    public static LocalSettingsModel.Backend localSettings() {
        return new LocalSettingsModel.Backend() {
            public LocalSettingsModel.Status status() {
                var current=instance;
                boolean ready=current!=null && current.config!=null && current.tls!=null;
                if(!ready)return new LocalSettingsModel.Status(false,false,false,false,"",0);
                return new LocalSettingsModel.Status(true,current.server!=null,
                    current.server!=null && current.server.connected(),current.config.enabled(),current.config.serverIp(),current.config.port());
            }
            public void toggleRuntime() {if(status().available())instance.toggleServer();}
            public boolean saveStartup(boolean enabled) {
                if(!status().available())return false;
                try {
                    instance.config=BridgeConfig.saveStartup(instance.configDirectory,instance.config,enabled);
                    return true;
                } catch(Exception error) {
                    LOG.warn("Could not save Blockwire startup preference ({}); private configuration retained.",error.getClass().getSimpleName());
                    return false;
                }
            }
        };
    }
    private void message(String text) {
        LOG.info("{}",text);
        if(mc.player!=null)mc.player.sendSystemMessage(Component.literal("[Blockwire] "+text));
    }
    public static boolean toggleKey(InputConstants.Key key) {
        if(instance==null || instance.toggle==null || !instance.toggle.matches(key))return false;
        instance.toggleServer();return true;
    }
    public static boolean play2CodeKey(InputConstants.Key key) {
        if(instance==null || instance.play2Code==null)return false;
        if(instance.play2CodeStart!=null && instance.play2CodeStart.matches(key)) {
            instance.startPlay2Code();return true;
        }
        if(instance.play2CodeStop!=null && instance.play2CodeStop.matches(key)) {
            instance.play2Code.requestStop();return true;
        }
        return false;
    }
    public static void recordBreakIntent(net.minecraft.core.BlockPos position,net.minecraft.core.Direction face) {
        if(instance!=null && instance.play2Code!=null)instance.play2Code.breakIntent(position,face);
    }
    public static void recordUseIntent(net.minecraft.client.player.LocalPlayer player,net.minecraft.world.InteractionHand hand,
                                       net.minecraft.world.phys.BlockHitResult hit) {
        if(instance!=null && instance.play2Code!=null)instance.play2Code.useIntent(player,hand,hit);
    }
    private void startPlay2Code() {
        if(mc.player==null || mc.level==null){message("Play2Code requires a loaded world.");return;}
        play2Code.start(mc,navigation.actorSession(mc),server!=null);
    }
    private void toggleServer() {
        if(server!=null){stop();message("Disabled; inputs released.");}
        else {play2Code.abort("control_endpoint_enabled");startServer();}
    }
    private void startServer() {
        if(server!=null)return;
        try {
            long epoch=++generation;
            server=new BridgeServer(config.serverIp(),config.port(),config.apiKey(),tls.context(),mc,this::dispatch,
                ()->{if(generation==epoch){autoEvents.disable();creativeBuild.clear();release();}});
            if(!java.net.InetAddress.getByName(config.serverIp()).isLoopbackAddress())
                LOG.warn("Blockwire is exposed beyond loopback. TLS is active; retain firewall and trusted-client restrictions.");
            message("Enabled TLS on "+config.serverIp()+":"+config.port()+" (F8 stops).");
        } catch(Exception e){message("Could not bind configured address; bridge remains disabled.");}
    }
    private void tick() {
        rotation.tick(mc,server!=null && server.connected());
        if(held.isEmpty())return;
        if(server==null || !server.connected() || mc.player==null || mc.player!=actor || mc.level!=world || !mc.player.isAlive() ||
            mc.gui.screen()!=null || mc.isPaused()) {release();return;}
        if(groundedCreativeLease && (mc.gameMode==null || mc.gameMode.getPlayerMode()!=net.minecraft.world.level.GameType.CREATIVE ||
            mc.player.getAbilities().flying || mc.player.isFallFlying() || mc.player.isPassenger())) {release();return;}
        long now=System.nanoTime();
        if(ticksLeft--<=0 || now>=deadline){releaseInputs();return;}
        var expired=inputLeases.expire(now);
        expired.forEach(key->InputState.set(keys().get(key),false));
        if(!expired.isEmpty()) {
            var remaining=new HashSet<>(held);remaining.removeAll(expired);held=Set.copyOf(remaining);
            if(held.isEmpty()){releaseInputs();return;}
        }
        held.forEach(key->InputState.set(keys().get(key),true));
    }
    private Map<String,KeyMapping> keys() {
        var o=mc.options;
        return Map.of("forward",o.keyUp,"back",o.keyDown,"left",o.keyLeft,"right",o.keyRight,
            "jump",o.keyJump,"sneak",o.keyShift,"sprint",o.keySprint,"attack",o.keyAttack,"use",o.keyUse);
    }
    private void releaseInputs() {
        held.forEach(key->InputState.set(keys().get(key),false));
        held=Set.of();inputLeases.clear();ticksLeft=0;actor=null;world=null;groundedCreativeLease=false;
    }
    private void release() {
        rotation.cancel(mc,"controls_released");releaseInputs();
    }
    private void stop() {++generation;autoEvents.disable();creativeBuild.clear();release();if(server!=null){server.close();server=null;}}
    public static boolean holdingAttack() {
        return instance!=null && instance.server!=null && instance.held.contains("attack") &&
            instance.server.connected() && instance.mc.gui.screen()==null && !instance.mc.isPaused() &&
            instance.mc.player==instance.actor && instance.mc.level==instance.world && instance.actor!=null && instance.actor.isAlive() &&
            System.nanoTime()<instance.deadline && instance.inputLeases.active("attack",System.nanoTime());
    }
    private void playerRequired() {
        if(mc.player==null || mc.level==null || mc.gameMode==null)throw new IllegalStateException("not_in_world");
    }
    private void playing() {
        playerRequired();
        if(!mc.player.isAlive())throw new IllegalStateException("player_dead");
        if(mc.gui.screen()!=null || mc.isPaused())throw new IllegalStateException("close_screen_first");
        if(mc.gameMode.isSpectator())throw new IllegalStateException("spectator_control_not_supported");
    }
    private void guardedActor(JsonObject q) {
        if(q.has("actor_session") && !navigation.matches(mc,Protocol.string(q,"actor_session")))
            throw new IllegalStateException("actor_session_changed");
    }
    private JsonObject inventorySnapshot() {
        var out=Observations.inventory(mc);
        out.addProperty("actor_session",navigation.actorSession(mc));
        out.addProperty("guarded_inventory",true);return out;
    }
    private JsonObject dispatch(JsonObject q) {
        String op=Protocol.operation(q);
        switch(op) {
            case "observe" -> {
                Protocol.fields(q);var scene=Observations.scene(mc);String session=navigation.actorSession(mc);
                scene.addProperty("actor_session",session);scene.addProperty("auto_events_supported",true);scene.addProperty("search_supported",true);scene.add("rotation",rotation.snapshot(mc,session));return scene;
            }
            case "creative" -> {
                var request=CreativeBuild.request(q);guardedActor(q);playing();
                if(request.action().equals("material"))release();
                return creativeBuild.dispatch(mc,request);
            }
            case "search" -> {
                var request=SearchView.request(q);guardedActor(q);playerRequired();
                if(!mc.player.isAlive())throw new IllegalStateException("player_dead");
                return SearchView.snapshot(mc,navigation.actorSession(mc),request);
            }
            case "navigation" -> {Protocol.fields(q,"terrain");return navigation.snapshot(mc,Protocol.bool(q,"terrain",false));}
            case "motion_trace" -> {
                Protocol.fields(q,"limit","reset","actor_session");
                if(q.has("actor_session"))guardedActor(q);
                int limit=MotionTrace.requestLimit(q);boolean reset=Protocol.bool(q,"reset",false);
                if(reset)motionTrace.reset(mc);
                return motionTrace.snapshot(mc,navigation.actorSession(mc),limit);
            }
            case "events_configure" -> {
                Protocol.fields(q,"enabled","actor_session");Protocol.string(q,"actor_session");guardedActor(q);playerRequired();
                if(Protocol.bool(q,"enabled",false))autoEvents.enable(mc,navigation.actorSession(mc),event->server!=null && server.publish(event));
                else autoEvents.disable();
                return autoEvents.status();
            }
            case "chat" -> {
                String text=Protocol.chat(q);guardedActor(q);playing();
                long now=System.nanoTime();
                if(now-lastChatSend<1_000_000_000L)throw new IllegalStateException("chat_rate_limited");
                lastChatSend=now;mc.player.connection.sendChat(text);
                var receipt=Protocol.ok("Normal Minecraft chat submitted; delivery is NOT confirmed. Do not blindly retry.");
                receipt.addProperty("submitted",true);return receipt;
            }
            case "inventory" -> {Protocol.fields(q);playerRequired();return inventorySnapshot();}
            case "menu" -> {Protocol.fields(q);return menus.snapshot(mc);}
            case "menu_click", "menu_key", "menu_text", "menu_scroll" -> {return menus.act(mc,q);}
            case "open_pause" -> {
                Protocol.fields(q);playing();release();mc.pauseGame(false);return menus.snapshot(mc);
            }
            case "stop" -> {Protocol.fields(q);release();return Protocol.ok("Inputs and active camera rotation released.");}
            case "look" -> {
                Protocol.fields(q,"yaw","pitch","actor_session","duration_ms","rotation_profile","grounded_creative");
                double yaw=Protocol.number(q,"yaw",-180,180),pitch=Protocol.number(q,"pitch",-90,90);
                Integer duration=Protocol.rotationDuration(q);String profile=Protocol.rotationProfile(q);
                guardedActor(q);playing();
                CreativeBuild.guardedInput(mc,q,held,null);
                return duration==null?rotation.immediate(mc,yaw,pitch):rotation.schedule(mc,yaw,pitch,duration,profile);
            }
            case "drive" -> {
                Protocol.fields(q,"buttons","ticks","actor_session","button_ticks","grounded_creative");int ticks=Protocol.integer(q,"ticks",1,100);
                if(!q.has("buttons") || !q.get("buttons").isJsonArray() || q.getAsJsonArray("buttons").size()>9)
                    throw new IllegalArgumentException("expected_buttons_array_max_9");
                Set<String> buttons=new HashSet<>();
                for(JsonElement el:q.getAsJsonArray("buttons")) {
                    if(!el.isJsonPrimitive() || !el.getAsJsonPrimitive().isString() ||
                        !keys().containsKey(el.getAsString()) || !buttons.add(el.getAsString()))
                        throw new IllegalArgumentException("invalid_or_duplicate_button");
                }
                if((buttons.contains("forward")&&buttons.contains("back")) || (buttons.contains("left")&&buttons.contains("right")))
                    throw new IllegalArgumentException("opposed_buttons");
                var leases=Protocol.buttonTicks(q,buttons,ticks);
                guardedActor(q);playing();
                CreativeBuild.guardedInput(mc,q,actor==mc.player && world==mc.level?held:Set.of(),buttons);
                groundedCreativeLease=Protocol.bool(q,"grounded_creative",false);
                if(actor!=mc.player || world!=mc.level)inputLeases.clear();
                var next=inputLeases.replace(buttons,leases,System.nanoTime());
                inputLeases.cap(ticks,System.nanoTime());
                boolean attack=next.contains("attack")&&!held.contains("attack"),use=next.contains("use")&&!held.contains("use");
                held.stream().filter(key->!next.contains(key)).forEach(key->InputState.set(keys().get(key),false));
                held=next;actor=mc.player;world=mc.level;ticksLeft=ticks;deadline=System.nanoTime()+ticks*50_000_000L;
                held.forEach(key->InputState.set(keys().get(key),true));
                if(attack)((MinecraftActions)(Object)mc).blockwire$attack();
                if(use)((MinecraftActions)(Object)mc).blockwire$use();
                return Protocol.ok("Native inputs scheduled for at most "+ticks+" ticks / "+(ticks*50)+" ms; not a completion receipt.");
            }
            case "action" -> {
                Integer expected=Protocol.actionTarget(q);String name=Protocol.string(q,"name");
                guardedActor(q);playing();
                Integer actual=null;
                if(mc.hitResult instanceof net.minecraft.world.phys.EntityHitResult hit &&
                    hit.getEntity().isAlive() && mc.level.getEntity(hit.getEntity().getId())==hit.getEntity() &&
                    mc.player.distanceTo(hit.getEntity())<=3 && mc.player.hasLineOfSight(hit.getEntity()))actual=hit.getEntity().getId();
                Protocol.requireTarget(expected,actual);
                if(name.equals("attack"))((MinecraftActions)(Object)mc).blockwire$attack();
                else ((MinecraftActions)(Object)mc).blockwire$use();
                return Protocol.ok("Native "+name+" requested; observe the resulting state.");
            }
            case "hotbar" -> {
                int slot=Protocol.hotbarSlot(q);guardedActor(q);playing();
                mc.player.getInventory().setSelectedSlot(slot);return Protocol.ok("Selected hotbar slot "+slot+".");
            }
            case "open_inventory" -> {
                Protocol.inventoryFields(q);guardedActor(q);playing();release();mc.gui.setScreen(new InventoryScreen(mc.player));
                return inventorySnapshot();
            }
            case "close_screen" -> {
                Protocol.inventoryFields(q);guardedActor(q);playerRequired();
                if(!(mc.gui.screen() instanceof AbstractContainerScreen<?>))throw new IllegalStateException("no_container_screen");
                release();mc.player.closeContainer();return Protocol.ok("Native container close requested.");
            }
            case "click_slot" -> {
                Protocol.inventoryFields(q,"menu_id","state_id","slot","button","mode");
                int menuId=Protocol.integer(q,"menu_id",0,Integer.MAX_VALUE),stateId=Protocol.integer(q,"state_id",0,Integer.MAX_VALUE);
                int slot=Protocol.integer(q,"slot",0,4095),button=Protocol.integer(q,"button",0,1);
                String mode=Protocol.string(q,"mode");
                if(!Set.of("pickup","quick_move").contains(mode))throw new IllegalArgumentException("unsupported_click_mode");
                guardedActor(q);playerRequired();
                if(!(mc.gui.screen() instanceof AbstractContainerScreen<?> screen) ||
                    screen.getMenu()!=mc.player.containerMenu)throw new IllegalStateException("no_container_screen");
                var menu=mc.player.containerMenu;
                if(menuId!=menu.containerId || stateId!=menu.getStateId())throw new IllegalStateException("stale_menu");
                if(slot>=menu.slots.size() || !menu.getSlot(slot).isActive())throw new IllegalArgumentException("invalid_slot");
                mc.gameMode.handleContainerInput(menuId,slot,button,mode.equals("pickup")?ContainerInput.PICKUP:ContainerInput.QUICK_MOVE,mc.player);
                return Protocol.ok("Native slot click submitted; server acknowledgement may be pending. Refresh inventory.");
            }
            case "command" -> {
                String command=Protocol.command(q);guardedActor(q);playing();
                release();mc.player.connection.sendCommand(command);
                var receipt=Protocol.ok("Command submitted through Minecraft; server permissions apply. Outcome and output are not confirmed. Do not blindly retry.");
                receipt.addProperty("submitted",true);return receipt;
            }
            case "respawn" -> {
                Protocol.inventoryFields(q);guardedActor(q);playerRequired();
                if(mc.player.isAlive())throw new IllegalStateException("player_not_dead");
                release();mc.player.respawn();return Protocol.ok("Native respawn requested.");
            }
            default -> throw new IllegalArgumentException("unknown_operation");
        }
    }
}
