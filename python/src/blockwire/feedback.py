"""Private host-side feature requests and input admission audit, never a planner.

Feedback is untrusted data awaiting an operator. It cannot grant capabilities,
change code, run commands, extend budgets, or control Minecraft.
"""
import argparse,dataclasses,hashlib,json,os,re,sqlite3,time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from pydantic import BaseModel,ConfigDict,Field
from typing import Literal

class FeatureRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,allow_inf_nan=False)
    category:Literal['feature_request','capability_gap','failure_report']='feature_request'
    title:str=Field(min_length=1,max_length=120)
    description:str=Field(min_length=1,max_length=2048)
    requested_capability:str=Field(default='',max_length=128)
    evidence_request_id:int|None=Field(default=None,ge=1,le=9007199254740991)

LLM_TOOLS=frozenset({'compile_bcl','discover_bcl_commands','describe_bcl_command','execute_bcl',
    'describe_surroundings','estimate_distance','show_inventory','list_skills',
    'request_feature','feedback_status','skill_status','cancel_skill','stop_inputs'})

@dataclasses.dataclass(frozen=True)
class InputPolicy:
    max_frame_operations:int=32
    max_session_operations:int=300
    max_actor_operations:int=1000
    max_feedback_per_session:int=20
    allowed_opcodes:frozenset[str]|None=None
    allowed_tools:frozenset[str]|None=LLM_TOOLS
    def __post_init__(self):
        for name,lo,hi in [('max_frame_operations',1,32),('max_session_operations',1,10000),('max_actor_operations',1,100000),('max_feedback_per_session',1,100)]:
            value=getattr(self,name)
            if type(value) is not int or not lo<=value<=hi:raise ValueError('Invalid bounded input policy: '+name)
        for name in ['allowed_opcodes','allowed_tools']:
            values=getattr(self,name)
            if values is not None and (not isinstance(values,frozenset) or len(values)>128 or any(not isinstance(v,str) or not 1<=len(v)<=128 for v in values)):raise ValueError('Explicit immutable allowlist required')

    def describe(self):
        return {field.name:(sorted(value) if isinstance(value,frozenset) else value) for field in dataclasses.fields(self) for value in [getattr(self,field.name)]}

class InputDenied(ValueError):pass

def owner_key(identity):
    if not isinstance(identity,dict) or set(identity)!={'agent_id','world_id','player_id'} or any(not isinstance(v,str) or not 1<=len(v)<=128 for v in identity.values()):raise ValueError('Bound agent/world/player identity required')
    return json.dumps(identity,sort_keys=True,separators=(',',':'))
def identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',value):raise ValueError('Bounded feedback identifier required')
    return value

