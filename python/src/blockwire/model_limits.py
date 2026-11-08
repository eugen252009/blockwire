"""Persistent operational limits for explicitly verified subscription campaigns.

Not a financial/token ledger. This opt-in mode is the operator's bounded
subscription exception, not a waiver for metered providers or other campaigns.
Trusted host API: it is not a sandbox against arbitrary Python run by the owner.
"""
import dataclasses,hashlib,json,os,re,sqlite3,time
from uuid import uuid4
from contextlib import contextmanager
from pathlib import Path

class LimitExceeded(RuntimeError):
    @property
    def code(self):return str(self)
class RequestConflict(ValueError):pass

def ident(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,96}',value):raise ValueError('Explicit bounded identity required')
    return value

def integer(value,low,high,name):
    if type(value) is not int or not low<=value<=high:raise ValueError('Invalid '+name)
    return value

@dataclasses.dataclass(frozen=True)
class OperationalPolicy:
    campaign_id:str
    agents:tuple[str,...]
    provider:str='openai-codex'
    model:str='gpt-6-luna'
    duration_ms:int=1800000
    requests_per_agent:int=30
    total_requests:int=60
    operations_per_agent:int=300
    total_operations:int=600
    concurrent_requests:int=2
    request_timeout_ms:int=90000
    inference_ms_per_agent:int=1800000
    total_inference_ms:int=3600000
    def __post_init__(self):
        ident(self.campaign_id)
        if not isinstance(self.agents,tuple) or not 1<=len(self.agents)<=2 or len(set(self.agents))!=len(self.agents):raise ValueError('One/two independent configured agents required')
        for agent in self.agents:ident(agent)
        if self.provider!='openai-codex' or self.model!='gpt-6-luna':raise ValueError('This subscription qualification has no provider/model fallback')
        for name,maximum in [('duration_ms',1800000),('requests_per_agent',30),('total_requests',60),('operations_per_agent',300),('total_operations',600),('concurrent_requests',2),('request_timeout_ms',180000),('inference_ms_per_agent',5400000),('total_inference_ms',10800000)]:integer(getattr(self,name),1,maximum,name)

@dataclasses.dataclass(frozen=True)
class ExperimentSeriesPolicy(OperationalPolicy):
    """Explicit three-experiment umbrella; individual agent limits stay unchanged.

    Five distinct scopes: one single-player and two pairs. At most two requests
    may be active; a fresh per-experiment world must not reset the shared ledger.
    The trusted supervisor also enforces each experiment's 30-minute deadline.
    """
    total_requests:int=150
    total_operations:int=1500
    duration_ms:int=7200000
    total_inference_ms:int=9000000
    def __post_init__(self):
        if not isinstance(self.agents,tuple) or not 1<=len(self.agents)<=5 or len(set(self.agents))!=len(self.agents):raise ValueError('At most five explicit experiment-agent scopes')
        for agent in self.agents:ident(agent)
        integer(self.total_requests,1,150,'series request cap');integer(self.total_operations,1,1500,'series operation cap');integer(self.duration_ms,1,7200000,'series duration');integer(self.total_inference_ms,1,9000000,'series inference time')
        # Keep every existing per-agent/provider/timeout/concurrency restriction.
        values=dataclasses.asdict(self);values.update(agents=self.agents[:2],total_requests=min(self.total_requests,60),total_operations=min(self.total_operations,600),duration_ms=min(self.duration_ms,1800000),total_inference_ms=min(self.total_inference_ms,10800000))
        OperationalPolicy(**values)

