package dev.blockwire;

import com.google.gson.*;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.Pose;
import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.level.block.*;
import net.minecraft.world.phys.AABB;
import java.util.*;

/** On-demand local geometry, never a tick scan or arbitrary remote block query. Flat full blocks only. */
public final class NavigationView {
    public static final int RADIUS=4;
    /** Conservative clearance envelope, not jump simulation; native physics executes the step. */
    static boolean stepClear(AABB a,AABB b,java.util.function.Predicate<AABB> clear) {
        if(Math.abs(Math.abs(a.minY-b.minY)-1.)>.01 ||
           Math.abs(Math.abs(a.minX-b.minX)+Math.abs(a.minZ-b.minZ)-1.)>.01)return false;
        AABB low=a.minY<b.minY?a:b,high=a.minY<b.minY?b:a;
        AABB raised=low.move(0,1.3,0),landing=high.move(0,.3,0);
        return clear.test(low.minmax(raised)) && clear.test(raised.minmax(landing)) && clear.test(high.minmax(landing));
    }
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
    public String actorSession(Minecraft mc) {refresh(mc);return session;}
    public JsonObject snapshot(Minecraft mc) {return snapshot(mc,false);}
    public JsonObject snapshot(Minecraft mc,boolean terrain) {
        refresh(mc);
        var out=new JsonObject();out.addProperty("profile",terrain?"stepped_full_blocks_v1":"flat_full_blocks_v1");
        out.addProperty("actor_session",session);out.addProperty("sampled_at_ms",System.currentTimeMillis());
        out.addProperty("hotbar_actor_session",true);out.addProperty("independent_input_leases",true);
        out.addProperty("radius",RADIUS);
        if(actor==null || level==null){out.addProperty("ready",false);out.addProperty("reason","not_in_world");return out;}
        var position=new JsonArray();position.add(actor.getX());position.add(actor.getY());position.add(actor.getZ());
        out.add("position",position);out.addProperty("dimension",level.dimension().identifier().toString());
        out.addProperty("health",actor.getHealth());out.addProperty("alive",actor.isAlive());out.addProperty("on_ground",actor.onGround());
        var velocity=actor.getDeltaMovement();var velocityJson=new JsonArray();velocityJson.add(velocity.x);velocityJson.add(velocity.y);velocityJson.add(velocity.z);
        out.add("velocity",velocityJson);out.addProperty("horizontal_speed",Math.hypot(velocity.x,velocity.z));
        out.addProperty("horizontal_collision",actor.horizontalCollision);out.addProperty("minor_horizontal_collision",actor.minorHorizontalCollision);
        out.addProperty("vertical_collision",actor.verticalCollision);out.addProperty("vertical_collision_below",actor.verticalCollisionBelow);
        out.addProperty("sprinting",actor.isSprinting());out.addProperty("sneaking",actor.isShiftKeyDown());out.addProperty("fall_distance",actor.fallDistance);
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
        out.addProperty("threat_profile","nearby_hostiles_v1");
        var eye=new JsonArray();eye.add(actor.getEyePosition().x);eye.add(actor.getEyePosition().y);eye.add(actor.getEyePosition().z);
        out.add("eye_position",eye);
        var threats=new JsonArray();
        var nearby=level.getEntitiesOfClass(Monster.class,actor.getBoundingBox().inflate(8),
            e->e.isAlive() && actor.distanceToSqr(e)<=64);
        nearby.sort(Comparator.comparingDouble(actor::distanceToSqr));
        for(var mob:nearby) {
            var threat=new JsonObject();threat.addProperty("entity_id",mob.getId());threat.addProperty("distance",actor.distanceTo(mob));
            threat.addProperty("type",BuiltInRegistries.ENTITY_TYPE.getKey(mob.getType()).toString());
            var xyz=new JsonArray();xyz.add(mob.getX());xyz.add(mob.getY());xyz.add(mob.getZ());threat.add("position",xyz);
            var aim=new JsonArray();aim.add(mob.getEyePosition().x);aim.add(mob.getEyePosition().y);aim.add(mob.getEyePosition().z);
            threat.add("eye_position",aim);threat.addProperty("visible",!mob.isInvisibleTo(actor) && actor.hasLineOfSight(mob));
            threats.add(threat);if(threats.size()==16)break;
        }
        out.add("nearby_hostiles",threats);
        int ox=actor.blockPosition().getX(),oz=actor.blockPosition().getZ(),y=(int)Math.rint(actor.getY());
        double half=actor.getBbWidth()/2.0,height=actor.getDimensions(Pose.STANDING).height();
        var cells=new JsonArray();var boxes=new HashMap<String,AABB>();var indices=new HashMap<String,Integer>();
        for(int x=ox-RADIUS;x<=ox+RADIUS;x++)for(int z=oz-RADIUS;z<=oz+RADIUS;z++)
        for(int cy=terrain?y-2:y;cy<=(terrain?y+2:y);cy++) {
            var foot=new BlockPos(x,cy,z);var floor=foot.below();
            if(!level.hasChunksAt(x-1,y-1,z-1,x+1,y+3,z+1) ||
                !level.getBlockState(floor).isCollisionShapeFullBlock(level,floor))continue;
            var box=new AABB(x+.5-half,cy+.001,z+.5-half,x+.5+half,cy+height,z+.5+half);
            if(!level.noCollision(actor,box))continue;
            var hazards=new JsonArray();boolean fluid=false;
            for(int dy=-1;dy<=2;dy++) {
                var pos=foot.offset(0,dy,0);var state=level.getBlockState(pos);
                if(!state.getFluidState().isEmpty())fluid=true;
                if(HAZARDS.contains(state.getBlock()))hazards.add("known_hazard");
            }
            if(fluid)continue; // Swimming, flowing fluids and waterlogged routes are not supported.
            String key=x+","+cy+","+z;indices.put(key,cells.size());boxes.put(key,box);
            var cell=new JsonObject();var xyz=new JsonArray();xyz.add(x);xyz.add(cy);xyz.add(z);
            cell.add("position",xyz);cell.add("hazards",hazards);cells.add(cell);
        }
        var edges=new JsonArray();var transitions=new JsonArray();
        for(var entry:indices.entrySet()) {
            String[] split=entry.getKey().split(",");int x=Integer.parseInt(split[0]),cy=Integer.parseInt(split[1]),z=Integer.parseInt(split[2]);
            for(int[] delta:new int[][]{{1,0},{0,1},{1,1},{1,-1}})for(int dy=terrain?-1:0;dy<=(terrain?1:0);dy++) {
                boolean diagonal=delta[0]!=0 && delta[1]!=0;
                if(diagonal && dy!=0)continue; // Vertical diagonal jumps are not inferred.
                String other=(x+delta[0])+","+(cy+dy)+","+(z+delta[1]);
                if(!indices.containsKey(other))continue;
                if(diagonal && (!indices.containsKey((x+delta[0])+","+cy+","+z) ||
                                !indices.containsKey(x+","+cy+","+(z+delta[1]))))continue;
                AABB a=boxes.get(entry.getKey()),b=boxes.get(other);
                boolean clear=dy==0?level.noCollision(actor,a.minmax(b)):stepClear(a,b,box->level.noCollision(actor,box));
                if(!clear)continue;
                var edge=new JsonArray();edge.add(entry.getValue());edge.add(indices.get(other));edges.add(edge);
                var transition=new JsonObject();transition.addProperty("a",entry.getValue());transition.addProperty("b",indices.get(other));
                transition.addProperty("kind",dy!=0?"step":diagonal?"diagonal":"flat");transitions.add(transition);
            }
            if(terrain)for(int[] delta:new int[][]{{2,0},{0,2},{2,2},{2,-2}}) {
                String other=(x+delta[0])+","+cy+","+(z+delta[1]);
                String middle=(x+delta[0]/2)+","+cy+","+(z+delta[1]/2);
                String behind=(x-delta[0]/2)+","+cy+","+(z-delta[1]/2);
                if(!indices.containsKey(other) || indices.containsKey(middle) || !indices.containsKey(behind))continue;
                AABB a=boxes.get(entry.getKey()),b=boxes.get(other),sweep=a.minmax(b);
                AABB flight=new AABB(sweep.minX,sweep.minY,sweep.minZ,sweep.maxX,sweep.maxY+1.3,sweep.maxZ);
                if(!level.noCollision(actor,flight))continue;
                int landingNeighbors=0;
                for(int[] side:new int[][]{{1,0},{-1,0},{0,1},{0,-1}})
                    if(indices.containsKey((x+delta[0]+side[0])+","+cy+","+(z+delta[1]+side[1])))landingNeighbors++;
                if(landingNeighbors<2)continue; // Require a broad native landing platform, not one isolated block.
                var edge=new JsonArray();edge.add(entry.getValue());edge.add(indices.get(other));edges.add(edge);
                var transition=new JsonObject();transition.addProperty("a",entry.getValue());transition.addProperty("b",indices.get(other));
                transition.addProperty("kind","gap_jump");transitions.add(transition);
            }
        }
        String positionKey=ox+","+y+","+oz,currentKey=positionKey;
        AABB body=actor.getBoundingBox().deflate(.001);
        boolean centerAccess=boxes.containsKey(currentKey) && level.noCollision(actor,body.minmax(boxes.get(currentKey)));
        boolean recovered=false;
        if(!centerAccess && actor.onGround()) {
            double best=Double.POSITIVE_INFINITY;
            for(var entry:boxes.entrySet()) {
                String[] split=entry.getKey().split(",");int x=Integer.parseInt(split[0]),cy=Integer.parseInt(split[1]),z=Integer.parseInt(split[2]);
                double dx=Math.abs(actor.getX()-x-.5),dz=Math.abs(actor.getZ()-z-.5),distance=Math.hypot(dx,dz);
                if(cy!=y || dx>.8 || dz>.8 || distance>=best || !level.noCollision(actor,body.minmax(entry.getValue())))continue;
                currentKey=entry.getKey();best=distance;centerAccess=true;recovered=true;
            }
        }
        String[] selected=currentKey.split(",");var current=new JsonArray();
        current.add(Integer.parseInt(selected[0]));current.add(Integer.parseInt(selected[1]));current.add(Integer.parseInt(selected[2]));out.add("current_cell",current);
        var positionCell=new JsonArray();positionCell.add(ox);positionCell.add(y);positionCell.add(oz);out.add("position_cell",positionCell);
        out.addProperty("source_recovered_from_partial_support",recovered);
        out.addProperty("current_center_access",centerAccess);out.add("cells",cells);out.add("edges",edges);out.add("transitions",transitions);
        out.addProperty("max_cells",terrain?405:81);
        out.addProperty("text",(terrain?"Local stepped full-block mesh; at most 405 cells, Y +/-2, one-block edges. ":"Local flat full-block navigation mesh; at most 81 cells. ")+ "Loaded chunks only. "+
            "Known hazards/hostiles are incomplete client knowledge, not a no-damage guarantee.");
        return out;
    }
}
