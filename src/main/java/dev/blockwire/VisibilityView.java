package dev.blockwire;

import com.google.gson.*;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.level.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.LevelChunk;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.material.FluidState;
import net.minecraft.world.phys.*;
import net.minecraft.world.phys.shapes.CollisionContext;
import java.util.*;

/** Fixed-budget, on-demand first-surface observations. Never reads block-entity values or NBT. */
public final class VisibilityView {
    public static final int RANGE=64, WIDTH=21, HEIGHT=13, MAX_POSITIONS=2048, MAX_SIGHT_TESTS=64, MAX_INTERACTABLES=16;
    private VisibilityView() {}

    /** A missing chunk is opaque/unknown, not air. Implementations must never load/generate chunks. */
    interface Source extends BlockGetter {
        boolean loaded(BlockPos pos);
        Iterable<BlockPos> candidates();
        boolean candidatesTruncated();
    }

    private static final class LoadedSource implements Source {
        private final ClientLevel level;
        private final Map<Long,LevelChunk> chunks=new HashMap<>();
        private final int cx,cz;
        private boolean truncated;
        LoadedSource(ClientLevel level,BlockPos origin) {this.level=level;cx=origin.getX()>>4;cz=origin.getZ()>>4;}
        private LevelChunk chunk(int x,int z) {
            // Includes shape-neighbor queries: nothing outside this fixed loaded-chunk window is read.
            if(Math.abs(x-cx)>4 || Math.abs(z-cz)>4)return null;
            long key=((long)x<<32) ^ (z&0xffffffffL);
            if(!chunks.containsKey(key))chunks.put(key,level.getChunkSource().getChunk(x,z,ChunkStatus.FULL,false));
            return chunks.get(key);
        }
        public boolean loaded(BlockPos pos) {return chunk(pos.getX()>>4,pos.getZ()>>4)!=null;}
        public BlockState getBlockState(BlockPos pos) {
            var chunk=chunk(pos.getX()>>4,pos.getZ()>>4);
            return chunk==null?Blocks.BARRIER.defaultBlockState():chunk.getBlockState(pos);
        }
        public FluidState getFluidState(BlockPos pos) {return getBlockState(pos).getFluidState();}
        public BlockEntity getBlockEntity(BlockPos pos) {return null;} // Deliberately no contents/custom names.
        public int getHeight() {return level.getHeight();}
        public int getMinY() {return level.getMinY();}
        public boolean candidatesTruncated() {return truncated;}
        public Iterable<BlockPos> candidates() {
            var positions=new ArrayList<BlockPos>();
            // Near chunks first; fixed 9x9 window and bounded metadata visits, no block volume scan.
            for(int ring=0;ring<=4;ring++)for(int dx=-ring;dx<=ring;dx++)for(int dz=-ring;dz<=ring;dz++) {
                if(Math.max(Math.abs(dx),Math.abs(dz))!=ring)continue;
                var chunk=chunk(cx+dx,cz+dz);if(chunk==null)continue;
                for(var pos:chunk.getBlockEntities().keySet()) {
                    if(positions.size()==MAX_POSITIONS){truncated=true;return positions;}
                    positions.add(pos.immutable());
                }
            }
            return positions;
        }
    }

    public static JsonObject snapshot(Minecraft mc) {
        var p=mc.player;
        return snapshot(new LoadedSource(mc.level,p.blockPosition()),p.getEyePosition(),p.getViewVector(1),p.getYRot());
    }

