"""Fast SIMULATED/reference/closed-file contracts, NOT Minecraft acceptance."""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tests'))
from building.reference import House,verify,AIR
from building.program import fixture_program,frames
from building.snapshots import OWNER,FIXTURE,capture,restore,validate
from building.anvil import NBT,inflate,voxels
from building.live import native_proof
from blockwire.bcl import default_commands
from blockwire.bcl.compiler import arguments

class BenchmarkReference(unittest.TestCase):
    def setUp(self):
        self.h=House();self.good={p:'minecraft:air' for p in self.h.workspace()}
        self.good.update({p:'minecraft:grass_block' for p in self.h.floors()});self.good.update(self.h.blocks())
        self.native={'interior_accessible':True,'safe_player':True}
    def check_world(self,world=None,native=None):return verify(self.h,self.good if world is None else world,native=self.native if native is None else native)
    def test_BM01_exact_geometry_and_reference_file(self):
        self.assertEqual(len(self.h.blocks()),71)
        self.assertEqual(sum(p[1]==-57 for p in self.h.blocks()),25)
        self.assertEqual(len(self.h.blocks())-25,46)
        path=Path(__file__).resolve().parents[2]/'tests/building/fixtures/reference.json'
        self.assertEqual(json.loads(path.read_text()),self.h.document())
        self.assertTrue(self.check_world()['objective_verified'])
    def test_BM02_missing_required_block(self):
        self.good[(0,-60,0)]='minecraft:air';r=self.check_world()
        self.assertFalse(r['objective_verified']);self.assertEqual(r['missing_blocks'],1)
    def test_BM03_wrong_material(self):
        self.good[(0,-60,0)]='minecraft:stone';r=self.check_world()
        self.assertFalse(r['objective_verified']);self.assertEqual(r['incorrect_blocks'],1)
    def test_BM04_unknown_never_correct_or_missing(self):
        del self.good[(0,-60,0)];r=self.check_world()
        self.assertEqual(r['unknown_blocks'],1);self.assertEqual(r['missing_blocks'],0);self.assertFalse(r['objective_verified'])
    def test_BM05_entrance_obstruction(self):
        self.good[(2,-59,0)]='minecraft:cobblestone';r=self.check_world()
        self.assertEqual(r['verified_blocks'],71);self.assertFalse(r['entrance_clear']);self.assertFalse(r['objective_verified'])
    def test_BM06_roof_hole(self):
        self.good[(2,-57,2)]='minecraft:air';r=self.check_world()
        self.assertFalse(r['roof_complete']);self.assertFalse(r['objective_verified'])
    def test_BM07_hidden_third_height_interior_obstruction(self):
        self.good[(2,-58,2)]='minecraft:dirt';r=self.check_world()
        self.assertFalse(r['interior_clear']);self.assertFalse(r['objective_verified'])
    def test_BM08_leftover_scaffold_and_unknown_free_cell(self):
        for block in ('minecraft:dirt',None):
            with self.subTest(block=block):
                self.good[(-4,-60,2)]=block
                self.assertFalse(self.check_world()['objective_verified'])
    def test_BM09_native_reachability_not_implied_by_shell(self):
        self.native['interior_accessible']=False
        self.assertFalse(self.check_world()['objective_verified'])
    def test_BM10_player_safe_required(self):
        self.native['safe_player']=False
        self.assertFalse(self.check_world()['objective_verified'])
    def test_BM11_floor_damage(self):
        self.good[(2,-61,2)]='minecraft:air'
        self.assertFalse(self.check_world()['objective_verified'])
    def test_BM12_truncated_or_cancelled_or_lost_ack_does_not_certify(self):
        # Effects are judged independently of delivery/session/task status.
        for retained in (0,1,30,70):
            world={p:'minecraft:air' for p in self.h.workspace()};world.update({p:'minecraft:grass_block' for p in self.h.floors()})
            world.update(dict(list(self.h.blocks().items())[:retained]))
            self.assertFalse(self.check_world(world)['objective_verified'])
    def test_BM13_declarative_size_extension(self):
        self.assertEqual(len(House(width=3,depth=3,height=2).blocks()),23)
        self.assertEqual(len(House(width=7,depth=9,height=3).blocks()),145)
        with self.assertRaises(ValueError):House(width=4)
    def test_BM14_no_native_actor_or_standing_assumption(self):
        s={'alive':True,'in_world':True,'on_ground':True,'health':20,'actor_session':'a','dimension':'minecraft:overworld'}
        cells=sorted(self.h.interior()|{self.h.entrance,self.h.point(2,0,-1)})
        nav={'ready':True,'profile':'stepped_full_blocks_v1','actor_session':'a','dimension':'minecraft:overworld',
             'current_center_access':True,'on_fire':False,'nearby_hostiles':[],'current_cell':list(self.h.point(2,0,2)),
             'cells':[{'position':list(p),'hazards':[]} for p in cells],
             'edges':[[0,i] for i in range(1,len(cells))]}
        self.assertTrue(native_proof(s,nav,self.h,'a')['safe_player'])
        self.assertTrue(native_proof(s,nav,self.h,'a')['interior_accessible'])
        for key,value in [('actor_session','wrong'),('current_center_access',False),('dimension','minecraft:the_nether')]:
            with self.subTest(key=key):
                bad=copy.deepcopy(nav);bad[key]=value
                r=native_proof(s,bad,self.h,'a');self.assertFalse(r['safe_player']);self.assertFalse(r['interior_accessible'])
    def test_BM15_no_receipt_input_to_verifier(self):
        self.assertNotIn('receipts',verify.__code__.co_varnames)
        self.good.clear();self.assertFalse(self.check_world()['objective_verified'])

