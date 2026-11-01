package dev.blockwire;

import com.google.gson.*;
import net.minecraft.client.Minecraft;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
import java.util.*;

/** Bounded read-only end-of-client-tick player telemetry; Minecraft remains the physics engine. */
public final class MotionTrace {
    public static final int CAPACITY=4096;
    private final ArrayDeque<JsonObject> samples=new ArrayDeque<>();
    private LocalPlayer actor;
    private ClientLevel level;
    private long sequence,dropped;

    private void bind(Minecraft mc) {
        if(mc.player!=actor || mc.level!=level) {
            actor=mc.player;level=mc.level;samples.clear();sequence=0;dropped=0;
        }
    }
    public void reset(Minecraft mc) {bind(mc);samples.clear();sequence=0;dropped=0;}
    public void sample(Minecraft mc,String actorSession,Set<String> remotelyOwned,Map<String,KeyMapping> keys,RotationController rotation) {
        bind(mc);if(actor==null || level==null)return;
        var out=new JsonObject();out.addProperty("client_tick",sequence++);
        out.addProperty("actor_tick",actor.tickCount);out.addProperty("game_time",level.getGameTime());
        out.addProperty("monotonic_ns",System.nanoTime());out.addProperty("actor_session",actorSession);
        out.add("position",vector(actor.getX(),actor.getY(),actor.getZ()));
        Vec3 velocity=actor.getDeltaMovement();out.add("velocity",vector(velocity.x,velocity.y,velocity.z));
        out.addProperty("horizontal_speed",Math.hypot(velocity.x,velocity.z));
        out.addProperty("yaw",actor.getYRot());out.addProperty("pitch",actor.getXRot());
        out.addProperty("on_ground",actor.onGround());out.addProperty("sprinting",actor.isSprinting());
        out.addProperty("sneaking",actor.isShiftKeyDown());out.addProperty("fall_distance",actor.fallDistance);
        out.addProperty("health",actor.getHealth());
        out.addProperty("horizontal_collision",actor.horizontalCollision);
        out.addProperty("minor_horizontal_collision",actor.minorHorizontalCollision);
        out.addProperty("vertical_collision",actor.verticalCollision);
        out.addProperty("vertical_collision_below",actor.verticalCollisionBelow);
        AABB box=actor.getBoundingBox();var bounds=new JsonArray();
        for(double value:new double[]{box.minX,box.minY,box.minZ,box.maxX,box.maxY,box.maxZ})bounds.add(value);
        out.add("bounding_box",bounds);
        var inputs=new JsonObject();keys.forEach((name,key)->inputs.addProperty(name,key.isDown()));out.add("inputs",inputs);
        var owned=new JsonArray();remotelyOwned.stream().sorted().forEach(owned::add);out.add("remote_owned_inputs",owned);
        rotation.annotate(out);
        if(samples.size()==CAPACITY){samples.removeFirst();dropped++;}samples.addLast(out);
    }
    private static JsonArray vector(double x,double y,double z) {
        var out=new JsonArray();out.add(x);out.add(y);out.add(z);return out;
    }
    public JsonObject snapshot(Minecraft mc,String actorSession,int limit) {
        bind(mc);var out=new JsonObject();out.addProperty("profile","native_player_motion_ticks_v1");
        out.addProperty("actor_session",actorSession);out.addProperty("capacity",CAPACITY);
        out.addProperty("dropped_samples",dropped);out.addProperty("read_only_world_state",true);
        var rows=new JsonArray();int skip=Math.max(0,samples.size()-limit),index=0;
        for(var sample:samples)if(index++>=skip)rows.add(sample.deepCopy());
        out.add("samples",rows);out.addProperty("sample_count",rows.size());
        out.addProperty("text","Bounded end-of-client-tick native player telemetry; no predicted physics or hidden world scan.");
        return out;
    }
    public static int requestLimit(JsonObject q) {
        return q.has("limit")?Protocol.integer(q,"limit",1,CAPACITY):CAPACITY;
    }
}
