"""Atomic benchmark evidence, never truncating a previously completed record."""
import json
import os
from pathlib import Path
import uuid

def write_json(path,value):
    path=Path(path);temporary=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.partial')
    # Failed partial files deliberately remain for diagnosis. Never overwrite
    # the last complete record on disk-full/short-write/rename failure.
    with temporary.open('x',encoding='utf-8') as stream:
        os.chmod(temporary,0o600)
        json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')
        stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)
