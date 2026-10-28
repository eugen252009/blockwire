package dev.blockwire;

import com.google.gson.*;
import net.minecraft.SharedConstants;
import net.minecraft.core.BlockPos;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.material.FluidState;
import net.minecraft.world.phys.Vec3;
import java.util.*;
import java.util.function.Predicate;

/** Real native outline rays on deterministic client-data fixtures, NOT graphical acceptance. */
public final class VisibilityContractTest {
    private static int checks;
    private static void check(boolean value,String label) {if(!value)throw new AssertionError(label);checks++;}
    private static final Vec3 EYE=new Vec3(.5,1.62,.5),FORWARD=new Vec3(0,0,1);
    private static final class World implements VisibilityView.Source {
        final Map<BlockPos,BlockState> states=new HashMap<>();
        final List<BlockPos> candidates=new ArrayList<>();
        Predicate<BlockPos> loaded=p->true;
        int reads;
        public boolean loaded(BlockPos pos) {return loaded.test(pos);}
        public BlockState getBlockState(BlockPos pos) {
            if(!loaded(pos))throw new AssertionError("unloaded_state_must_not_be_read");
            reads++;return states.getOrDefault(pos,Blocks.AIR.defaultBlockState());
        }
        public FluidState getFluidState(BlockPos pos) {throw new AssertionError("use_loaded_only_state_for_fluid");}
        public BlockEntity getBlockEntity(BlockPos pos) {throw new AssertionError("never_read_block_entity_contents");}
        public int getHeight() {return 384;}
        public int getMinY() {return -64;}
        public Iterable<BlockPos> candidates() {return candidates;}
        public boolean candidatesTruncated() {return false;}
        void put(int x,int y,int z,Block block) {
            var pos=new BlockPos(x,y,z);states.put(pos,block.defaultBlockState());candidates.add(pos);
        }
        JsonObject observe() {return VisibilityView.snapshot(this,EYE,FORWARD,0);}
    }
    private static boolean contains(JsonObject view,int x,int y,int z) {
        for(var entry:view.getAsJsonArray("visible_interactables")) {
            var p=entry.getAsJsonObject().getAsJsonArray("position");
            if(p.get(0).getAsInt()==x && p.get(1).getAsInt()==y && p.get(2).getAsInt()==z)return true;
        }
        return false;
    }
    private static Map<BlockPos,String> decode(JsonObject blocks) {
        var origin=blocks.getAsJsonArray("origin");var palette=blocks.getAsJsonArray("palette");
        var result=new HashMap<BlockPos,String>();
        for(var element:blocks.getAsJsonArray("runs")) {
            var run=element.getAsJsonArray();int length=run.get(4).getAsInt();
            check(length>0,"VIS07_positive_run_length");
            for(int dx=0;dx<length;dx++) {
                var pos=new BlockPos(origin.get(0).getAsInt()+run.get(1).getAsInt()+dx,
                    origin.get(1).getAsInt()+run.get(2).getAsInt(),origin.get(2).getAsInt()+run.get(3).getAsInt());
                check(result.put(pos,palette.get(run.get(0).getAsInt()).getAsString())==null,"VIS07_no_duplicate_cells");
            }
        }
        return result;
    }
    public static void main(String[] args) {
        SharedConstants.tryDetectVersion();Bootstrap.bootStrap();
        // VIS01: a chest beyond vanilla reach is detected; no action or inventory is involved.
        var world=new World();world.put(0,1,10,Blocks.CHEST);
        var view=world.observe();
        check(contains(view,0,1,10),"VIS01_distant_chest_detected");
        check(view.getAsJsonObject("sight_target").get("id").getAsString().equals("minecraft:chest"),"VIS01_extended_center_ray");
        var target=view.getAsJsonArray("visible_interactables").get(0).getAsJsonObject();
        check(target.get("distance").getAsDouble()>4.5,"VIS01_detection_not_interaction_reach");
        check(target.keySet().equals(Set.of("id","position","aim_position","distance","face","kind")),"VIS02_no_container_contents_or_names");
        // VIS03: outline occlusion is conservative, including glass. No hidden chest is reported.
        for(Block blocker:List.of(Blocks.STONE,Blocks.GLASS,Blocks.WATER)) {
            world=new World();world.put(0,1,10,Blocks.CHEST);
            for(int x=-3;x<=3;x++)for(int y=-2;y<=5;y++)world.states.put(new BlockPos(x,y,5),blocker.defaultBlockState());
            check(!contains(world.observe(),0,1,10),"VIS03_occluded_chest_rejected");
        }
        // VIS04: never read missing chunks; missing terrain must block rays to loaded terrain behind it.
        world=new World();world.put(0,1,10,Blocks.CHEST);world.loaded=p->p.getZ()!=5;
        view=world.observe();
        check(!contains(view,0,1,10),"VIS04_missing_chunk_is_opaque");
        check(!decode(view.getAsJsonObject("visible_blocks")).containsKey(new BlockPos(0,1,10)),"VIS04_no_surface_through_unknown");
        var safe=VisibilityView.loadedOnly(world);
        check(safe.getBlockEntity(new BlockPos(0,1,10))==null,"VIS02_block_entity_values_inaccessible");
        // VIS05: position/type alone is not enough; behind-camera, far and obstructed objects are omitted.
        world=new World();world.put(0,1,-10,Blocks.CHEST);world.put(0,1,66,Blocks.CHEST);
        check(world.observe().getAsJsonArray("visible_interactables").isEmpty(),"VIS05_range_and_view_filter");
        world=new World();world.put(9,1,25,Blocks.BARREL);
        check(contains(world.observe(),9,1,25),"VIS05_off_center_candidate_detected");
        // VIS06: fixed budget and explicit partial/truncation metadata in an extreme fixture.
        world=new World();
        for(int z=3;z<=60;z++)for(int x=-20;x<=20;x++)world.put(x,1,z,Blocks.CHEST);
        view=world.observe();var meta=view.getAsJsonObject("visibility");
        check(view.getAsJsonArray("visible_interactables").size()<=16,"VIS06_target_cap");
        check(meta.get("candidate_sight_tests").getAsInt()<=64,"VIS06_sight_test_cap");
        check(meta.get("candidate_positions_visited").getAsInt()<=2048,"VIS06_candidate_metadata_cap");
        check(meta.get("sample_rays").getAsInt()==273,"VIS06_sample_ray_cap");
        check(meta.get("partial").getAsBoolean() && meta.get("candidate_limit_reached").getAsBoolean(),"VIS06_partial_is_explicit");
        check(view.getAsJsonObject("visible_blocks").get("observed_blocks").getAsInt()<=337,"VIS06_surface_cap");
        check(view.toString().length()<100_000,"VIS06_bounded_response");
        // More than sixteen individually visible objects, not just an occluding wall of chests.
        world=new World();
        for(int angle=-45;angle<=45;angle+=3)world.put((int)Math.round(Math.sin(Math.toRadians(angle))*25),1,
            (int)Math.round(Math.cos(Math.toRadians(angle))*25),Blocks.CHEST);
        view=world.observe();
        check(view.getAsJsonArray("visible_interactables").size()==16,"VIS06_target_cap");
        check(view.getAsJsonObject("visibility").get("interactables_truncated").getAsBoolean(),"VIS06_target_truncation_flag");
        // VIS07: codec is exactly reversible, supports negatives, and NEVER joins across unknown cells/types/rows.
        var surfaces=new HashMap<BlockPos,BlockState>();
        for(int x=-10;x<20;x++)surfaces.put(new BlockPos(x,7,-4),Blocks.STONE.defaultBlockState());
        surfaces.put(new BlockPos(21,7,-4),Blocks.STONE.defaultBlockState()); // Gap at x=20.
        surfaces.put(new BlockPos(22,7,-4),Blocks.DIRT.defaultBlockState());
        surfaces.put(new BlockPos(23,8,-4),Blocks.STONE.defaultBlockState());
        var packed=VisibilityView.compress(new BlockPos(-20,12,-30),surfaces);var decoded=decode(packed);
        check(decoded.keySet().equals(surfaces.keySet()),"VIS07_roundtrip_positions_and_gaps");
        check(decoded.get(new BlockPos(22,7,-4)).equals("minecraft:dirt"),"VIS07_palette_preserves_type");
        check(packed.getAsJsonArray("runs").size()==4,"VIS07_contiguous_x_run_compression");
        check(VisibilityView.compress(BlockPos.ZERO,Map.of()).getAsJsonArray("runs").isEmpty(),"VIS07_empty_surface");
        var random=new Random(7241);
        for(int trial=0;trial<20;trial++) {
            surfaces.clear();
            for(int i=0;i<100;i++)surfaces.put(new BlockPos(random.nextInt(41)-20,random.nextInt(9)-4,random.nextInt(21)-10),
                (random.nextBoolean()?Blocks.STONE:Blocks.DIRT).defaultBlockState());
            decoded=decode(VisibilityView.compress(new BlockPos(-200,50,200),surfaces));
            check(decoded.keySet().equals(surfaces.keySet()),"VIS07_generated_roundtrip_positions");
            for(var entry:surfaces.entrySet())check(decoded.get(entry.getKey()).equals(
                entry.getValue().is(Blocks.STONE)?"minecraft:stone":"minecraft:dirt"),"VIS07_generated_roundtrip_types");
        }
        // VIS08: ordinary non-container controls can be observed when a sample actually hits them.
        check(VisibilityView.kind(Blocks.CRAFTING_TABLE.defaultBlockState()).equals("workstation"),"VIS08_workstation_kind");
        check(VisibilityView.kind(Blocks.OAK_DOOR.defaultBlockState()).equals("door"),"VIS08_door_kind");
        check(VisibilityView.kind(Blocks.STONE.defaultBlockState())==null,"VIS08_no_invented_interaction");
        System.out.println("BLOCKWIRE_VISIBILITY_CONTRACT_PASS checks="+checks);
    }
}
