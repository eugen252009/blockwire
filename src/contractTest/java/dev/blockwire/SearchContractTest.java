package dev.blockwire;

import com.google.gson.*;
import net.minecraft.SharedConstants;
import net.minecraft.server.Bootstrap;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.material.FluidState;
import net.minecraft.world.phys.Vec3;
import java.util.*;
import java.util.function.Predicate;

/** Additional native rays on bounded fixtures, not renderer/gameplay acceptance. */
public final class SearchContractTest {
    static int checks;
    static void check(boolean condition,String name){if(!condition)throw new AssertionError(name);checks++;}
    static final Vec3 EYE=new Vec3(.5,1.62,.5),FORWARD=new Vec3(0,0,1);
    static final class World implements VisibilityView.Source {
        final Map<BlockPos,BlockState> states=new HashMap<>();Predicate<BlockPos> loaded=p->true;int reads;
        public boolean loaded(BlockPos p){return loaded.test(p);}
        public BlockState getBlockState(BlockPos p){check(loaded(p),"SEARCH_no_unloaded_read");reads++;return states.getOrDefault(p,Blocks.AIR.defaultBlockState());}
        public FluidState getFluidState(BlockPos p){throw new AssertionError("No direct fluid query");}
        public BlockEntity getBlockEntity(BlockPos p){throw new AssertionError("No block entity contents");}
        public Iterable<BlockPos> candidates(){return List.of();}
        public boolean candidatesTruncated(){return false;}
        public int getHeight(){return 384;} public int getMinY(){return -64;}
        void put(int x,int y,int z,Block block){states.put(new BlockPos(x,y,z),block.defaultBlockState());}
    }
    static JsonObject page(World w,int page,String view){return SearchView.snapshot(w,EYE,FORWARD,0,"actor",new SearchView.Request("logs",64,30,page,view));}
    static Map<String,JsonObject> scan(World w,int range){
        String view=null;var found=new HashMap<String,JsonObject>();int cells=0;
        for(int p=0;p<SearchView.PAGES;p++){
            var r=SearchView.snapshot(w,EYE,FORWARD,0,"actor",new SearchView.Request("logs",range,30,p,view));view=r.get("view_id").getAsString();
            check(r.get("rays_cast").getAsInt()<=128,"SEARCH_ray_budget");cells+=r.get("visited_cells").getAsInt();
            check(r.get("page").getAsInt()==p,"SEARCH_page_identity");
            for(var h:r.getAsJsonArray("matches")){var hit=h.getAsJsonObject();found.put(hit.get("position").toString(),hit);}
        }
        check(cells==4225,"SEARCH_dense_grid_budget");return found;
    }
    static void rejected(Runnable operation,String label){try{operation.run();throw new AssertionError(label);}catch(IllegalArgumentException|IllegalStateException expected){checks++;}}
    public static void main(String[] args) throws Exception {
        SharedConstants.tryDetectVersion();Bootstrap.bootStrap();
        var w=new World();w.put(1,1,20,Blocks.OAK_LOG);
        var coarse=VisibilityView.snapshot(w,EYE,FORWARD,0);
        check(!coarse.has("sight_target"),"SEARCH_no_centre_hit_fixture");
        check(coarse.getAsJsonObject("visible_blocks").getAsJsonArray("runs").isEmpty(),"SEARCH_coarse_misses_between_rays");
        var found=scan(w,64);check(found.size()==1,"SEARCH_additional_rays_find_off_grid_log");
        var h=found.values().iterator().next();check(h.get("id").getAsString().equals("minecraft:oak_log"),"SEARCH_exact_id");
        var aim=h.getAsJsonArray("aim_position");var point=new Vec3(aim.get(0).getAsDouble(),aim.get(1).getAsDouble(),aim.get(2).getAsDouble());
        check(Math.abs(h.get("distance_blocks").getAsDouble()-EYE.distanceTo(point))<1e-8,"SEARCH_surface_distance");
        check(h.get("distance_blocks").getAsDouble()<64,"SEARCH_range");
        check(scan(w,16).isEmpty(),"SEARCH_short_range_excludes_target");
        for(Block blocker:List.of(Blocks.STONE,Blocks.GLASS,Blocks.OAK_LEAVES,Blocks.WATER)){
            w=new World();w.put(1,1,20,Blocks.OAK_LOG);
            for(int x=-4;x<=4;x++)for(int y=-3;y<=6;y++)w.put(x,y,10,blocker);
            check(scan(w,64).isEmpty(),"SEARCH_occlusion_conservative");
        }
        w=new World();w.put(1,1,20,Blocks.OAK_LOG);w.loaded=p->p.getZ()!=10;
        check(scan(w,64).isEmpty(),"SEARCH_unknown_opaque");
        w=new World();w.put(0,1,-10,Blocks.OAK_LOG);w.put(15,1,20,Blocks.OAK_LOG);w.put(5,6,20,Blocks.OAK_LOG);
        check(scan(w,64).isEmpty(),"SEARCH_cone_and_behind_excluded");
        w=new World();String view=page(w,0,null).get("view_id").getAsString();final World empty=w;
        rejected(()->SearchView.snapshot(empty,EYE.add(.01,0,0),FORWARD,0,"actor",new SearchView.Request("logs",64,30,1,view)),"SEARCH_pose_fence");
        rejected(()->SearchView.snapshot(empty,EYE,FORWARD,0,"other",new SearchView.Request("logs",64,30,1,view)),"SEARCH_actor_fence");
        rejected(()->SearchView.snapshot(empty,EYE,FORWARD,0,"actor",new SearchView.Request("minecraft:stone",64,30,1,view)),"SEARCH_query_fence");
        rejected(()->SearchView.snapshot(empty,EYE,new Vec3(1,0,0),-90,"actor",new SearchView.Request("logs",64,30,1,view)),"SEARCH_rotation_fence");
        for(int x=-40;x<=40;x++)for(int y=-40;y<=40;y++)w.put(x,y,40,Blocks.OAK_LOG);
        var crowded=SearchView.snapshot(w,EYE,FORWARD,0,"actor",new SearchView.Request("logs",64,90,16,null));
        check(crowded.getAsJsonArray("matches").size()==32 && crowded.get("truncated").getAsBoolean(),"SEARCH_result_cap");
        check(crowded.toString().length()<24000,"SEARCH_wire_bound");
        String valid="{\"op\":\"search\",\"actor_session\":\"actor\",\"target\":\"logs\",\"range\":64,\"cone_degrees\":30,\"page\":0}";
        SearchView.request(JsonParser.parseString(valid).getAsJsonObject());
        for(String bad:List.of(valid.replace("64","65"),valid.replace("30","91"),valid.replace("\"page\":0","\"page\":34"),
                valid.replace("\"page\":0","\"page\":1"),valid.replace("\"page\":0","\"page\":true"),valid.replace("logs","oak_log"),
                valid.replace("\"page\":0","\"x\":4,\"page\":0"))){
            rejected(()->SearchView.request(JsonParser.parseString(bad).getAsJsonObject()),"SEARCH_strict_request");
        }
        check(!SearchView.matches("logs","minecraft:oak_planks") && !SearchView.matches("logs","minecraft:stripped_oak_log") &&
            SearchView.matches("logs","minecraft:birch_log") && SearchView.matches("mod:beam","mod:beam"),"SEARCH_group_not_fuzzy");
        // Static dispatch guard: integration with a real client remains a separate gate.
        String source=java.nio.file.Files.readString(java.nio.file.Path.of("src/main/java/dev/blockwire/Blockwire.java"));
        String branch=source.substring(source.indexOf("case \"search\""),source.indexOf("case \"navigation\"",source.indexOf("case \"search\"")));
        check(branch.contains("guardedActor(q);playerRequired();") && branch.indexOf("guardedActor(q)")<branch.indexOf("SearchView.snapshot"),"SEARCH_dispatch_actor_guard");
        check(!branch.contains("release(") && !branch.contains("drive(") && !branch.contains("rotation."),"SEARCH_dispatch_read_only");
        System.out.println("BLOCKWIRE_SEARCH_CONTRACT_PASS checks="+checks);
    }
}
