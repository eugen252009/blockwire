"""Transactional modal interpreter and durable request deduplication; no Minecraft calls."""
from dataclasses import dataclass
import copy,hashlib,json,math
from .compiler import compile_bcl,arguments,Program,BCLError,Diagnostic
from .registry import VERSION,DEFAULT_PERMISSIONS
from ..agent import SessionStore

@dataclass(frozen=True)
class Modal:
    execution_mode: str = 'sync'
    coordinate_mode: str = 'absolute'
    movement_mode: str = 'normal'
    error_mode: str = 'stop'
    timeout_seconds: float = 30.
    def __post_init__(self):
        for key,values in [('execution_mode',('sync','async')),('coordinate_mode',('absolute','relative')),('movement_mode',('normal','fast','sneak')),('error_mode',('stop','continue'))]:
            if getattr(self,key) not in values:raise ValueError('Invalid typed modal enum')
        if type(self.timeout_seconds) not in (int,float) or not math.isfinite(self.timeout_seconds) or not .1<=self.timeout_seconds<=120:raise ValueError('Invalid typed modal timeout')
    def to_dict(self):return self.__dict__.copy()

@dataclass(frozen=True)
class Prepared:
    source: str
    program: Program
    contexts: tuple[Modal,...]
    request_id: int
    response: dict

class ModalSession:
    def __init__(self,registry,path,identity,actor_session,permissions=DEFAULT_PERMISSIONS):
        self.registry,self.permissions,self.actor_session=registry,permissions,actor_session
        self.store=SessionStore(path,identity);self.state=self.store.acquire()
        try:
            self.layout={s.namespace+':'+s.opcode:s.describe() for s in registry.settings.values()}
            if self.state.get('modal_version',VERSION)!=VERSION or self.state.get('modal_layout',self.layout)!=self.layout:
                raise ValueError('Incompatible persisted BCL modal schema')
            if self.state.get('actor_session',actor_session)!=actor_session:raise ValueError('Explicit new actor session requires a NEW BCL session ID')
            self.state.setdefault('modal',{self.key(s):s.default for s in registry.settings.values()})
            for setting in registry.settings.values():
                value=self.state['modal'].get(self.key(setting))
                if setting.values and value not in setting.values:raise ValueError('Corrupt persisted modal enum')
                if not setting.values and (type(value) not in (int,float) or not math.isfinite(value) or not .1<=value<=120):raise ValueError('Corrupt persisted modal number')
            self.state.setdefault('subscriptions',[]);self.state.setdefault('requests',{});self.state.setdefault('last_request_id',0)
            self.state.update(modal_version=VERSION,modal_layout=self.layout,actor_session=actor_session)
            # Queued/running requests cannot be reconstructed safely after process/connection loss.
            for record in self.state['requests'].values():
                if record['status'] in {'accepted','running'}:
                    record.update(status='interrupted',diagnostics=[{'code':'INTERRUPTED_SESSION','message':'Not replayed; inspect state before explicitly issuing new work.'}])
            self.store.save(self.state)
        except BaseException:self.store.release();raise
    @staticmethod
    def key(setting):return setting.name if setting.namespace=='core' else setting.namespace+':'+setting.name
    @property
    def modal(self):return Modal(**{k:self.state['modal'][k] for k in Modal.__dataclass_fields__})
    @property
    def subscriptions(self):return frozenset(self.state['subscriptions'])
    def prepare(self,source,request_id,*,reset=False,control=None,accepted_control=False):
        def fail(code,message):raise BCLError(Diagnostic(code,message,phase='session'))
        # Full static validation precedes every setting/subscription mutation.
        program=None if reset or control is not None else compile_bcl(source,self.registry,permissions=self.permissions)
        if type(request_id) is not int or not 1<=request_id<=9007199254740991:fail('INVALID_REQUEST_ID','Monotonically increasing positive safe integer required')
        digest=hashlib.sha256(('RESET' if reset else json.dumps(control,sort_keys=True) if control is not None else source).encode()).hexdigest();key=str(request_id)
        if key in self.state['requests']:
            record=self.state['requests'][key]
            if record['source_digest']!=digest:fail('REQUEST_CONFLICT','Request ID already used with different source')
            return None,{**copy.deepcopy(record),'deduplicated':True}
        if request_id<=self.state['last_request_id']:fail('STALE_REQUEST','Evicted/old request IDs are never executed again')
        staged=copy.deepcopy(self.state);outputs=[];operations=[];contexts=[]
        if reset:
            staged['modal']={self.key(s):s.default for s in self.registry.settings.values()};staged['subscriptions']=[]
        elif control is None:
            for op in program.operations:
                command=self.registry.resolve(op.namespace,op.opcode);values=arguments(op,command)
                if command.category=='setting':
                    setting=self.registry.settings[op.namespace,op.opcode];name=self.key(setting)
                    current=staged['modal'][name]
                    if 'value' not in values:
                        if not setting.cyclic:fail('MISSING_REQUIRED_ARGUMENT','Numeric setting requires a value or ?/status')
                        value=setting.values[(setting.values.index(current)+1)%len(setting.values)];operation='cycle'
                    elif values['value'] in {'?','status'}:value=current;operation='get'
                    else:value=values['value'];operation='set'
                    if operation!='get':staged['modal'][name]=value
                    outputs.append({'opcode':op.opcode,'setting':name,'operation':operation,'value':value})
                elif command.category=='event_control':
                    subs=set(staged['subscriptions']);event=values.get('event')
                    if op.opcode=='E0':subs.add(event)
                    elif op.opcode=='E1':subs.discard(event)
                    elif op.opcode=='E3':subs.clear()
                    if len(subs)>32:fail('PROGRAM_LIMIT','At most 32 subscriptions per session')
                    staged['subscriptions']=sorted(subs)
                    outputs.append({'opcode':op.opcode,'subscriptions':sorted(subs)})
                else:
                    operations.append(op);contexts.append(Modal(**{k:staged['modal'][k] for k in Modal.__dataclass_fields__}))
        response={'request_id':request_id,'source_digest':digest,'status':'accepted' if operations or accepted_control else 'completed',
                  'execution_mode':contexts[-1].execution_mode if contexts else staged['modal']['execution_mode'],
                  'modal':{k:staged['modal'][k] for k in Modal.__dataclass_fields__},'outputs':outputs}
        staged['requests'][key]=copy.deepcopy(response);staged['last_request_id']=request_id
        while len(staged['requests'])>128:del staged['requests'][next(iter(staged['requests']))]
        self.store.save(staged)  # Atomic SQLite commit BEFORE publishing state or accepting actions.
        self.state=staged
        prepared=Prepared(source,Program(VERSION,program.registry_digest,tuple(operations)),tuple(contexts),request_id,response) if operations else None
        return prepared,response
    def update(self,request_id,**values):
        staged=copy.deepcopy(self.state);record=staged['requests'].get(str(request_id))
        if record is not None:
            record.update(values);self.store.save(staged);self.state=staged
    def close(self):self.store.release()
