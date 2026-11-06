package dev.blockwire;

import com.google.gson.*;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.phys.*;
import net.minecraft.world.phys.shapes.CollisionContext;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;

/** Explicit dense first-surface search, paged to bound client-thread work. Not renderer pixels. */
public final class SearchView {
    private SearchView() {}
    public static final int SIDE=65, CELLS=SIDE*SIDE, PAGE_SIZE=128, PAGES=(CELLS+PAGE_SIZE-1)/PAGE_SIZE, MAX_MATCHES=32;
    private static final Set<String> LOGS=Set.of("oak","spruce","birch","jungle","acacia","dark_oak","mangrove","cherry","pale_oak");
    public record Request(String target,int range,int cone,int page,String view) {}
    public static Request request(JsonObject q) {
        Protocol.fields(q,"target","range","cone_degrees","page","view_id","actor_session");
        String actor=Protocol.string(q,"actor_session"),target=Protocol.string(q,"target");
        if(actor.isEmpty() || actor.length()>128)throw new IllegalArgumentException("invalid_actor_session");
        if(target.length()>128 || !(target.equals("logs") || target.matches("[a-z0-9_.-]+:[a-z0-9_./-]+")))
            throw new IllegalArgumentException("invalid_search_target");
        int range=Protocol.integer(q,"range",1,64),cone=Protocol.integer(q,"cone_degrees",10,90),page=Protocol.integer(q,"page",0,PAGES-1);
        String view=q.has("view_id")?Protocol.string(q,"view_id"):null;
        if((page>0 && view==null) || (view!=null && !view.matches("[0-9a-f]{64}")))throw new IllegalArgumentException("search_view_required");
        return new Request(target,range,cone,page,view);
    }
    static boolean matches(String target,String id) {
        return target.equals(id) || (target.equals("logs") && LOGS.stream().anyMatch(wood->id.equals("minecraft:"+wood+"_log")));
    }
    static String stamp(String actor,Vec3 eye,Vec3 forward,float yaw,Request request) {
        String text=actor+"|"+eye+"|"+forward+"|"+Float.toHexString(yaw)+"|"+request.target+"|"+request.range+"|"+request.cone;
        try {return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(text.getBytes(StandardCharsets.UTF_8)));}
        catch(java.security.NoSuchAlgorithmException impossible){throw new AssertionError(impossible);}
    }
    public static JsonObject snapshot(Minecraft mc,String actor,Request request) {
        return snapshot(new VisibilityView.LoadedSource(mc.level,mc.player.blockPosition()),mc.player.getEyePosition(),
            mc.player.getViewVector(1),mc.player.getYRot(),actor,request);
    }
    static JsonArray xyz(double x,double y,double z) {var a=new JsonArray();a.add(x);a.add(y);a.add(z);return a;}
    static JsonObject snapshot(VisibilityView.Source source,Vec3 eye,Vec3 forward,float yaw,String actor,Request request) {
        String view=stamp(actor,eye,forward,yaw,request);
        if(request.view!=null && !request.view.equals(view))throw new IllegalStateException("search_view_changed");
        forward=forward.normalize();var right=Vec3.directionFromRotation(0,yaw+90);var up=right.cross(forward).normalize();
        double tangent=Math.tan(Math.toRadians(request.cone/2.)),cosine=Math.cos(Math.toRadians(request.cone/2.));
        var blocks=VisibilityView.loadedOnly(source);var found=new LinkedHashMap<BlockPos,JsonObject>();
        int start=request.page*PAGE_SIZE,end=Math.min(start+PAGE_SIZE,CELLS),rays=0;boolean truncated=false;
        for(int index=start;index<end;index++) {
            int row=index/SIDE,col=index%SIDE;
            double x=(2.*col/(SIDE-1)-1)*tangent,y=(1-2.*row/(SIDE-1))*tangent;
            var direction=forward.add(right.scale(x)).add(up.scale(y)).normalize();
            if(direction.dot(forward)<cosine-1e-12)continue;
            rays++;
            var hit=blocks.clip(new ClipContext(eye,eye.add(direction.scale(request.range)),ClipContext.Block.OUTLINE,ClipContext.Fluid.ANY,CollisionContext.empty()));
            if(hit.getType()!=HitResult.Type.BLOCK || !source.loaded(hit.getBlockPos()))continue;
            var position=hit.getBlockPos();String id=BuiltInRegistries.BLOCK.getKey(blocks.getBlockState(position).getBlock()).toString();
            if(!matches(request.target,id) || found.containsKey(position))continue;
            if(found.size()>=MAX_MATCHES){truncated=true;continue;}
            var point=hit.getLocation();var result=new JsonObject();result.addProperty("id",id);
            var pos=new JsonArray();pos.add(position.getX());pos.add(position.getY());pos.add(position.getZ());result.add("position",pos);
            result.add("aim_position",xyz(point.x,point.y,point.z));result.addProperty("distance_blocks",eye.distanceTo(point));
            result.addProperty("eye_distance_to_center",eye.distanceTo(Vec3.atCenterOf(position)));
            result.addProperty("face",hit.getDirection().getName());found.put(position.immutable(),result);
        }
        var out=new JsonObject();out.addProperty("profile","targeted_surface_search_v1");out.addProperty("actor_session",actor);
        out.addProperty("target",request.target);out.addProperty("range",request.range);out.addProperty("cone_degrees",request.cone);
        out.addProperty("view_id",view);out.addProperty("page",request.page);out.addProperty("pages",PAGES);
        out.add("next_page",end==CELLS?JsonNull.INSTANCE:new JsonPrimitive(request.page+1));
        out.addProperty("visited_cells",end-start);out.addProperty("rays_cast",rays);out.addProperty("truncated",truncated);
        out.addProperty("sampled_at_ms",System.currentTimeMillis());out.add("eye_position",xyz(eye.x,eye.y,eye.z));
        out.add("forward",xyz(forward.x,forward.y,forward.z));var hits=new JsonArray();found.values().forEach(hits::add);out.add("matches",hits);
        return out;
    }
}
