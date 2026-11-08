"""Guarded host-side campaign building blocks. No planner, opcode or transport.

A model's optional BCL field is not a BCL program until it contains commands.
No-command decisions remain observations/feedback/finish proposals, never gameplay
success. An extended campaign is forbidden until independently verified gates pass.
"""
import asyncio,dataclasses,hashlib,json,os,struct,zipfile
from pathlib import Path
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
from .feedback import FeatureRequest
from .bcl import compile_bcl,DEFAULT_PERMISSIONS
from .bcl.compiler import BCLError,Program
from .llm import strict_json

class CampaignDecision(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,allow_inf_nan=False)
    source:str=Field(default='',max_length=16384)
    note:str=Field(default='',max_length=2048)
    memory:dict=Field(default_factory=dict)
    feedback:FeatureRequest|None=None
    chat:str=Field(default='',max_length=256)
    finish:bool=False
    wait_seconds:int=Field(default=0,ge=0,le=30)

@dataclasses.dataclass(frozen=True)
class PreparedDecision:
    decision:CampaignDecision
    program:Program|None
    kind:Literal['commands','finish_unverified','feedback_only','observation_only']
    @property
    def operation_count(self):return len(self.program.operations) if self.program else 0

def prepare_decision(raw,registry,*,permissions=DEFAULT_PERMISSIONS,max_operations=32):
    """Validate the COMPLETE decision before feedback/chat or scheduling effects.

    Catch exactly EMPTY_PROGRAM; malformed headers/opcodes/parameters still fail.
    The BCL compiler/gateway deliberately continue rejecting empty BCL frames.
    """
    if type(max_operations) is not int or not 1<=max_operations<=32:raise ValueError('Bounded operation limit required')
    if isinstance(raw,(str,bytes)):
        if len(raw)>16384:raise ValueError('Model response bound')
        raw=strict_json(raw)
    decision=CampaignDecision.model_validate(raw)
    if len(json.dumps(decision.memory,allow_nan=False).encode())>8192:raise ValueError('Model memory bound')
    # Validate optional chat statically without touching a native backend.
    if decision.chat:
        from .client import Player
        class NoEffects:
            def call(self,*args,**kwargs):return {}
        Player(NoEffects()).chat(decision.chat,actor_session='static-validation-only')
    try:program=compile_bcl(decision.source,registry,permissions=permissions)
    except BCLError as error:
        if error.diagnostic.code!='EMPTY_PROGRAM':raise
        program=None
    if program is not None and len(program.operations)>max_operations:raise ValueError('Frame operation budget')
    kind='commands' if program else 'finish_unverified' if decision.finish else 'feedback_only' if decision.feedback else 'observation_only'
    return PreparedDecision(decision,program,kind)

class NoCommandBudget:
    def __init__(self,maximum=3):
        if type(maximum) is not int or not 1<=maximum<=30:raise ValueError('Bounded idle decision budget required')
        self.maximum=maximum;self.consecutive=0
    def accept(self,prepared):
        if prepared.program:self.consecutive=0
        else:self.consecutive+=1
        return prepared.decision.finish or self.consecutive>=self.maximum

class UnknownNoRetry(RuntimeError):pass

async def dispatch_decision(prepared,client,*,feedback_id,check,chat=None):
    """Use an already-bound SDK lease once. Never create/reconnect a connection.

    check is the trusted host deadline/cancel/identity fence. Pure no-command
    decisions cannot acquire an actor lease or submit an empty BCL frame.
    Unknown receipt outcomes end this execution scope; caller must not retry.
    """
    check();decision=prepared.decision;result={'kind':prepared.kind,'operations':prepared.operation_count,
        'gameplay_verified':False,'finish_proposed':decision.finish,'bcl_submitted':False}
    if decision.chat and chat is None:raise ValueError('Chat not explicitly enabled by host')
    cancellation_confirmed=False
    try:
        if decision.feedback:
            check();result['feedback']=await client.request_feature(feedback_id,decision.feedback.model_dump())
            if result['feedback'].get('status')!='recorded':raise ValueError('Feedback rejected; no capability workaround')
        if decision.chat:
            check();result['chat']=await chat(decision.chat)
        if prepared.program is not None:
            check();result['bcl_submitted']=True;response=await client.send(decision.source)
            if response.get('status')=='accepted':
                identifier=response['task_id']
                try:response=await client.wait(identifier)
                except asyncio.CancelledError:
                    # Cleanup only the known owned task on the SAME still-bound lease.
                    # No replacement connection or action resubmission is permitted.
                    try:
                        await client.cancel(identifier)
                        await asyncio.wait_for(client.wait(identifier),5.)
                        cancellation_confirmed=True
                    except Exception as error:raise UnknownNoRetry('UNKNOWN_NO_RETRY: cancellation unconfirmed') from error
                    raise
            diagnostics=response.get('diagnostics',[])+response.get('result',{}).get('diagnostics',[])
            if any(d.get('code') in {'transport.disconnected','invariant.violation','UNKNOWN_NO_RETRY'} for d in diagnostics):raise UnknownNoRetry('UNKNOWN_NO_RETRY: terminal execution uncertainty')
            result['bcl_response']=response
            # Program verification is distinct from the external Survival objective.
            result['program_verified']=response.get('result',{}).get('program_verified') is True
    except asyncio.CancelledError as error:
        if cancellation_confirmed:raise
        raise UnknownNoRetry('UNKNOWN_NO_RETRY: interrupted in-flight submission') from error
    except (ConnectionError,TimeoutError) as error:
        raise UnknownNoRetry('UNKNOWN_NO_RETRY: receipt/transport uncertain') from error
    return result