@dataclasses.dataclass(frozen=True)
class TwoHourPolicy(OperationalPolicy):
    """Explicit two-hour play allocation, plus bounded preparation/finalization.

    Opt-in subscription profile only. Legacy policies and persisted configuration
    layouts are unchanged. The host starts a separate 7200s gameplay deadline
    after admission, inside this 9000s immutable outer envelope.
    """
    duration_ms:int=9000000
    requests_per_agent:int=720
    total_requests:int=1440
    operations_per_agent:int=9000
    total_operations:int=18000
    inference_ms_per_agent:int=7200000
    total_inference_ms:int=14400000
    def __post_init__(self):
        integer(self.request_timeout_ms,1,90000,'request timeout')
        for name,maximum in [('duration_ms',9000000),('requests_per_agent',720),('total_requests',1440),('operations_per_agent',9000),('total_operations',18000),('inference_ms_per_agent',7200000),('total_inference_ms',14400000)]:integer(getattr(self,name),1,maximum,name)
        values=dataclasses.asdict(self)
        values.update(duration_ms=min(self.duration_ms,1800000),requests_per_agent=min(self.requests_per_agent,30),total_requests=min(self.total_requests,60),operations_per_agent=min(self.operations_per_agent,300),total_operations=min(self.total_operations,600),inference_ms_per_agent=min(self.inference_ms_per_agent,5400000),total_inference_ms=min(self.total_inference_ms,10800000))
        OperationalPolicy(**values)

