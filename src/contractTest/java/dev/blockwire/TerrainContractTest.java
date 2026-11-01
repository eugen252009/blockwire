package dev.blockwire;

import com.google.gson.*;
import net.minecraft.world.phys.AABB;
import java.nio.file.*;

/** Clearance/parser contracts, NOT native jump-physics acceptance. */
public final class TerrainContractTest {
    static int checks;
    static void check(boolean ok,String label){checks++;if(!ok)throw new AssertionError(label);}
    public static void main(String[] args) throws Exception {
        net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();
        AABB low=new AABB(.2,.001,.2,.8,1.8,.8), high=low.move(1,1,0);
        AABB support=new AABB(1,0,0,2,1,1), ceiling=new AABB(0,3,0,2,4,1);
        check(NavigationView.stepClear(low,high,b->!b.intersects(support)),"TR01_step_clear_native_boxes");
        check(NavigationView.stepClear(high,low,b->!b.intersects(support)),"TR02_reverse_step_clear");
        check(!NavigationView.stepClear(low,high,b->!b.intersects(ceiling)),"TR03_low_ceiling_rejected");
        check(!NavigationView.stepClear(low,low.move(1,2,0),b->true),"TR04_two_block_step_rejected");
        check(!NavigationView.stepClear(low,low.move(2,1,0),b->true),"TR05_gap_rejected");
        check(!NavigationView.stepClear(low,high,b->false),"TR06_blocked_sweep_rejected");
        check(!Protocol.bool(new JsonObject(),"terrain",false),"TR07_legacy_flat_default");
        for(String value:new String[]{"0","1","null","\"true\"","{}","[]"}) {
            var q=new JsonObject();q.add("terrain",JsonParser.parseString(value));
            try {Protocol.bool(q,"terrain",false);throw new AssertionError("TR08_strict_terrain_flag");}
            catch(IllegalArgumentException expected){checks++;}
        }
        var q=new JsonObject();q.addProperty("terrain",true);
        check(Protocol.bool(q,"terrain",false),"TR09_explicit_terrain_optin");
        String source=Files.readString(Path.of("src/main/java/dev/blockwire/NavigationView.java"));
        check(source.contains("{1,0},{0,1},{1,1},{1,-1}") && source.contains("diagonal && dy!=0"),"TR10_flat_diagonal_only");
        check(source.contains("{2,0},{0,2},{2,2},{2,-2}") && source.contains("transition.addProperty(\"kind\",\"gap_jump\")") && source.contains("landingNeighbors<2"),"TR11_gap_requires_broad_landing");
        check(source.contains("indices.containsKey(middle)") && source.contains("indices.containsKey(behind)"),"TR12_gap_and_runup_geometry");
        check(source.contains("source_recovered_from_partial_support") && source.contains("if(!centerAccess && actor.onGround())") && source.contains("dx>.8 || dz>.8"),"TR13_partial_support_recovery_is_bounded");
        System.out.println("BLOCKWIRE_TERRAIN_CONTRACT_PASS checks="+checks);
    }
}