    static BlockGetter loadedOnly(Source source) {
        return new BlockGetter() {
            public BlockState getBlockState(BlockPos pos) {
                return source.loaded(pos)?source.getBlockState(pos):Blocks.BARRIER.defaultBlockState();
            }
            public FluidState getFluidState(BlockPos pos) {return getBlockState(pos).getFluidState();}
            public BlockEntity getBlockEntity(BlockPos pos) {return null;}
            public int getHeight() {return source.getHeight();}
            public int getMinY() {return source.getMinY();}
        };
    }
    private static BlockHitResult cast(BlockGetter blocks,Vec3 eye,Vec3 end) {
        return blocks.clip(new ClipContext(eye,end,ClipContext.Block.OUTLINE,ClipContext.Fluid.ANY,CollisionContext.empty()));
    }
    private static boolean eligible(Vec3 eye,Vec3 forward,Vec3 point) {
        var delta=point.subtract(eye);
        return delta.lengthSqr()>0 && delta.lengthSqr()<=RANGE*RANGE && delta.normalize().dot(forward)>=.5;
    }
    static String kind(BlockState state) {
        var b=state.getBlock();
        if(b instanceof AbstractChestBlock<?> || b instanceof BarrelBlock || b instanceof ShulkerBoxBlock ||
            b instanceof AbstractFurnaceBlock || b instanceof HopperBlock || b instanceof DispenserBlock ||
            b instanceof BrewingStandBlock || b instanceof CrafterBlock)return "container";
        if(b instanceof CraftingTableBlock || b instanceof AnvilBlock || b instanceof EnchantingTableBlock ||
            b instanceof StonecutterBlock || b instanceof SmithingTableBlock || b instanceof LoomBlock ||
            b instanceof CartographyTableBlock || b instanceof GrindstoneBlock)return "workstation";
        if(b instanceof DoorBlock || b instanceof TrapDoorBlock || b instanceof FenceGateBlock)return "door";
        if(b instanceof ButtonBlock || b instanceof LeverBlock)return "switch";
        if(b instanceof BedBlock)return "bed";
        if(b instanceof BellBlock)return "bell";
        return null;
    }
    private record Seen(BlockPos position,BlockState state,Vec3 aim,double distance,String face) {}
    private static Seen seen(Source source,Vec3 eye,BlockHitResult hit,Vec3 aim) {
        if(hit.getType()!=HitResult.Type.BLOCK || !source.loaded(hit.getBlockPos()))return null;
        return new Seen(hit.getBlockPos().immutable(),source.getBlockState(hit.getBlockPos()),aim,
            eye.distanceTo(hit.getLocation()),hit.getDirection().getName());
    }
    private static JsonArray xyz(double x,double y,double z) {var a=new JsonArray();a.add(x);a.add(y);a.add(z);return a;}
    private static JsonArray xyz(BlockPos p) {var a=new JsonArray();a.add(p.getX());a.add(p.getY());a.add(p.getZ());return a;}
    private static String id(BlockState state) {return BuiltInRegistries.BLOCK.getKey(state.getBlock()).toString();}
    private static JsonObject describe(Seen seen) {
        var o=new JsonObject();o.addProperty("id",id(seen.state));o.add("position",xyz(seen.position));
        o.add("aim_position",xyz(seen.aim.x,seen.aim.y,seen.aim.z));o.addProperty("distance",seen.distance);
        o.addProperty("face",seen.face);return o;
    }

