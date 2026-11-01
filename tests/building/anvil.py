"""Bounded read-only closed-save audit for TESTS, never an agent observation API.

No dependency on Minecraft or native placement reports. Only declared benchmark
voxels are queried. Missing/unreadable chunks remain unknown; no air fabrication.
"""
import gzip
import io
from pathlib import Path
import struct
import zlib

MAX_BYTES=16*1024*1024

class NBT:
    def __init__(self, data):
        if len(data)>MAX_BYTES:raise ValueError('NBT size bound')
        self.stream=io.BytesIO(data);self.nodes=0
    def read(self,n):
        if not 0<=n<=MAX_BYTES:raise ValueError('NBT length bound')
        data=self.stream.read(n)
        if len(data)!=n:raise ValueError('Truncated NBT')
        return data
    def unpack(self,fmt):return struct.unpack('>'+fmt,self.read(struct.calcsize('>'+fmt)))[0]
    def string(self):return self.read(self.unpack('H')).decode('utf-8')
    def payload(self,kind,depth=0):
        self.nodes+=1
        if depth>64 or self.nodes>1000000:raise ValueError('NBT complexity bound')
        if kind in {1,2,3,4,5,6}:return self.unpack({1:'b',2:'h',3:'i',4:'q',5:'f',6:'d'}[kind])
        if kind==8:return self.string()
        if kind in {7,9,11,12}:
            child=self.unpack('B') if kind==9 else {7:1,11:3,12:4}[kind]
            n=self.unpack('i')
            if not 0<=n<=1000000:raise ValueError('NBT array bound')
            return [self.payload(child,depth+1) for _ in range(n)]
        if kind==10:
            out={}
            while True:
                child=self.unpack('B')
                if child==0:return out
                name=self.string()
                if name in out:raise ValueError('Duplicate NBT key')
                out[name]=self.payload(child,depth+1)
        raise ValueError('Unsupported NBT type')
    def root(self):
        kind=self.unpack('B');self.string()
        result=self.payload(kind)
        if self.stream.read(1):raise ValueError('Trailing NBT data')
        return result

def inflate(data,kind):
    if kind not in (1,2,3):raise ValueError('Unsupported chunk compression')
    if kind==3:return data
    decoder=zlib.decompressobj(31 if kind==1 else 15)
    out=decoder.decompress(data,MAX_BYTES+1)
    if len(out)>MAX_BYTES or not decoder.eof or decoder.unconsumed_tail:raise ValueError('Decompression bound/truncation')
    return out

def region_directory(world):
    world=Path(world)
    choices=[world/'dimensions/minecraft/overworld/region',world/'region']
    existing=[p for p in choices if p.is_dir()]
    if len(existing)!=1:raise ValueError('Unambiguous overworld region directory required')
    return existing[0]

def chunk(region,cx,cz):
    path=region/f'r.{cx//32}.{cz//32}.mca'
    if not path.exists():return None
    if path.is_symlink():raise ValueError('Symlink region')
    with path.open('rb') as f:
        f.seek(4*((cx%32)+32*(cz%32)));entry=f.read(4)
        if len(entry)!=4:raise ValueError('Truncated region header')
        offset=int.from_bytes(entry[:3],'big');sectors=entry[3]
        if offset==0 and sectors==0:return None
        if offset<2 or sectors==0:raise ValueError('Invalid chunk allocation')
        f.seek(offset*4096);header=f.read(5)
        if len(header)!=5:raise ValueError('Truncated chunk header')
        size=int.from_bytes(header[:4],'big');compression=header[4]
        if not 1<size<=sectors*4096-4 or size>MAX_BYTES or compression&128:raise ValueError('Chunk length/external-storage bound')
        raw=f.read(size-1)
        if len(raw)!=size-1:raise ValueError('Truncated chunk data')
        result=NBT(inflate(raw,compression)).root()
    result=result.get('Level',result)
    if result.get('xPos')!=cx or result.get('zPos')!=cz:raise ValueError('Chunk coordinate mismatch')
    return result

def voxels(world,positions):
    positions=set(positions)
    if len(positions)>16384:raise ValueError('Bounded benchmark volume required')
    region=region_directory(world);cache={};result={}
    for x,y,z in sorted(positions):
        key=(x//16,z//16)
        if key not in cache:cache[key]=chunk(region,*key)
        value=cache[key]
        if value is None:continue
        section=next((s for s in value.get('sections',[]) if s['Y']==y//16),None)
        if section is None:continue
        states=section.get('block_states',{});palette=states.get('palette',[])
        if not palette:continue
        index=0
        if len(palette)>1:
            bits=max(4,(len(palette)-1).bit_length());per_long=64//bits
            i=(y%16)*256+(z%16)*16+x%16;data=states.get('data',[])
            if i//per_long>=len(data):continue
            index=((data[i//per_long]&((1<<64)-1))>>((i%per_long)*bits))&((1<<bits)-1)
        if index>=len(palette):raise ValueError('Palette index out of range')
        entry=palette[index]
        name=entry if isinstance(entry,str) else entry.get('Name')
        if not isinstance(name,str):raise ValueError('Malformed palette')
        result[(x,y,z)]=name.split('[',1)[0]  # 26.3 string palettes, legacy compound palettes
    return result
