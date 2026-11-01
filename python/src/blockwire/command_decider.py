"""Explicit trusted host-command JSON model adapter; NEVER a Minecraft/game RPC.

No shell or discovery. The operator supplies a reviewed argv for an installed
model client. This is trusted host execution, NOT a sandbox. Model output is
strict data; the Minecraft runtime still enforces its independent skill allowlist.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from .llm import SYSTEM, strict_json


class CommandJSONDecider:
    def __init__(self, argv, *, timeout=150., audit_directory=None, system_prompt=SYSTEM):
        if (not isinstance(argv,list) or not 1<=len(argv)<=64 or
            any(not isinstance(a,str) or not a or len(a)>8192 or '\0' in a for a in argv)):
            raise ValueError('Explicit bounded trusted model argv required')
        if type(timeout) not in (int,float) or not .1<=timeout<=180:
            raise ValueError('Bounded model command timeout required')
        if not isinstance(system_prompt,str) or not 1<=len(system_prompt)<=8192:raise ValueError('Bounded explicit system prompt required')
        self.system=system_prompt
        self.argv,self.timeout=argv[:],timeout
        self.audit=Path(audit_directory) if audit_directory else None
        if self.audit:
            self.audit.mkdir(mode=0o700,parents=True,exist_ok=True)
            if self.audit.is_symlink() or self.audit.stat().st_mode & 0o077:raise ValueError('Private model audit directory required')
        self.sequence=0

    def decide(self, context):
        data=json.dumps({'system':self.system,'context':context},allow_nan=False).encode()
        if len(data)>128*1024:raise ValueError('Model context bound exceeded')
        self.sequence+=1
        def record(name,body):
            if self.audit:
                fd=os.open(self.audit/f'{self.sequence:03d}-{name}.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                with os.fdopen(fd,'wb') as f:f.write(body)
        record('request',data)
        # Do not pass native connection paths/credentials through environment variables.
        env={k:v for k,v in os.environ.items() if not k.startswith(('BLOCKWIRE_','BLOCK_BRIDGE_'))}
        with tempfile.TemporaryDirectory(prefix='blockwire-model-') as cwd, tempfile.TemporaryFile() as output:
            run=subprocess.run(self.argv,input=data,stdout=output,stderr=subprocess.DEVNULL,
                               cwd=cwd,env=env,timeout=self.timeout,check=False,shell=False)
            if run.returncode:
                record('failure',json.dumps({'kind':'nonzero_exit','returncode':run.returncode}).encode())
                raise RuntimeError('model_command_failed')
            output.seek(0);body=output.read(16385)
        if len(body)>16384:raise ValueError('Model decision output bound exceeded')
        record('reply',body)
        parsed=strict_json(body)
        if not isinstance(parsed,dict):raise ValueError('Model must return one JSON object')
        return parsed
