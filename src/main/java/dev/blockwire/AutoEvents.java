package dev.blockwire;

import com.google.gson.*;
import com.mojang.authlib.GameProfile;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.network.chat.PlayerChatMessage;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.player.Player;
import java.util.*;
import java.util.function.Predicate;

/** Opt-in client observation source. No world scans, controls, networking waits or planner. */
public final class AutoEvents {
    public static final int MAX_SCAN=256, MAX_ENTITIES=16, MAX_CHAT=2048;
    private LocalPlayer actor;
    private ClientLevel world;
    private String session;
    private Predicate<JsonObject> sink;
    private long sequence,dropped,chatWindow;
    private int ticks,chatCount;
    private final LinkedHashSet<Object> signatures=new LinkedHashSet<>();

    public void enable(Minecraft mc,String session,Predicate<JsonObject> sink) {
        disable();this.actor=mc.player;this.world=mc.level;this.session=session;this.sink=sink;
    }
    public void disable() {actor=null;world=null;session=null;sink=null;ticks=0;signatures.clear();}
    private boolean valid(Minecraft mc) {
        if(sink==null)return false;
        if(mc.player!=actor || mc.level!=world || actor==null || !actor.isAlive()) {disable();return false;}
        return true;
    }
    private void emit(String name,JsonObject data) {
        var frame=new JsonObject();frame.addProperty("type","native_event");frame.addProperty("name",name);
        frame.addProperty("actor_session",session);frame.addProperty("sequence",++sequence);
        frame.addProperty("dropped_total",dropped);frame.add("data",data);
        if(!sink.test(frame))dropped++;
    }
    public void chat(Minecraft mc,Component displayed,PlayerChatMessage message,GameProfile sender) {
        if(!valid(mc) || message==null || message.isSystem() || message.isFullyFiltered())return;
        // Use the actually delivered/displayed component, not hidden unfiltered signed content.
        String text=displayed.getString();
        if(text.length()>MAX_CHAT){dropped++;return;} // Never truncate into a different message.
        Object signature=message.signature();
        if(signature!=null && !signatures.add(signature))return;
        if(signatures.size()>64)signatures.remove(signatures.iterator().next());
        long now=System.currentTimeMillis();
        if(now-chatWindow>=1000){chatWindow=now;chatCount=0;}
        if(chatCount++>=10){dropped++;return;}
        var data=new JsonObject();data.addProperty("message",text);data.addProperty("channel","player_chat");
        data.addProperty("received_at_ms",now);data.addProperty("signed",message.hasSignature());
        if(sender!=null){data.addProperty("sender_uuid",sender.id().toString());data.addProperty("sender_name",sender.name());}
        // Public chat can arrive from afar. Only expose distance for an already observable player.
        var visible=world.getPlayerByUUID(message.sender());
        if(visible!=null && observable(actor,visible))data.addProperty("distance",actor.distanceTo(visible));
        emit("player.chat",data);
    }
    static boolean observable(LocalPlayer p,Entity e) {
        if(e==p || !e.isAlive() || e.isInvisibleTo(p) || p.distanceToSqr(e)>24*24)return false;
        var delta=e.getEyePosition().subtract(p.getEyePosition());
        return delta.lengthSqr()>0 && delta.normalize().dot(p.getViewVector(1))>.5 && p.hasLineOfSight(e);
    }
    public void tick(Minecraft mc) {
        if(!valid(mc) || ++ticks%5!=0)return;
        var rows=new JsonArray();int scanned=0;boolean truncated=false;
        for(Entity e:world.entitiesForRendering()) {
            if(++scanned>MAX_SCAN){truncated=true;break;}
            if(!(e instanceof Player) && !(e instanceof Monster))continue;
            if(!observable(actor,e))continue;
            if(rows.size()>=MAX_ENTITIES){truncated=true;break;}
            var row=new JsonObject();row.addProperty("entity_id",e.getId());row.addProperty("uuid",e.getUUID().toString());
            row.addProperty("category",e instanceof Player?"player":"hostile");
            row.addProperty("entity_type",BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString());
            if(e instanceof Player p)row.addProperty("player_name",p.getGameProfile().name());
            var pos=new JsonArray();pos.add(e.getX());pos.add(e.getY());pos.add(e.getZ());row.add("position",pos);
            row.addProperty("distance",actor.distanceTo(e));rows.add(row);
        }
        var data=new JsonObject();data.add("entities",rows);data.addProperty("truncated",truncated);
        data.addProperty("observed_at_ms",System.currentTimeMillis());data.addProperty("radius",24);
        emit("entities.snapshot",data);
    }
    public JsonObject status() {
        var out=Protocol.ok("Automatic native observations configured; no durable event replay.");
        out.addProperty("enabled",sink!=null);out.addProperty("sequence",sequence);out.addProperty("dropped_total",dropped);return out;
    }
}