class ModelLimits:
    def __init__(self,directory,policy,*,subscription_proof,clock_ms=None):
        if not isinstance(policy,OperationalPolicy):raise ValueError('Typed operator policy required')
        expected={'provider':policy.provider,'model':policy.model,'oauth':True,'subscription':True,'api':'openai-codex-responses','base_url':'https://chatgpt.com/backend-api'}
        if not isinstance(subscription_proof,dict) or any(subscription_proof.get(k)!=v for k,v in expected.items()):raise ValueError('Verified existing subscription route required; no metered fallback')
        self.policy=policy;self.clock=clock_ms or (lambda:time.time_ns()//1000000);self.directory=Path(directory);self.directory.mkdir(parents=True,mode=0o700,exist_ok=True)
        if self.directory.is_symlink() or self.directory.stat().st_uid!=os.getuid() or self.directory.stat().st_mode&0o077:raise ValueError('Private nonsymlink ledger directory required')
        self.path=self.directory/'model-limits.sqlite';fd=os.open(self.path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600);os.close(fd)
        if self.path.stat().st_uid!=os.getuid() or self.path.stat().st_mode&0o077:raise ValueError('Private owned ledger required')
        configuration={'policy':dataclasses.asdict(policy),'subscription_route':expected}
        # Distinguish the opt-in audit allowance even if an operator lowers every
        # numeric quota to legacy values. Never widen a legacy persisted store.
        if isinstance(policy,TwoHourPolicy):configuration['profile']='two_hour_v1'
        config=json.dumps(configuration,sort_keys=True)
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS campaign(id INTEGER PRIMARY KEY CHECK(id=1),config TEXT,state TEXT,started INTEGER,deadline INTEGER,last_time INTEGER);
            CREATE TABLE IF NOT EXISTS agents(id TEXT PRIMARY KEY,halted INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,agent TEXT NOT NULL,digest TEXT NOT NULL,state TEXT NOT NULL,reserved_ms INTEGER NOT NULL,spent_ms INTEGER,usage TEXT,reason TEXT,created INTEGER NOT NULL,ended INTEGER);
            CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY,agent TEXT NOT NULL,digest TEXT NOT NULL,amount INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,at INTEGER,kind TEXT,agent TEXT,request_id TEXT,reason TEXT);''')
            # executescript ends a transaction: re-enter before immutable initialization.
            db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT config FROM campaign WHERE id=1').fetchone()
            if old and old[0]!=config:raise RequestConflict('Persisted campaign configuration mismatch; never reset a budget')
            if not old:
                now=self.clock();db.execute('INSERT INTO campaign VALUES(1,?,?,?,?,?)',(config,'CREATED',None,None,now))
                db.executemany('INSERT INTO agents(id) VALUES(?)',[(a,) for a in policy.agents])
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=2.)
        try:
            maximum=(16*1024*1024)//db.execute('PRAGMA page_size').fetchone()[0]
            if db.execute(f'PRAGMA max_page_count={maximum}').fetchone()[0]>maximum:raise LimitExceeded('ledger_capacity')
            if db.execute('PRAGMA journal_mode').fetchone()[0]!='delete':raise ValueError('Bounded rollback-journal database required')
            db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE');yield db;db.commit()
        except BaseException:db.rollback();raise
        finally:db.close()
    def _agent(self,db,agent):
        ident(agent);row=db.execute('SELECT halted FROM agents WHERE id=?',(agent,)).fetchone()
        if row is None:raise ValueError('Agent not configured in this campaign')
        return bool(row[0])
    def _running(self,db,agent=None):
        state,deadline,last=db.execute('SELECT state,deadline,last_time FROM campaign WHERE id=1').fetchone();now=self.clock()
        if now<last:raise LimitExceeded('clock_regressed; no new dispatch')
        if state!='RUNNING' or now>=deadline:raise LimitExceeded('campaign_stopped_or_deadline')
        if agent is not None and self._agent(db,agent):raise LimitExceeded('agent_halted_or_uncertain')
        db.execute('UPDATE campaign SET last_time=? WHERE id=1',(now,));return now,deadline
    @property
    def audit_capacity(self):
        # 1440 requests need 4320 reserve/dispatch/terminal records, plus bounded
        # denials/stop. Never raise the legacy/experiment store's 2000-row limit.
        return 8192 if isinstance(self.policy,TwoHourPolicy) else 2000
    def _event(self,db,kind,agent,request_id,reason=''):
        if db.execute('SELECT count(*) FROM events').fetchone()[0]>=self.audit_capacity:raise LimitExceeded('event_capacity')
        db.execute('INSERT INTO events(at,kind,agent,request_id,reason) VALUES(?,?,?,?,?)',(self.clock(),kind,agent,request_id,reason[:256]))
    def start(self):
        with self.db() as db:
            state,deadline=db.execute('SELECT state,deadline FROM campaign WHERE id=1').fetchone()
            if state=='RUNNING':return deadline
            if state!='CREATED':raise LimitExceeded('Explicit stopped campaign cannot restart')
            now=self.clock();deadline=now+self.policy.duration_ms;db.execute("UPDATE campaign SET state='RUNNING',started=?,deadline=?,last_time=? WHERE id=1",(now,deadline,now));return deadline
    def check(self,agent):
        with self.db() as db:self._running(db,agent)
    def reserve(self,agent,request_id,context_digest,*,timeout_ms=None):
        ident(request_id)
        if not isinstance(context_digest,str) or not re.fullmatch('[0-9a-f]{64}',context_digest):raise ValueError('Canonical context SHA-256 required')
        timeout=self.policy.request_timeout_ms if timeout_ms is None else integer(timeout_ms,1,self.policy.request_timeout_ms,'request timeout')
        rejected=None
        with self.db() as db:
            self._agent(db,agent)
            old=db.execute('SELECT agent,digest,state FROM requests WHERE id=?',(request_id,)).fetchone()
            if old:
                if old[0]!=agent or old[1]!=context_digest:raise RequestConflict('Conflicting stable request identifier')
                return {'request_id':request_id,'state':old[2],'new':False,'dispatch_allowed':False}
            now,deadline=self._running(db,agent)
            total=db.execute('SELECT count(*),coalesce(sum(coalesce(spent_ms,reserved_ms)),0) FROM requests').fetchone();own=db.execute('SELECT count(*),coalesce(sum(coalesce(spent_ms,reserved_ms)),0) FROM requests WHERE agent=?',(agent,)).fetchone();active=db.execute("SELECT count(*) FROM requests WHERE state IN ('RESERVED','DISPATCHED','UNCERTAIN')").fetchone()[0]
            if timeout>deadline-now:rejected='request_exceeds_remaining_runtime'
            elif total[0]>=self.policy.total_requests:rejected='global_request_budget'
            elif own[0]>=self.policy.requests_per_agent:rejected='agent_request_budget'
            elif active>=self.policy.concurrent_requests:rejected='model_concurrency_budget'
            elif total[1]+timeout>self.policy.total_inference_ms:rejected='global_inference_time_budget'
            elif own[1]+timeout>self.policy.inference_ms_per_agent:rejected='agent_inference_time_budget'
            if rejected:self._event(db,'REJECTED',agent,request_id,rejected)
            else:
                db.execute('INSERT INTO requests(id,agent,digest,state,reserved_ms,created) VALUES(?,?,?,?,?,?)',(request_id,agent,context_digest,'RESERVED',timeout,now));self._event(db,'RESERVED',agent,request_id)
        if rejected:raise LimitExceeded(rejected)
        return {'request_id':request_id,'state':'RESERVED','new':True,'dispatch_allowed':True,'timeout_ms':timeout}
    def dispatch(self,agent,request_id):
        with self.db() as db:
            now,deadline=self._running(db,agent);row=db.execute('SELECT agent,state,reserved_ms FROM requests WHERE id=?',(request_id,)).fetchone()
            if not row or row[0]!=agent or row[1]!='RESERVED':raise RequestConflict('A request can dispatch exactly once for its bound agent')
            if now+row[2]>deadline:raise LimitExceeded('request_exceeds_remaining_runtime')
            db.execute("UPDATE requests SET state='DISPATCHED' WHERE id=?",(request_id,));self._event(db,'DISPATCHED',agent,request_id)
    def finish(self,agent,request_id,*,elapsed_ms,usage=None,state='COMPLETED',reason=''):
        integer(elapsed_ms,0,180000,'elapsed inference time')
        if state not in {'COMPLETED','PROVIDER_ERROR','UNCERTAIN','CANCELLED_BEFORE_DISPATCH'}:raise ValueError('Invalid terminal model state')
        encoded=json.dumps(usage,allow_nan=False,sort_keys=True)
        if len(encoded)>4096:raise ValueError('Bounded optional provider usage telemetry required')
        with self.db() as db:
            self._agent(db,agent);row=db.execute('SELECT agent,state,reserved_ms,spent_ms,usage,reason FROM requests WHERE id=?',(request_id,)).fetchone()
            if not row or row[0]!=agent:raise RequestConflict('Not this agent request')
            if row[1] in {'COMPLETED','PROVIDER_ERROR','UNCERTAIN','CANCELLED_BEFORE_DISPATCH'}:
                if row[1]==state and row[4]==encoded and row[3]==(row[2] if state=='UNCERTAIN' else elapsed_ms) and row[5]==reason[:256]:return False
                raise RequestConflict('Terminal model outcome cannot be rewritten')
            if (state=='CANCELLED_BEFORE_DISPATCH')!=(row[1]=='RESERVED'):raise RequestConflict('Incorrect dispatch/cancel lifecycle')
            if state!='CANCELLED_BEFORE_DISPATCH' and row[1]!='DISPATCHED':raise RequestConflict('Never reconcile an undispatched provider call')
            if elapsed_ms>row[2]:state='UNCERTAIN';reason='inference_timeout_bound_exceeded'
            spent=row[2] if state=='UNCERTAIN' else elapsed_ms
            db.execute('UPDATE requests SET state=?,spent_ms=?,usage=?,reason=?,ended=? WHERE id=?',(state,spent,encoded,reason[:256],self.clock(),request_id))
            if state in {'UNCERTAIN','PROVIDER_ERROR'}:db.execute('UPDATE agents SET halted=1 WHERE id=?',(agent,))
            self._event(db,state,agent,request_id,reason);return True
    def admit_operations(self,agent,request_id,source,count):
        ident(request_id);integer(count,1,32,'BCL frame operations');digest=hashlib.sha256(source.encode()).hexdigest()
        with self.db() as db:
            self._running(db,agent);old=db.execute('SELECT agent,digest,amount FROM operations WHERE id=?',(request_id,)).fetchone()
            if old:
                if old!=(agent,digest,count):raise RequestConflict('Conflicting BCL admission identifier')
                return False
            total=db.execute('SELECT coalesce(sum(amount),0) FROM operations').fetchone()[0];own=db.execute('SELECT coalesce(sum(amount),0) FROM operations WHERE agent=?',(agent,)).fetchone()[0]
            if total+count>self.policy.total_operations or own+count>self.policy.operations_per_agent:raise LimitExceeded('BCL operation budget')
            db.execute('INSERT INTO operations VALUES(?,?,?,?)',(request_id,agent,digest,count));return True
    def recover_interrupted(self):
        """Explicit recovery, never replay/refund. Uncertain slots remain charged."""
        with self.db() as db:
            rows=db.execute("SELECT id,agent,reserved_ms FROM requests WHERE state IN ('RESERVED','DISPATCHED')").fetchall()
            for rid,agent,ms in rows:
                db.execute("UPDATE requests SET state='UNCERTAIN',spent_ms=?,reason='host_interrupted' WHERE id=?",(ms,rid));db.execute('UPDATE agents SET halted=1 WHERE id=?',(agent,));self._event(db,'UNCERTAIN',agent,rid,'host_interrupted')
            return len(rows)
    def stop(self,reason):
        with self.db() as db:
            db.execute("UPDATE campaign SET state='STOPPED' WHERE id=1")
            # Budget/audit exhaustion must never revoke emergency stop authority.
            if db.execute('SELECT count(*) FROM events').fetchone()[0]<self.audit_capacity:self._event(db,'STOPPED',None,None,reason)
    def snapshot(self):
        with self.db() as db:
            state,started,deadline=db.execute('SELECT state,started,deadline FROM campaign WHERE id=1').fetchone();agents={}
            for agent in self.policy.agents:
                reqs=db.execute('SELECT state,reserved_ms,spent_ms,usage FROM requests WHERE agent=?',(agent,)).fetchall();ops=db.execute('SELECT coalesce(sum(amount),0) FROM operations WHERE agent=?',(agent,)).fetchone()[0]
                agents[agent]={'requests':len(reqs),'operations':ops,'inference_ms_charged':sum(r[2] if r[2] is not None else r[1] for r in reqs),'states':{s:sum(r[0]==s for r in reqs) for s in {r[0] for r in reqs}},'halted':self._agent(db,agent)}
            return {'campaign':self.policy.campaign_id,'mode':'subscription_operational_not_financial','state':state,'started_ms':started,'deadline_ms':deadline,'agents':agents,'requests':sum(r['requests'] for r in agents.values()),'operations':sum(r['operations'] for r in agents.values()),'token_accounting':'optional telemetry, not a hard token/billing guarantee'}

class LimitedDecider:
    """Single admission boundary for trusted HTTP/command/mailbox/SDK adapters.

    The campaign supplies only this bound object to its autonomous runtime. All
    exceptions after dispatch conservatively halt that agent; no automatic retry.
    Legacy direct adapters are not globally intercepted or sandboxed by this API.
    """
    def __init__(self,manager,agent,decider):
        if not isinstance(manager,ModelLimits) or agent not in manager.policy.agents or not callable(getattr(decider,'decide',None)):raise ValueError('Configured agent and trusted model adapter required')
        timeout=getattr(decider,'timeout',None)
        if type(timeout) not in (int,float) or not .001<=timeout<=manager.policy.request_timeout_ms/1000:raise ValueError('Underlying adapter must enforce the configured request timeout')
        self.manager,self.agent,self.decider=manager,agent,decider;self.last_request_id=None
    def decide(self,context):
        body=json.dumps(context,allow_nan=False,sort_keys=True).encode()
        if len(body)>128*1024:raise ValueError('Bounded inference context required')
        request_id=self.agent+'-'+uuid4().hex;self.last_request_id=request_id
        reservation=self.manager.reserve(self.agent,request_id,hashlib.sha256(body).hexdigest())
        if not reservation['dispatch_allowed']:raise RequestConflict('No dispatch authority for duplicate request')
        self.manager.dispatch(self.agent,request_id);started=time.monotonic()
        try:
            answer=self.decider.decide(context)
            if not isinstance(answer,dict) or len(json.dumps(answer,allow_nan=False).encode())>16384:raise ValueError('Malformed or oversized provider decision')
            elapsed=int((time.monotonic()-started)*1000)
            if elapsed>reservation['timeout_ms']:raise TimeoutError('Inference exceeded reserved timeout')
            self.manager.finish(self.agent,request_id,elapsed_ms=elapsed,usage=getattr(self.decider,'last_usage',None))
            self.manager.check(self.agent)
            return answer
        except BaseException as error:
            # Even malformed/partial output may have consumed remote inference.
            elapsed=min(180000,int((time.monotonic()-started)*1000))
            with self.manager.db() as db:state=db.execute('SELECT state FROM requests WHERE id=?',(request_id,)).fetchone()[0]
            if state=='DISPATCHED':self.manager.finish(self.agent,request_id,elapsed_ms=elapsed,state='UNCERTAIN',reason=type(error).__name__)
            raise
