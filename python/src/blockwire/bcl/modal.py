"""Transactional modal interpreter, persistent S1 homes and request deduplication."""
from dataclasses import dataclass
import copy,hashlib,json,math
from .compiler import compile_bcl,arguments,Program,BCLError,Diagnostic
from .registry import VERSION,DEFAULT_PERMISSIONS
from ..agent import SessionStore

MODAL_SEMANTICS='s1-home-v1'
_HOME_TERMINAL=frozenset({'failed','cancelled','interrupted'})

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
class CoordinateContext:
    mode: str = 'absolute'
    home_id: int | None = None
    home: tuple[float,float,float] | None = None
    voxel_origin: tuple[int,int,int] | None = None
    dimension: str | None = None
    status: str = 'absolute'
    def __post_init__(self):
        if self.mode not in {'absolute','relative'}:raise ValueError('Invalid coordinate context mode')
        if self.mode=='absolute':
            if any(v is not None for v in (self.home_id,self.home,self.voxel_origin,self.dimension)) or self.status!='absolute':raise ValueError('Invalid absolute coordinate context')
            return
        if type(self.home_id)is not int or self.home_id<1 or self.status not in {'pending','ready'}:raise ValueError('Invalid relative coordinate context')
        if self.status=='pending':
            if any(v is not None for v in (self.home,self.voxel_origin,self.dimension)):raise ValueError('Pending home cannot contain coordinates')
            return
        if (not isinstance(self.home,tuple) or len(self.home)!=3 or not isinstance(self.voxel_origin,tuple) or len(self.voxel_origin)!=3
                or any(type(v)not in (int,float) or not math.isfinite(v) for v in self.home)
                or any(type(v)is not int for v in self.voxel_origin)
                or not isinstance(self.dimension,str) or not 1<=len(self.dimension)<=128):
            raise ValueError('Invalid captured coordinate home')
    def to_dict(self):
        return {'mode':self.mode,'status':self.status,'home_id':self.home_id,
                'home_position':list(self.home) if self.home is not None else None,
                'voxel_origin':list(self.voxel_origin) if self.voxel_origin is not None else None,
                'dimension':self.dimension}

@dataclass(frozen=True)
class Prepared:
    source: str
    program: Program
    contexts: tuple[Modal,...]
    coordinates: tuple[CoordinateContext,...]
    request_id: int
    response: dict

