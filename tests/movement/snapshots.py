"""Closed explicitly owned movement-benchmark saves; never touch arbitrary worlds."""
import hashlib,json,shutil
from pathlib import Path

OWNER='.blockwire-motion-benchmark.json'
FIXTURE='blockwire-native-motion-v1'
REQUESTED_NAME='Blockwire Native Motion Benchmark'
NAME='Blockwire Native Motion Benchmar'  # Native 26.3 name/save-folder limit.
DIRECTORY=NAME

def tree(root):
    root=Path(root);result={}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():raise ValueError('Symlink in save tree')
        if path.is_file() and path.name!='session.lock':result[path.relative_to(root).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    if not result:raise ValueError('Empty snapshot')
    return result

def identity(files):return hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def owned(root):
    root=Path(root)
    if root.is_symlink() or json.loads((root/OWNER).read_text())!={'fixture':FIXTURE}:raise ValueError('Not an owned movement world')

def capture(world,target,require_closed):
    require_closed();owned(world);world,target=Path(world),Path(target)
    if target.exists() or world.resolve()==target.resolve() or world.resolve() in target.resolve().parents or target.resolve() in world.resolve().parents:raise ValueError('New disjoint snapshot required')
    files=tree(world);target.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(world,target);require_closed()
    if tree(target)!=files:raise ValueError('Snapshot changed during copy')
    manifest={'fixture':FIXTURE,'identity':identity(files),'files':files,'session_lock_excluded':True}
    target.with_name(target.name+'.manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');return manifest

def validate(snapshot):
    snapshot=Path(snapshot);owned(snapshot);manifest=json.loads(snapshot.with_name(snapshot.name+'.manifest.json').read_text());actual=tree(snapshot)
    if manifest['fixture']!=FIXTURE or manifest['files']!=actual or manifest['identity']!=identity(actual):raise ValueError('Snapshot identity mismatch')
    return manifest

def restore(snapshot,destination,archive,require_closed):
    require_closed();manifest=validate(snapshot);snapshot,destination,archive=map(Path,(snapshot,destination,archive))
    if destination.name!=DIRECTORY or destination.is_symlink() or archive.exists():raise ValueError('Exact safe movement destination required')
    paths=[p.resolve() for p in (snapshot,destination,archive)]
    if any(a==b or a in b.parents or b in a.parents for i,a in enumerate(paths) for b in paths[i+1:]):raise ValueError('Overlapping paths')
    if destination.exists():owned(destination);archive.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(destination),str(archive))
    shutil.copytree(snapshot,destination);require_closed()
    if tree(destination)!=manifest['files']:raise ValueError('Restoration not byte-identical')
    return manifest
