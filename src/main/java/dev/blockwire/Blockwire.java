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
    private KeyMapping toggle;
    private int ticksLeft;
    private BridgeConfig config;
    private TlsIdentity tls;
    private final MenuBridge menus=new MenuBridge();
    private final NavigationView navigation=new NavigationView();
    private long deadline, generation;
    private net.minecraft.client.player.LocalPlayer actor;
    private net.minecraft.client.multiplayer.ClientLevel world;
    private Set<String> held=Set.of();
    private final Minecraft mc=Minecraft.getInstance();

    public void onInitializeClient() {
        instance=this;
        try {
            var directory=BridgeConfig.directory(FabricLoader.getInstance().getConfigDir());
            config=BridgeConfig.load(directory);
            tls=TlsIdentity.load(directory); // Generate once, even while remote control is disabled.
        } catch(Exception e) {LOG.error("Blockwire disabled: could not initialize private configuration ({})",e.getClass().getSimpleName());return;}
        toggle=KeyMappingHelper.registerKeyMapping(new KeyMapping("key.block_bridge.toggle",InputConstants.Type.KEYBOARD,
            InputConstants.KEY_F8,KeyMapping.Category.register(Identifier.parse("blockwire:controls"))));
        ClientTickEvents.START_CLIENT_TICK.register(client->tick());
        ClientLifecycleEvents.CLIENT_STOPPING.register(client->stop());
        ClientLifecycleEvents.CLIENT_STARTED.register(client->{if(config.enabled())startServer();});
        LOG.info("Blockwire configured; auto-start {}. F8 toggles local control.",config.enabled());
    }
    private void message(String text) {
        LOG.info("{}",text);
        if(mc.player!=null)mc.player.sendSystemMessage(Component.literal("[Blockwire] "+text));
    }
    public static boolean toggleKey(InputConstants.Key key) {
        if(instance==null || instance.toggle==null || !instance.toggle.matches(key))return false;
        instance.toggleServer();return true;
    }
    private void toggleServer() {
        if(server!=null){stop();message("Disabled; inputs released.");}
        else startServer();
    }
    private void startServer() {
        if(server!=null)return;
        try {
            long epoch=++generation;
            server=new BridgeServer(config.serverIp(),config.port(),config.apiKey(),tls.context(),mc,this::dispatch,
                ()->{if(generation==epoch)release();});
            if(!java.net.InetAddress.getByName(config.serverIp()).isLoopbackAddress())
                LOG.warn("Blockwire is exposed beyond loopback. TLS is active; retain firewall and trusted-client restrictions.");
            message("Enabled TLS on "+config.serverIp()+":"+config.port()+" (F8 stops).");
        } catch(Exception e){message("Could not bind configured address; bridge remains disabled.");}
    }
    private void tick() {
        if(held.isEmpty())return;
        if(server==null || !server.connected() || mc.player==null || mc.player!=actor || mc.level!=world || !mc.player.isAlive() ||
            mc.gui.screen()!=null || mc.isPaused() || ticksLeft--<=0 || System.nanoTime()>=deadline) {release();return;}
        held.forEach(key->InputState.set(keys().get(key),true));
    }
    private Map<String,KeyMapping> keys() {
        var o=mc.options;
        return Map.of("forward",o.keyUp,"back",o.keyDown,"left",o.keyLeft,"right",o.keyRight,
            "jump",o.keyJump,"sneak",o.keyShift,"sprint",o.keySprint,"attack",o.keyAttack,"use",o.keyUse);
    }
    private void release() {
        held.forEach(key->InputState.set(keys().get(key),false));
        held=Set.of();ticksLeft=0;actor=null;world=null;
    }
    private void stop() {++generation;release();if(server!=null){server.close();server=null;}}
    public static boolean holdingAttack() {
        return instance!=null && instance.server!=null && instance.held.contains("attack") &&
            instance.server.connected() && instance.mc.gui.screen()==null && !instance.mc.isPaused() &&
            instance.mc.player==instance.actor && instance.mc.level==instance.world && instance.actor!=null && instance.actor.isAlive() &&
            System.nanoTime()<instance.deadline;
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
    private JsonObject dispatch(JsonObject q) {
        String op=Protocol.operation(q);
        switch(op) {
            case "observe" -> {Protocol.fields(q);return Observations.scene(mc);}
            case "navigation" -> {Protocol.fields(q);return navigation.snapshot(mc);}
            case "inventory" -> {Protocol.fields(q);playerRequired();return Observations.inventory(mc);}
            case "menu" -> {Protocol.fields(q);return menus.snapshot(mc);}
            case "menu_click", "menu_key", "menu_text", "menu_scroll" -> {return menus.act(mc,q);}
            case "open_pause" -> {
                Protocol.fields(q);playing();release();mc.pauseGame(false);return menus.snapshot(mc);
            }
            case "stop" -> {Protocol.fields(q);release();return Protocol.ok("Inputs released.");}
            case "look" -> {
                Protocol.fields(q,"yaw","pitch","actor_session");double yaw=Protocol.number(q,"yaw",-180,180),pitch=Protocol.number(q,"pitch",-90,90);
                guardedActor(q);playing();mc.player.setYRot((float)yaw);mc.player.setXRot((float)pitch);
                return Protocol.ok("Camera set. Target observation refreshes on the next rendered frame.");
            }
            case "drive" -> {
                Protocol.fields(q,"buttons","ticks","actor_session");int ticks=Protocol.integer(q,"ticks",1,100);
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
                guardedActor(q);playing();boolean attack=buttons.contains("attack")&&!held.contains("attack"),use=buttons.contains("use")&&!held.contains("use");
                release();held=Set.copyOf(buttons);actor=mc.player;world=mc.level;ticksLeft=ticks;deadline=System.nanoTime()+ticks*50_000_000L;
                held.forEach(key->InputState.set(keys().get(key),true));
                if(attack)((MinecraftActions)(Object)mc).blockwire$attack();
                if(use)((MinecraftActions)(Object)mc).blockwire$use();
                return Protocol.ok("Native inputs scheduled for at most "+ticks+" ticks / "+(ticks*50)+" ms; not a completion receipt.");
            }
            case "action" -> {
                Protocol.fields(q,"name");String name=Protocol.string(q,"name");
                if(!Set.of("attack","use").contains(name))throw new IllegalArgumentException("unsupported_action");
                playing();
                if(name.equals("attack"))((MinecraftActions)(Object)mc).blockwire$attack();
                else ((MinecraftActions)(Object)mc).blockwire$use();
                return Protocol.ok("Native "+name+" requested; observe the resulting state.");
            }
            case "hotbar" -> {
                Protocol.fields(q,"slot");int slot=Protocol.integer(q,"slot",0,8);playing();
                mc.player.getInventory().setSelectedSlot(slot);return Protocol.ok("Selected hotbar slot "+slot+".");
            }
            case "open_inventory" -> {
                Protocol.fields(q);playing();release();mc.gui.setScreen(new InventoryScreen(mc.player));
                return Observations.inventory(mc);
            }
            case "close_screen" -> {
                Protocol.fields(q);playerRequired();
                if(!(mc.gui.screen() instanceof AbstractContainerScreen<?>))throw new IllegalStateException("no_container_screen");
                release();mc.player.closeContainer();return Protocol.ok("Native container close requested.");
            }
            case "click_slot" -> {
                Protocol.fields(q,"menu_id","state_id","slot","button","mode");
                int menuId=Protocol.integer(q,"menu_id",0,Integer.MAX_VALUE),stateId=Protocol.integer(q,"state_id",0,Integer.MAX_VALUE);
                int slot=Protocol.integer(q,"slot",0,4095),button=Protocol.integer(q,"button",0,1);
                String mode=Protocol.string(q,"mode");
                if(!Set.of("pickup","quick_move").contains(mode))throw new IllegalArgumentException("unsupported_click_mode");
                playerRequired();
                if(!(mc.gui.screen() instanceof AbstractContainerScreen<?> screen) ||
                    screen.getMenu()!=mc.player.containerMenu)throw new IllegalStateException("no_container_screen");
                var menu=mc.player.containerMenu;
                if(menuId!=menu.containerId || stateId!=menu.getStateId())throw new IllegalStateException("stale_menu");
                if(slot>=menu.slots.size() || !menu.getSlot(slot).isActive())throw new IllegalArgumentException("invalid_slot");
                mc.gameMode.handleContainerInput(menuId,slot,button,mode.equals("pickup")?ContainerInput.PICKUP:ContainerInput.QUICK_MOVE,mc.player);
                return Protocol.ok("Native slot click submitted; server acknowledgement may be pending. Refresh inventory.");
            }
            case "respawn" -> {
                Protocol.fields(q);playerRequired();
                if(mc.player.isAlive())throw new IllegalStateException("player_not_dead");
                release();mc.player.respawn();return Protocol.ok("Native respawn requested.");
            }
            default -> throw new IllegalArgumentException("unknown_operation");
        }
    }
}