class FeedbackStore:
    MAX_AUDIT=10000
    MAX_FEEDBACK=1000
    def __init__(self,directory,policy=None):
        self.policy=policy or InputPolicy()
        if not isinstance(self.policy,InputPolicy):raise ValueError('Typed operator input policy required')
        self.directory=Path(directory);self.directory.mkdir(parents=True,mode=0o700,exist_ok=True)
        if self.directory.is_symlink() or self.directory.stat().st_mode&0o077:raise ValueError('Private nonsymlink feedback directory required')
        self.path=self.directory/'feedback.sqlite'
        fd=os.open(self.path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600);os.close(fd)
        if self.path.stat().st_mode&0o077 or self.path.stat().st_uid!=os.getuid():raise ValueError('Private owned feedback database required')
        with self.db() as db:
            if db.execute('PRAGMA journal_mode').fetchone()[0]!='delete':raise InputDenied('Private bounded rollback-journal database required')
            db.executescript('''CREATE TABLE IF NOT EXISTS feedback(
              ticket TEXT PRIMARY KEY,owner TEXT NOT NULL,session TEXT NOT NULL,feedback_id TEXT NOT NULL,
              digest TEXT NOT NULL,body TEXT NOT NULL,actor TEXT NOT NULL,status TEXT NOT NULL,created REAL NOT NULL,
              review TEXT NOT NULL DEFAULT '',UNIQUE(owner,session,feedback_id));
              CREATE TABLE IF NOT EXISTS inputs(id INTEGER PRIMARY KEY,created REAL,owner TEXT,session TEXT,
              kind TEXT,request_id TEXT,payload TEXT,status TEXT,detail TEXT);
              CREATE TABLE IF NOT EXISTS reservations(owner TEXT,session TEXT,request_id INTEGER,digest TEXT,
              operations INTEGER,PRIMARY KEY(owner,session,request_id));''')
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=1.)
        try:
            page_size=db.execute('PRAGMA page_size').fetchone()[0];maximum=(32*1024*1024)//page_size
            if db.execute(f'PRAGMA max_page_count={maximum}').fetchone()[0]>maximum:raise InputDenied('feedback_database_oversize')
            db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE');yield db;db.commit()
        except BaseException:db.rollback();raise
        finally:db.close()
    def audit(self,identity,session,kind,request_id,payload,status='received',detail=''):
        owner=owner_key(identity);body=json.dumps(payload,allow_nan=False,sort_keys=True)
        if len(body.encode())>20000:body=json.dumps({'oversize_sha256':hashlib.sha256(body.encode()).hexdigest(),'bytes':len(body.encode()),'body_omitted':True})
        with self.db() as db:
            if db.execute('SELECT count(*) FROM inputs').fetchone()[0]>=self.MAX_AUDIT:raise InputDenied('input_audit_capacity; operator review required')
            cursor=db.execute('INSERT INTO inputs(created,owner,session,kind,request_id,payload,status,detail) VALUES(?,?,?,?,?,?,?,?)',(time.time(),owner,session,kind,str(request_id),body,status,detail[:512]));return cursor.lastrowid
    def outcome(self,record,status,detail=''):
        with self.db() as db:db.execute('UPDATE inputs SET status=?,detail=? WHERE id=?',(status,detail[:512],record))
    def admit_bcl(self,identity,session,request_id,source,program):
        """Durably reserve admitted operations, not receipts or gameplay outcomes.

        The aggregate bound spans every alias in this per-instance store.
        No client-accessible reset or refund can erase consumed authority.
        """
        owner=owner_key(identity)
        if type(request_id) is not int or not 1<=request_id<=9007199254740991:raise InputDenied('invalid_request_id')
        if not isinstance(session,str) or not 1<=len(session)<=128:raise InputDenied('invalid_session')
        digest=hashlib.sha256(source.encode()).hexdigest();count=len(program.operations);p=self.policy
        opcodes={o.namespace+':'+o.opcode for o in program.operations}
        if count>p.max_frame_operations or (p.allowed_opcodes is not None and not opcodes<=p.allowed_opcodes):raise InputDenied('input_operation_policy')
        with self.db() as db:
            prior=db.execute('SELECT digest FROM reservations WHERE owner=? AND session=? AND request_id=?',(owner,session,request_id)).fetchone()
            if prior:
                if prior[0]!=digest:raise InputDenied('input_request_conflict')
                return False
            used=db.execute('SELECT coalesce(sum(operations),0) FROM reservations WHERE owner=? AND session=?',(owner,session)).fetchone()[0]
            total=db.execute('SELECT coalesce(sum(operations),0) FROM reservations').fetchone()[0]
            if used+count>p.max_session_operations or total+count>p.max_actor_operations:raise InputDenied('input_operation_budget')
            db.execute('INSERT INTO reservations VALUES(?,?,?,?,?)',(owner,session,request_id,digest,count));return True
    def submit(self,identity,session,feedback_id,proposal,actor_session):
        owner=owner_key(identity);identifier(feedback_id);proposal=FeatureRequest.model_validate(proposal);body=json.dumps(proposal.model_dump(),sort_keys=True,allow_nan=False);digest=hashlib.sha256(body.encode()).hexdigest()
        if not isinstance(session,str) or not 1<=len(session)<=128 or not isinstance(actor_session,str) or not 1<=len(actor_session)<=128:raise ValueError('Explicit bounded session and actor required')
        with self.db() as db:
            old=db.execute('SELECT ticket,digest,status FROM feedback WHERE owner=? AND session=? AND feedback_id=?',(owner,session,feedback_id)).fetchone()
            if old:
                if old[1]!=digest:raise InputDenied('feedback_id_conflict')
                return {'ticket':old[0],'status':old[2],'deduplicated':True,'capabilities_changed':False}
            count=db.execute('SELECT count(*) FROM feedback WHERE owner=? AND session=?',(owner,session)).fetchone()[0]
            if count>=self.policy.max_feedback_per_session or db.execute('SELECT count(*) FROM feedback').fetchone()[0]>=self.MAX_FEEDBACK:raise InputDenied('feedback_capacity; operator review required')
            ticket=uuid4().hex;db.execute('INSERT INTO feedback(ticket,owner,session,feedback_id,digest,body,actor,status,created) VALUES(?,?,?,?,?,?,?,?,?)',(ticket,owner,session,feedback_id,digest,body,actor_session,'pending_review',time.time()))
            return {'ticket':ticket,'status':'pending_review','deduplicated':False,'capabilities_changed':False}
    def status(self,identity,session,feedback_id):
        owner=owner_key(identity);identifier(feedback_id)
        with self.db() as db:row=db.execute('SELECT ticket,status,body,review FROM feedback WHERE owner=? AND session=? AND feedback_id=?',(owner,session,feedback_id)).fetchone()
        if row is None:raise ValueError('feedback_not_found_in_own_session')
        return {'ticket':row[0],'status':row[1],'request':json.loads(row[2]),'operator_note':row[3],'capabilities_changed':False}
    def inputs(self,limit=50):
        """Operator-only bounded inspection; not exposed through MCP/gateway."""
        if type(limit) is not int or not 1<=limit<=100:raise ValueError('Audit inspection limit 1..100 required')
        with self.db() as db:rows=db.execute('SELECT id,created,owner,session,kind,request_id,payload,status,detail FROM inputs ORDER BY id DESC LIMIT ?',(limit,)).fetchall()
        return [{'id':r[0],'created':r[1],'identity':json.loads(r[2]),'session':r[3],'kind':r[4],'request_id':r[5],'input':json.loads(r[6]),'status':r[7],'detail':r[8]} for r in rows]
    def pending(self):
        with self.db() as db:rows=db.execute("SELECT ticket,owner,session,body,created FROM feedback WHERE status='pending_review' ORDER BY created LIMIT 100").fetchall()
        return [{'ticket':r[0],'identity':json.loads(r[1]),'session':r[2],'request':json.loads(r[3]),'created':r[4]} for r in rows]
    def review(self,ticket,status,note=''):
        identifier(ticket)
        if status not in {'planned','declined'} or not isinstance(note,str) or len(note)>2048:raise ValueError('Operator review only: planned/declined with bounded note')
        with self.db() as db:
            changed=db.execute('UPDATE feedback SET status=?,review=? WHERE ticket=?',(status,note,ticket)).rowcount
            if not changed:raise ValueError('Unknown feedback ticket')

def main():
    parser=argparse.ArgumentParser(description='Operator-only private feedback review; NEVER auto-installs or grants features')
    parser.add_argument('--directory',required=True,type=Path);parser.add_argument('--inputs',action='store_true');parser.add_argument('--limit',type=int,default=50);parser.add_argument('--ticket');parser.add_argument('--review',choices=['planned','declined']);parser.add_argument('--note',default='');a=parser.parse_args();store=FeedbackStore(a.directory)
    if a.review:
        if not a.ticket:parser.error('--ticket required for review')
        store.review(a.ticket,a.review,a.note);print(json.dumps({'reviewed':a.ticket,'status':a.review,'capabilities_changed':False}))
    else:print(json.dumps(store.inputs(a.limit) if a.inputs else store.pending(),indent=2))
if __name__=='__main__':main()