class BenchmarkProgram(unittest.TestCase):
    def test_BM16_versioned_program_full_preflight_and_exact_house_targets(self):
        registry=default_commands();source=fixture_program()
        path=Path(__file__).resolve().parents[2]/'tests/building/fixtures/build.bcl'
        self.assertEqual(path.read_text(),source)
        compiled=frames(source,registry);targets={};counts=0
        for part,program in compiled:
            self.assertLessEqual(len(program.operations),32)
            for op in program.operations:
                if op.opcode=='I4':
                    args=arguments(op,registry.resolve(op.namespace,op.opcode));p=tuple(args['position'])
                    self.assertNotIn(p,targets);targets[p]=args['block'];counts+=1
        self.assertEqual({p:b for p,b in targets.items() if b=='minecraft:cobblestone'},House().blocks())
        self.assertEqual(sum(b=='minecraft:dirt' for b in targets.values()),11)
    def test_BM17_late_invalid_frame_rejected_before_any_execution(self):
        with self.assertRaises(ValueError):frames(fixture_program()+'\n; @frame\nM999',default_commands())

class BenchmarkSnapshots(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.world=self.root/'saves'/'Blockwire Benchmark Superflat';self.world.mkdir(parents=True)
        (self.world/OWNER).write_text(json.dumps({'fixture':FIXTURE}));(self.world/'level.dat').write_bytes(b'fixture')
        self.baseline=self.root/'private/baseline';self.closed=lambda:None
    def test_BM18_snapshot_restore_identity_and_archive(self):
        m=capture(self.world,self.baseline,self.closed)
        (self.world/'level.dat').write_bytes(b'changed')
        restored=restore(self.baseline,self.world,self.root/'retained-ended',self.closed)
        self.assertEqual(restored['identity'],m['identity']);self.assertEqual((self.world/'level.dat').read_bytes(),b'fixture')
        self.assertEqual((self.root/'retained-ended/level.dat').read_bytes(),b'changed')
    def test_BM19_tamper_and_unowned_world_rejected(self):
        capture(self.world,self.baseline,self.closed)
        (self.baseline/'level.dat').write_bytes(b'tampered')
        with self.assertRaises(ValueError):validate(self.baseline)
        with self.assertRaises(ValueError):restore(self.baseline,self.world,self.root/'archive',self.closed)
    def test_BM20_running_world_never_restored(self):
        capture(self.world,self.baseline,self.closed)
        def running():raise ValueError('world open')
        with self.assertRaises(ValueError):restore(self.baseline,self.world,self.root/'archive',running)
        self.assertTrue(self.world.exists());self.assertFalse((self.root/'archive').exists())
    def test_BM21_unowned_destination_not_overwritten(self):
        capture(self.world,self.baseline,self.closed);(self.world/OWNER).write_text('{}')
        with self.assertRaises(ValueError):restore(self.baseline,self.world,self.root/'archive',self.closed)
    def test_BM26_overlapping_snapshot_paths_rejected(self):
        with self.assertRaises(ValueError):capture(self.world,self.world/'nested',self.closed)
        capture(self.world,self.baseline,self.closed)
        with self.assertRaises(ValueError):restore(self.baseline,self.world,self.world/'archive',self.closed)
    def test_BM22_symlinks_forbidden(self):
        (self.world/'link').symlink_to(self.world/'level.dat')
        with self.assertRaises(ValueError):capture(self.world,self.baseline,self.closed)

class BenchmarkRecovery(unittest.TestCase):
    def test_BM27_full_reference_reconstruction_lost_ack_no_replay(self):
        from blockwire.projects import ProjectJournal
        from test_projects import scene_fixture,IDENTITY
        h=House();plan={'site':list(h.origin),'dimension':'minecraft:overworld','sections':['shell'],
                       'blocks':[{'position':list(p),'block':b,'section':'shell'} for p,b in h.blocks().items()]}
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'project.sqlite'
            with ProjectJournal(path,IDENTITY,'benchmark','fixed goal',policy='blocks_v1') as p:
                p.bind(scene_fixture());p.revise(plan)
                p.intent('I4 Bminecraft:cobblestone P"[0,-60,0]"',9,'old',1)
            with ProjectJournal(path,IDENTITY,'benchmark','fixed goal',policy='blocks_v1') as p:
                self.assertEqual(len(p.p['plan']['blocks']),71);self.assertTrue(p.p['pending'])
                s=scene_fixture();s['actor_session']='new'
                with self.assertRaises(ValueError):p.bind(s)
                p.bind(s,allow_rebind=True);self.assertIsNone(p.p['pending'])
                self.assertEqual(p.p['counters']['operations'],1)
                self.assertEqual(p.p['counters']['placement_events'],0)
                self.assertTrue(any(e['kind']=='interrupted_intent_not_replayed' for e in p.p['history']))
                with self.assertRaises(ValueError):p.intent('V0',9,'old',1)
                self.assertEqual(p.p['status'],'OBJECTIVE_INCOMPLETE')

class BenchmarkNBT(unittest.TestCase):
    def test_BM23_truncation_and_decompression_bounds(self):
        for data in (b'',b'\x0a\x00\x00\x03\x00\x01x',b'\x0a\x00\x00\x07\x00\x01x\xff\xff\xff\xff\x00'):
            with self.assertRaises((ValueError,struct.error)):NBT(data).root()
        with self.assertRaises(ValueError):inflate(b'x',99)
    def test_BM24_missing_chunk_stays_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'region').mkdir()
            self.assertEqual(voxels(d,{(0,-60,0)}),{})
    def test_BM25_padded_palette_decoder_string_and_compound(self):
        # Build a bounded synthetic actual region, exercising binary parsing,
        # signed long words, negative section Y and the 26.3 string palette.
        import zlib
        def string(s):v=s.encode();return struct.pack('>H',len(v))+v
        def tag(kind,name,payload):return bytes([kind])+string(name)+payload
        for modern in (True,False):
            palette=bytes([8 if modern else 10])+struct.pack('>i',2)
            for name in ('minecraft:air','minecraft:cobblestone'):
                palette+=string(name) if modern else tag(8,'Name',string(name))+b'\0'
            states=tag(9,'palette',palette)+tag(12,'data',struct.pack('>i',256)+struct.pack('>q',17)+bytes(8*255))+b'\0'
            section=tag(1,'Y',struct.pack('>b',-4))+tag(10,'block_states',states)+b'\0'
            raw=b'\x0a\0\0'+tag(3,'xPos',bytes(4))+tag(3,'zPos',bytes(4))+tag(9,'sections',b'\x0a'+struct.pack('>i',1)+section)+b'\0'
            compressed=zlib.compress(raw);payload=struct.pack('>I',len(compressed)+1)+b'\x02'+compressed
            region=b'\0\0\x02\x01'+bytes(8192-4)+payload+bytes(4096-len(payload))
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)/'region';p.mkdir();(p/'r.0.0.mca').write_bytes(region)
                self.assertEqual(voxels(d,{(0,-64,0)})[(0,-64,0)],'minecraft:cobblestone')
                self.assertEqual(voxels(d,{(1,-64,0)})[(1,-64,0)],'minecraft:cobblestone')
                self.assertEqual(voxels(d,{(2,-64,0)})[(2,-64,0)],'minecraft:air')

if __name__=='__main__':unittest.main()
