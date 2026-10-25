package dev.blockwire;

import com.google.gson.*;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.world.entity.Pose;
import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.level.block.*;
import net.minecraft.world.phys.AABB;
import java.util.*;

/** On-demand local geometry, never a tick scan or arbitrary remote block query. Flat full blocks only. */
public final class NavigationView {
    public static final int RADIUS=4;
    private net.minecraft.client.player.LocalPlayer actor;
    private net.minecraft.client.multiplayer.ClientLevel level;
    private String session;
    private static final Set<Block> HAZARDS=Set.of(Blocks.MAGMA_BLOCK,Blocks.CACTUS,Blocks.FIRE,Blocks.SOUL_FIRE,
        Blocks.CAMPFIRE,Blocks.SOUL_CAMPFIRE,Blocks.SWEET_BERRY_BUSH,Blocks.WITHER_ROSE,Blocks.POWDER_SNOW,
        Blocks.POINTED_DRIPSTONE,Blocks.NETHER_PORTAL,Blocks.END_PORTAL,Blocks.END_GATEWAY,Blocks.COBWEB,
        Blocks.SLIME_BLOCK,Blocks.HONEY_BLOCK);
    public boolean matches(Minecraft mc,String supplied) {
        return session!=null && session.equals(supplied) && actor!=null && mc.player==actor && mc.level==level;
    }
    private void refresh(Minecraft mc) {
        if(mc.player!=actor || mc.level!=level || session==null) {
            actor=mc.player;level=mc.level;session=UUID.randomUUID().toString();
        }
    }
    public JsonObject snapshot(Minecraft mc) {
        refresh(mc);
        var out=new JsonObject();out.addProperty("profile","flat_full_blocks_v1");
        out.addProperty("actor_session",session);out.addProperty("sampled_at_ms",System.currentTimeMillis());
        out.addProperty("radius",RADIUS);
        if(actor==null || level==null){out.addProperty("ready",false);out.addProperty("reason","not_in_world");return out;}
        var position=new JsonArray();position.add(actor.getX());position.add(actor.getY());position.add(actor.getZ());
        out.add("position",position);out.addProperty("dimension",level.dimension().identifier().toString());
        out.addProperty("health",actor.getHealth());out.addProperty("alive",actor.isAlive());out.addProperty("on_ground",actor.onGround());
        String reason=null;
        if(!actor.isAlive())reason="player_dead";
        else if(mc.gui.screen()!=null || mc.gui.overlay()!=null || mc.isPaused())reason="screen_or_pause";
        else if(mc.gameMode==null || mc.gameMode.isSpectator())reason="unsupported_game_mode";
        else if(actor.isPassenger() || actor.isFallFlying() || actor.getAbilities().flying)reason="unsupported_movement_mode";
        else if(!actor.onGround())reason="not_grounded";
        else if(Math.abs(actor.getY()-Math.rint(actor.getY()))>.05)reason="unsupported_floor_geometry";
        else if(actor.isInWater())reason="in_water";
        out.addProperty("on_fire",actor.isOnFire());
        out.addProperty("ready",reason==null);
        if(reason!=null){out.addProperty("reason",reason);return out;}
        var threats=new JsonArray();
        for(var mob:level.getEntitiesOfClass(Monster.class,actor.getBoundingBox().inflate(8),e->e.isAlive())) {
            var threat=new JsonObject();threat.addProperty("entity_id",mob.getId());threat.addProperty("distance",actor.distanceTo(mob));
            threats.add(threat);if(threats.size()==16)break;
        }
        out.add("nearby_hostiles",threats);
        int ox=actor.blockPosition().getX(),oz=actor.blockPosition().getZ(),y=(int)Math.rint(actor.getY());
        double half=actor.getBbWidth()/2.0,height=actor.getDimensions(Pose.STANDING).height();
        var cells=new JsonArray();var boxes=new HashMap<String,AABB>();var indices=new HashMap<String,Integer>();
        for(int x=ox-RADIUS;x<=ox+RADIUS;x++)for(int z=oz-RADIUS;z<=oz+RADIUS;z++) {
            var foot=new BlockPos(x,y,z);var floor=foot.below();
            if(!level.hasChunksAt(x-1,y-1,z-1,x+1,y+3,z+1) ||
                !level.getBlockState(floor).isCollisionShapeFullBlock(level,floor))continue;
            var box=new AABB(x+.5-half,y+.001,z+.5-half,x+.5+half,y+height,z+.5+half);
            if(!level.noCollision(actor,box))continue;
            var hazards=new JsonArray();boolean fluid=false;
            for(int dy=-1;dy<=2;dy++) {
                var pos=foot.offset(0,dy,0);var state=level.getBlockState(pos);
                if(!state.getFluidState().isEmpty())fluid=true;
                if(HAZARDS.contains(state.getBlock()))hazards.add("known_hazard");
            }
            if(fluid)continue; // Swimming, flowing fluids and waterlogged routes are not supported.
            String key=x+","+z;indices.put(key,cells.size());boxes.put(key,box);
            var cell=new JsonObject();var xyz=new JsonArray();xyz.add(x);xyz.add(y);xyz.add(z);
            cell.add("position",xyz);cell.add("hazards",hazards);cells.add(cell);
        }
        var edges=new JsonArray();
        for(var entry:indices.entrySet()) {
            String[] split=entry.getKey().split(",");int x=Integer.parseInt(split[0]),z=Integer.parseInt(split[1]);
            for(int[] delta:new int[][]{{1,0},{0,1}}) {
                String other=(x+delta[0])+","+(z+delta[1]);
                if(!indices.containsKey(other) || !level.noCollision(actor,boxes.get(entry.getKey()).minmax(boxes.get(other))))continue;
                var edge=new JsonArray();edge.add(entry.getValue());edge.add(indices.get(other));edges.add(edge);
            }
        }
        var current=new JsonArray();current.add(ox);current.add(y);current.add(oz);out.add("current_cell",current);
        String currentKey=ox+","+oz;
        boolean centerAccess=boxes.containsKey(currentKey) &&
            level.noCollision(actor,actor.getBoundingBox().deflate(.001).minmax(boxes.get(currentKey)));
        out.addProperty("current_center_access",centerAccess);out.add("cells",cells);out.add("edges",edges);
        out.addProperty("text","Local flat full-block navigation mesh; at most 81 cells, loaded chunks only. "+
            "Known hazards/hostiles are incomplete client knowledge, not a no-damage guarantee.");
        return out;
    }
}