    static JsonObject snapshot(Source source,Vec3 eye,Vec3 forward,float yaw) {
        forward=forward.normalize();
        var blocks=loadedOnly(source);
        var origin=BlockPos.containing(eye);
        var surfaces=new HashMap<BlockPos,BlockState>();var interactables=new HashMap<BlockPos,Seen>();
        Seen sightTarget=null;
        // Perspective sample grid: 100 degrees horizontal, 70 vertical. Not renderer/pixel visibility.
        var right=Vec3.directionFromRotation(0,yaw+90);
        var up=right.cross(forward).normalize();
        for(int row=0;row<HEIGHT;row++)for(int col=0;col<WIDTH;col++) {
            double x=(2.0*col/(WIDTH-1)-1)*Math.tan(Math.toRadians(50));
            double y=(1-2.0*row/(HEIGHT-1))*Math.tan(Math.toRadians(35));
            var direction=forward.add(right.scale(x)).add(up.scale(y)).normalize();
            var hit=cast(blocks,eye,eye.add(direction.scale(RANGE)));
            var seen=seen(source,eye,hit,hit.getLocation());
            if(seen==null)continue;
            surfaces.put(seen.position,seen.state);
            if(row==HEIGHT/2 && col==WIDTH/2)sightTarget=seen;
            if(kind(seen.state)!=null)interactables.put(seen.position,seen);
        }
        // Target block-entity positions explicitly as small/distant chests can fall between sample rays.
        // Keep only a bounded nearest set before native visibility tests; never expose untested candidates.
        var candidates=new TreeSet<BlockPos>(Comparator.<BlockPos>comparingDouble(p->Vec3.atCenterOf(p).distanceToSqr(eye))
            .thenComparingInt(BlockPos::getX).thenComparingInt(BlockPos::getY).thenComparingInt(BlockPos::getZ));
        int visits=0;boolean candidateLimit=false;
        for(var pos:source.candidates()) {
            if(visits==MAX_POSITIONS){candidateLimit=true;break;}
            visits++;
            if(!source.loaded(pos) || !eligible(eye,forward,Vec3.atCenterOf(pos)) || kind(source.getBlockState(pos))==null)continue;
            candidates.add(pos.immutable());
            if(candidates.size()>MAX_SIGHT_TESTS){candidates.pollLast();candidateLimit=true;}
        }
        int tests=0;
        for(var pos:candidates) {
            tests++;
            for(double y:new double[]{.5,.85,.15}) {
                var aim=new Vec3(pos.getX()+.5,pos.getY()+y,pos.getZ()+.5);
                if(!eligible(eye,forward,aim))continue;
                var hit=cast(blocks,eye,aim);
                var seen=seen(source,eye,hit,aim);
                if(seen!=null && seen.position.equals(pos)) {
                    interactables.put(pos,seen);surfaces.put(pos,seen.state);break;
                }
            }
        }
        var ordered=new ArrayList<>(interactables.values());
        ordered.sort(Comparator.comparingDouble(Seen::distance).thenComparingInt(s->s.position.getX())
            .thenComparingInt(s->s.position.getY()).thenComparingInt(s->s.position.getZ()));
        var targets=new JsonArray();
        for(var seen:ordered.subList(0,Math.min(MAX_INTERACTABLES,ordered.size()))) {
            var o=describe(seen);o.addProperty("kind",kind(seen.state));targets.add(o);
        }
        var out=new JsonObject();out.add("visible_interactables",targets);
        if(sightTarget!=null)out.add("sight_target",describe(sightTarget));
        out.add("visible_blocks",compress(origin,surfaces));
        var meta=new JsonObject();meta.addProperty("profile","sampled_surfaces_v1");meta.addProperty("range",RANGE);
        meta.addProperty("sample_rays",WIDTH*HEIGHT);meta.addProperty("horizontal_fov",100);meta.addProperty("vertical_fov",70);
        meta.addProperty("candidate_cone_degrees",120);meta.addProperty("candidate_sight_tests",tests);
        meta.addProperty("candidate_positions_visited",visits);
        meta.addProperty("candidate_limit_reached",candidateLimit || source.candidatesTruncated());
        meta.addProperty("interactables_truncated",ordered.size()>MAX_INTERACTABLES);meta.addProperty("partial",true);
        out.add("visibility",meta);return out;
    }

    /** Lossless x-axis runs of ONLY sampled first-hit positions; never fill unknown cells. */
    static JsonObject compress(BlockPos origin,Map<BlockPos,BlockState> surfaces) {
        var positions=new ArrayList<>(surfaces.keySet());
        positions.sort(Comparator.<BlockPos>comparingInt(BlockPos::getY).thenComparingInt(BlockPos::getZ).thenComparingInt(BlockPos::getX));
        var palette=new JsonArray();var indices=new HashMap<String,Integer>();var runs=new JsonArray();
        JsonArray run=null;BlockPos previous=null;int previousType=-1;
        for(var pos:positions) {
            String block=id(surfaces.get(pos));
            if(!indices.containsKey(block)){indices.put(block,palette.size());palette.add(block);}
            int type=indices.get(block);
            if(previous!=null && type==previousType && pos.getY()==previous.getY() && pos.getZ()==previous.getZ() && pos.getX()==previous.getX()+1) {
                run.set(4,new JsonPrimitive(run.get(4).getAsInt()+1));
            } else {
                run=new JsonArray();run.add(type);run.add(pos.getX()-origin.getX());run.add(pos.getY()-origin.getY());
                run.add(pos.getZ()-origin.getZ());run.add(1);runs.add(run);
            }
            previous=pos;previousType=type;
        }
        var out=new JsonObject();out.addProperty("encoding","palette_x_runs_v1");out.add("origin",xyz(origin));
        out.add("palette",palette);out.add("runs",runs);out.addProperty("observed_blocks",positions.size());return out;
    }
}