class ModalSession:
    def __init__(self,registry,path,identity,actor_session,permissions=DEFAULT_PERMISSIONS):
        self.registry,self.permissions,self.actor_session=registry,permissions,actor_session
        self.store=SessionStore(path,identity);self.state=self.store.acquire()
        try:
            self.layout={s.namespace+':'+s.opcode:s.describe() for s in registry.settings.values()}
            existing=any(key in self.state for key in ('modal_version','modal_layout','modal','coordinate'))
            if existing and self.state.get('modal_semantics')!=MODAL_SEMANTICS:
                raise ValueError('Incompatible persisted BCL/1 S1 coordinate semantics; use a new session ID')
            if self.state.get('modal_version',VERSION)!=VERSION or self.state.get('modal_layout',self.layout)!=self.layout:
                raise ValueError('Incompatible persisted BCL modal schema')
            if self.state.get('actor_session',actor_session)!=actor_session:raise ValueError('Explicit new actor session requires a NEW BCL session ID')
            self.state.setdefault('modal',{self.key(s):s.default for s in registry.settings.values()})
            for setting in registry.settings.values():
                value=self.state['modal'].get(self.key(setting))
                if setting.values and value not in setting.values:raise ValueError('Corrupt persisted modal enum')
                if not setting.values and (type(value) not in (int,float) or not math.isfinite(value) or not .1<=value<=120):raise ValueError('Corrupt persisted modal number')
            self.state.setdefault('subscriptions',[]);self.state.setdefault('requests',{});self.state.setdefault('last_request_id',0)
            self.state.setdefault('coordinate',{'next_home_id':1,'current_home_id':None,'homes':{}})
            self._validate_coordinate_state(self.state)
            self.state.update(modal_version=VERSION,modal_layout=self.layout,modal_semantics=MODAL_SEMANTICS,actor_session=actor_session)
            # Queued/running requests cannot be reconstructed safely after process/connection loss.
            interrupted=set()
            for key,record in self.state['requests'].items():
                if record['status'] in {'accepted','running'}:
                    interrupted.add(int(key));record.update(status='interrupted',diagnostics=[{'code':'INTERRUPTED_SESSION','message':'Not replayed; inspect state before explicitly issuing new work.'}])
            if interrupted:self._fail_homes_in(self.state,interrupted,'interrupted')
            self.store.save(self.state)
        except BaseException:self.store.release();raise
    @staticmethod
    def key(setting):return setting.name if setting.namespace=='core' else setting.namespace+':'+setting.name
    @staticmethod
    def _public(record):return {k:copy.deepcopy(v) for k,v in record.items() if not k.startswith('_')}
    @staticmethod
    def _normalize_home(position,dimension):
        if (not isinstance(position,(list,tuple)) or len(position)!=3
                or any(type(v)not in (int,float) or not math.isfinite(v) for v in position)):
            raise ValueError('Fresh finite three-axis player position required for S1 homing')
        home=tuple(float(v) for v in position)
        if abs(home[0])>29999984 or not -2048<=home[1]<=2048 or abs(home[2])>29999984:
            raise ValueError('Observed S1 home is outside supported world bounds')
        if not isinstance(dimension,str) or not 1<=len(dimension)<=128:raise ValueError('Fresh dimension identity required for S1 homing')
        return home,tuple(math.floor(v) for v in home)
    def _validate_coordinate_state(self,state):
        coordinate=state.get('coordinate')
        if not isinstance(coordinate,dict) or set(coordinate)!={'next_home_id','current_home_id','homes'}:raise ValueError('Corrupt persisted coordinate context')
        if type(coordinate['next_home_id'])is not int or not 1<=coordinate['next_home_id']<=9007199254740991 or type(coordinate['homes'])is not dict or len(coordinate['homes'])>256:raise ValueError('Corrupt persisted coordinate home ledger')
        current=coordinate['current_home_id'];homes=coordinate['homes']
        if current is not None and (type(current)is not int or str(current) not in homes):raise ValueError('Corrupt persisted active coordinate home')
        for key,record in homes.items():
            if (not isinstance(key,str) or not key.isdecimal() or not isinstance(record,dict)
                    or record.get('home_id')!=int(key) or record.get('status') not in {'pending','ready',*_HOME_TERMINAL}
                    or type(record.get('request_id'))is not int or record.get('previous_mode') not in {'absolute','relative'}
                    or (record.get('previous_home_id') is not None and type(record.get('previous_home_id'))is not int)
                    or record.get('actor_session')!=self.actor_session or record.get('world_id')!=self.store.identity['world_id']
                    or record.get('player_id')!=self.store.identity['player_id']):
                raise ValueError('Corrupt persisted coordinate home record')
            identifier=int(key);previous=record.get('previous_home_id')
            if identifier>=coordinate['next_home_id'] or (record['previous_mode']=='absolute')!=(previous is None):
                raise ValueError('Corrupt persisted coordinate home chain')
            if previous is not None and (previous>=identifier or str(previous) not in homes):raise ValueError('Corrupt persisted coordinate home chain')
            if record['status']=='pending' and any(record.get(name) is not None for name in ('home','voxel_origin','dimension')):
                raise ValueError('Corrupt persisted pending coordinate home')
            if record['status']=='ready':
                _,voxel=self._normalize_home(record.get('home'),record.get('dimension'))
                if record.get('voxel_origin')!=list(voxel):raise ValueError('Corrupt persisted coordinate voxel origin')
        mode=state['modal']['coordinate_mode']
        if mode=='absolute' and current is not None:raise ValueError('Absolute mode cannot retain an active S1 home')
        if mode=='relative' and (current is None or homes[str(current)]['status'] not in {'pending','ready'}):
            raise ValueError('Relative mode lacks a persisted S1 home')
    @property
    def modal(self):return Modal(**{k:self.state['modal'][k] for k in Modal.__dataclass_fields__})
    @property
    def subscriptions(self):return frozenset(self.state['subscriptions'])
    def _context(self,state,*,mode=None,home_id=None):
        mode=state['modal']['coordinate_mode'] if mode is None else mode
        if mode=='absolute':return CoordinateContext()
        home_id=state['coordinate']['current_home_id'] if home_id is None else home_id
        record=state['coordinate']['homes'].get(str(home_id))
        if record is None or record['status'] not in {'pending','ready'}:raise ValueError('Relative mode lacks an available S1 home')
        if record['status']=='pending':return CoordinateContext('relative',home_id,status='pending')
        home,voxel=self._normalize_home(record['home'],record['dimension'])
        return CoordinateContext('relative',home_id,home,voxel,record['dimension'],'ready')
    @property
    def coordinate_context(self):return self._context(self.state)
    def _modal_from(self,state):return Modal(**{k:state['modal'][k] for k in Modal.__dataclass_fields__})
    def _protected_homes(self,state):
        homes=state['coordinate']['homes'];protected=set()
        current=state['coordinate']['current_home_id']
        if current is not None:protected.add(current)
        for record in state['requests'].values():
            if record.get('status') in {'accepted','running'}:protected.update(record.get('_coordinate_home_ids',[]))
        protected.update(r['home_id'] for r in homes.values() if r['status']=='pending')
        queue=list(protected)
        while queue:
            record=homes.get(str(queue.pop()))
            previous=record.get('previous_home_id') if record else None
            if previous is not None and previous not in protected:protected.add(previous);queue.append(previous)
        return protected
    def _prune_homes(self,state):
        homes=state['coordinate']['homes'];protected=self._protected_homes(state)
        for key in list(homes):
            if int(key) not in protected and homes[key]['status']!='pending':
                removed=int(key);homes.pop(key)
                for record in homes.values():
                    if record.get('previous_home_id')==removed:record.update(previous_mode='absolute',previous_home_id=None)
            if len(homes)<128:break
        if len(homes)>=128:raise BCLError(Diagnostic('PROGRAM_LIMIT','Coordinate home history is still in use; finish queued work or start a new session.',phase='session'))
    def _allocate_home(self,state,request_id):
        self._prune_homes(state)
        coordinate=state['coordinate'];identifier=coordinate['next_home_id']
        if identifier>=9007199254740991:raise BCLError(Diagnostic('PROGRAM_LIMIT','Coordinate home revision bound exhausted; start a new session.',phase='session'))
        coordinate['next_home_id']+=1
        previous_mode=state['modal']['coordinate_mode'];previous=coordinate['current_home_id'] if previous_mode=='relative' else None
        coordinate['homes'][str(identifier)]={'home_id':identifier,'request_id':request_id,'status':'pending','home':None,'dimension':None,
            'previous_mode':previous_mode,'previous_home_id':previous,'actor_session':self.actor_session,
            'world_id':self.store.identity['world_id'],'player_id':self.store.identity['player_id']}
        coordinate['current_home_id']=identifier
        return identifier
    def requires_runtime(self,program):
        mode=self.state['modal']['coordinate_mode']
        for op in program.operations:
            command=self.registry.resolve(op.namespace,op.opcode)
            if command.category=='skill':return True
            if (op.namespace,op.opcode)==('core','S1'):
                values=arguments(op,command);value=values.get('value')
                if value in {'?','status'}:continue
                target=('relative' if mode=='absolute' else 'absolute') if value is None else value
                if target=='relative':return True
                mode=target
        return False
    def prepare(self,source,request_id,*,reset=False,control=None,accepted_control=False):
        def fail(code,message):raise BCLError(Diagnostic(code,message,phase='session'))
        # Full static validation precedes every setting/subscription mutation.
        program=None if reset or control is not None else compile_bcl(source,self.registry,permissions=self.permissions)
        if type(request_id) is not int or not 1<=request_id<=9007199254740991:fail('INVALID_REQUEST_ID','Monotonically increasing positive safe integer required')
        digest=hashlib.sha256(('RESET' if reset else json.dumps(control,sort_keys=True) if control is not None else source).encode()).hexdigest();key=str(request_id)
        if key in self.state['requests']:
            record=self.state['requests'][key]
            if record['source_digest']!=digest:fail('REQUEST_CONFLICT','Request ID already used with different source')
            return None,{**self._public(record),'modal':self.modal.to_dict(),'coordinate_context':self.coordinate_context.to_dict(),'deduplicated':True}
        if request_id<=self.state['last_request_id']:fail('STALE_REQUEST','Evicted/old request IDs are never executed again')
        staged=copy.deepcopy(self.state);outputs=[];operations=[];contexts=[];coordinates=[]
        if reset:
            staged['modal']={self.key(s):s.default for s in self.registry.settings.values()};staged['subscriptions']=[]
            staged['coordinate']={'next_home_id':staged['coordinate']['next_home_id'],'current_home_id':None,'homes':{}}
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
                    home_id=None
                    if operation!='get':
                        if (op.namespace,op.opcode)==('core','S1'):
                            if value=='relative':
                                home_id=self._allocate_home(staged,request_id)
                            else:staged['coordinate']['current_home_id']=None
                        staged['modal'][name]=value
                    output={'opcode':op.opcode,'setting':name,'operation':operation,'value':value}
                    if (op.namespace,op.opcode)==('core','S1'):
                        coordinate=self._context(staged)
                        output['coordinate_context']=coordinate.to_dict()
                        if home_id is not None:
                            output.update(homing='pending',home_id=home_id)
                            operations.append(op);contexts.append(self._modal_from(staged));coordinates.append(coordinate)
                    outputs.append(output)
                elif command.category=='event_control':
                    subs=set(staged['subscriptions']);event=values.get('event')
                    if op.opcode=='E0':subs.add(event)
                    elif op.opcode=='E1':subs.discard(event)
                    elif op.opcode=='E3':subs.clear()
                    if len(subs)>32:fail('PROGRAM_LIMIT','At most 32 subscriptions per session')
                    staged['subscriptions']=sorted(subs)
                    outputs.append({'opcode':op.opcode,'subscriptions':sorted(subs)})
                else:
                    operations.append(op);contexts.append(self._modal_from(staged));coordinates.append(self._context(staged))
        coordinate=self._context(staged)
        response={'request_id':request_id,'source_digest':digest,'status':'accepted' if operations or accepted_control else 'completed',
                  'execution_mode':contexts[-1].execution_mode if contexts else staged['modal']['execution_mode'],
                  'modal':{k:staged['modal'][k] for k in Modal.__dataclass_fields__},'coordinate_context':coordinate.to_dict(),'outputs':outputs}
        home_ids=sorted({c.home_id for c in coordinates if c.home_id is not None})
        staged['requests'][key]={**copy.deepcopy(response),'_coordinate_home_ids':home_ids};staged['last_request_id']=request_id
        while len(staged['requests'])>128:del staged['requests'][next(iter(staged['requests']))]
        self.store.save(staged)  # Atomic SQLite commit BEFORE publishing state or accepting actions.
        self.state=staged
        prepared=Prepared(source,Program(VERSION,program.registry_digest,tuple(operations)),tuple(contexts),tuple(coordinates),request_id,response) if operations else None
        return prepared,response
    def _replace_context(self,state,home_id,value):
        for record in state['requests'].values():
            if record.get('coordinate_context',{}).get('home_id')==home_id:record['coordinate_context']=copy.deepcopy(value)
            for output in record.get('outputs',[]):
                if output.get('coordinate_context',{}).get('home_id')==home_id:
                    output['coordinate_context']=copy.deepcopy(value)
                    if output.get('home_id')==home_id:output['homing']='captured' if value.get('status')=='ready' else value.get('status')
    def capture_home(self,request_id,home_id,position,dimension):
        home,voxel=self._normalize_home(position,dimension);staged=copy.deepcopy(self.state)
        record=staged['coordinate']['homes'].get(str(home_id))
        if record is None or record['request_id']!=request_id:raise ValueError('S1 home does not belong to this request')
        if record['status']=='ready':return self._context(staged,mode='relative',home_id=home_id)
        if record['status']!='pending':raise ValueError('S1 home is no longer executable')
        record.update(status='ready',home=list(home),dimension=dimension,voxel_origin=list(voxel))
        context=CoordinateContext('relative',home_id,home,voxel,dimension,'ready')
        self._replace_context(staged,home_id,context.to_dict())
        self.store.save(staged)  # The home is durable before any following coordinate-bearing operation.
        self.state=staged;return context
    def resolve_home(self,home_id):
        return self._context(self.state,mode='relative',home_id=home_id)
    @staticmethod
    def _fallback(state,record):
        mode,home_id=record['previous_mode'],record['previous_home_id']
        homes=state['coordinate']['homes'];seen=set()
        while mode=='relative':
            if home_id in seen:return 'absolute',None
            seen.add(home_id);previous=homes.get(str(home_id))
            if previous is None:return 'absolute',None
            if previous['status'] in {'pending','ready'}:return 'relative',home_id
            mode,home_id=previous['previous_mode'],previous['previous_home_id']
        return 'absolute',None
    def _fail_homes_in(self,state,request_ids,status):
        changed=[]
        for record in state['coordinate']['homes'].values():
            if record['request_id'] in request_ids and record['status']=='pending':record['status']=status;changed.append(record)
        current=state['coordinate']['current_home_id']
        if state['modal']['coordinate_mode']=='relative' and any(r['home_id']==current for r in changed):
            mode,home_id=self._fallback(state,next(r for r in changed if r['home_id']==current))
            state['modal']['coordinate_mode']=mode;state['coordinate']['current_home_id']=home_id
        for record in changed:
            self._replace_context(state,record['home_id'],{'mode':'relative','status':status,'home_id':record['home_id'],
                'home_position':None,'voxel_origin':None,'dimension':None})
        return bool(changed)
    def fail_homes(self,request_id,status):
        status=status if status in _HOME_TERMINAL else 'failed';staged=copy.deepcopy(self.state)
        changed=self._fail_homes_in(staged,{request_id},status)
        if changed:self.store.save(staged);self.state=staged
        return changed
    def update(self,request_id,**values):
        staged=copy.deepcopy(self.state);record=staged['requests'].get(str(request_id))
        if record is not None:
            record.update(values);self.store.save(staged);self.state=staged
    def close(self):self.store.release()