# Values may only be supplied by trusted qualification infrastructure, never a model.
REQUIRED_GATES=frozenset({'empty_bcl','normal_shutdown','cancellation_input_release','tls_gateway',
    'world_persistence','memory_persistence','replay_finalization','bcl_regression',
    'actor_isolation','unknown_no_retry','resource_limits','current_concurrency',
    'model_token_cost_limits'})
def campaign_blockers(checks):
    """Missing, partial, stale or unverified is NOT PASS. Process exit is no gate."""
    return sorted(name for name in REQUIRED_GATES if checks.get(name)!='PASS')

def require_campaign_ready(checks):
    blocked=campaign_blockers(checks)
    if blocked:raise RuntimeError('CAMPAIGN_BLOCKED: '+', '.join(blocked))

FINALIZATION_PROOFS=frozenset({'decisions_stopped','scheduling_stopped','tasks_terminal',
    'owned_inputs_released','memory_durable','world_saved','replay_finalized',
    'journals_flushed','gateway_closed','processes_gone','artifacts_hashed'})
TRANSITIONS={'CREATED':{'PREPARING','BLOCKED'},'PREPARING':{'RUNNING','STOPPING','BLOCKED'},
    'RUNNING':{'STOPPING'},'STOPPING':{'FINALIZING'},'FINALIZING':{'COMPLETED','FAILED','BLOCKED'}}
class SessionLifecycle:
    """Trusted-host lifecycle; COMPLETED means verified finalization, not a won goal."""
    def __init__(self,path,identity):
        self.path=Path(path)
        if self.path.exists():raise ValueError('Existing lifecycle requires explicit reconciliation; never auto-resume')
        self.path.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
        if self.path.parent.is_symlink() or self.path.parent.stat().st_mode&0o077:raise ValueError('Private lifecycle directory required')
        self.value={'identity':identity,'state':'CREATED','history':['CREATED'],'unknown':False,'goal_verified':False}
        self._save()
    def _save(self):
        body=json.dumps(self.value,allow_nan=False,sort_keys=True).encode();temp=self.path.with_name(self.path.name+'.pending')
        fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            with os.fdopen(fd,'wb') as f:f.write(body);f.flush();os.fsync(f.fileno())
            os.replace(temp,self.path)
            fd=os.open(self.path.parent,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
        finally:
            if temp.exists():temp.unlink()
    def save_memory(self,memory):
        encoded=json.dumps(memory,allow_nan=False)
        if not isinstance(memory,dict) or len(encoded.encode())>8192:raise ValueError('Bounded JSON agent memory required')
        self.value['memory']=json.loads(encoded);self._save()
    def transition(self,target,*,proofs=None,unknown=False):
        current=self.value['state']
        if target==current:
            if unknown and not self.value['unknown']:
                if current in {'COMPLETED','FAILED','BLOCKED'}:raise ValueError('Terminal state requires explicit late-incident reconciliation')
                self.value['unknown']=True;self._save();return True
            return False  # Idempotent metadata; never gameplay cleanup.
        if target not in TRANSITIONS.get(current,set()):raise ValueError('Invalid lifecycle transition')
        uncertain=self.value['unknown'] or unknown
        if target=='COMPLETED' and (uncertain or proofs is None or any(proofs.get(k) is not True for k in FINALIZATION_PROOFS)):raise ValueError('Independent finalization proofs required; unknown is not completion')
        self.value.update(state=target,unknown=uncertain);self.value['history'].append(target)
        if proofs is not None:self.value['proofs']=dict(proofs)
        self._save();return True


def verify_replay(path,*,max_bytes=2*1024**3,max_duration_ms=8*3600*1000):
    """Closed finalized ZIP + CRC/full packet framing. NOT viewer playback proof."""
    path=Path(path)
    if path.is_symlink() or path.suffix!='.mcpr' or not path.is_file() or not 0<path.stat().st_size<=max_bytes:raise ValueError('Finalized bounded nonsymlink .mcpr required')
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or len(names)>4096 or any(n.startswith('/') or '..' in Path(n).parts for n in names):raise ValueError('Unsafe replay members')
        if sum(i.file_size for i in z.infolist())>max_bytes:raise ValueError('Expanded replay bound')
        if z.testzip() is not None:raise ValueError('Replay CRC failed')
        if not {'recording.tmcpr','metaData.json'}<=set(names):raise ValueError('Replay packet/metadata missing')
        metadata=strict_json(z.read('metaData.json'));last=-1;count=0
        with z.open('recording.tmcpr') as f:
            while True:
                header=f.read(8)
                if not header:break
                if len(header)!=8:raise ValueError('Truncated replay packet header')
                stamp,size=struct.unpack('>ii',header)
                if stamp<last or stamp>max_duration_ms or not 0<size<=8*1024*1024 or len(f.read(size))!=size:raise ValueError('Invalid replay packet framing')
                last=stamp;count+=1
        if count==0 or not isinstance(metadata,dict):raise ValueError('Replay is not recorded gameplay')
    with path.open('rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
    return {'sha256':digest,'bytes':path.stat().st_size,'packets':count,'duration_ms':last,'integrity':'PASS','viewer_playback':'NOT_RUN'}
