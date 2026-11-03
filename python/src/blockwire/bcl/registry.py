"""BCL/1 declarative aliases. Skill parameter contracts remain authoritative."""
from dataclasses import dataclass
import re
from typing import Annotated, Literal, get_args, get_origin
from pydantic import TypeAdapter,Field
from ..skills import default_registry

VERSION='BCL/1'
DEFAULT_PERMISSIONS=frozenset({'observe','movement','crafting','inventory','mining','combat','settings','events'})

@dataclass(frozen=True)
class Parameter:
    key: str
    name: str
    kind: str
    adapter: object
    default_kind: str = 'required'
    default: object = None
    enum: tuple = ()
    def describe(self):
        return {'key':self.key,'name':self.name,'type':self.kind,'default_kind':self.default_kind,
                'default':self.default,'enum':list(self.enum),'schema':self.adapter.json_schema()}

@dataclass(frozen=True)
class Command:
    namespace: str
    opcode: str
    name: str
    description: str
    parameters: tuple[Parameter,...]
    skill: str | None
    permissions: frozenset[str]
    available: bool = True
    preconditions: tuple[str,...] = ('authorized actor/session','fresh native observations','skill preconditions')
    language: str = VERSION
    category: str = 'skill'
    coordinate_parameters: tuple[tuple[str,str],...] = ()
    def describe(self):
        return {'namespace':self.namespace,'opcode':self.opcode,'command':self.name,'language':self.language,
                'description':self.description,'category':self.category,'direction':'server_to_client' if self.category=='event_out' else 'client_to_server','signature':' '.join([self.opcode]+[p.key for p in self.parameters]),
                'parameters':[p.describe() for p in self.parameters],'coordinate_parameters':[{'parameter':name,'kind':kind} for name,kind in self.coordinate_parameters],
                'skill':self.skill,'available':self.available,
                'permissions':sorted(self.permissions),'preconditions':list(self.preconditions),
                'return_type':'verified SkillResult / fresh observation',
                'errors':['UNKNOWN_COMMAND','UNKNOWN_NAMESPACE','UNKNOWN_PARAMETER','INVALID_ARGUMENT','INVALID_ENUM_VALUE',
                          'MISSING_REQUIRED_ARGUMENT','DUPLICATE_ARGUMENT','INVALID_STRING','PROGRAM_LIMIT','EMPTY_PROGRAM',
                          'PERMISSION_DENIED','UNSUPPORTED_CAPABILITY','UNREACHABLE_TARGET','EXECUTION_TIMEOUT',
                          'EXECUTION_CANCELLED','POSTCONDITION_FAILED','ACTOR_MISMATCH','INTERRUPTED_SESSION',
                          'COORDINATE_HOME_UNAVAILABLE','COORDINATE_CONTEXT_MISMATCH','INVALID_COORDINATE_HOME',
                          'UNSUPPORTED_VERSION','DIRECTION_DENIED','REQUEST_CONFLICT','STALE_REQUEST','INVALID_REQUEST_ID']}

class CommandRegistry:
    def __init__(self, skills=None):
        self.skills=skills if skills is not None else default_registry()
        self.namespaces={'core':'1'}
        self._commands={}
        self.settings={}
        self.events={}
    def namespace(self,name,version='1'):
        if not re.fullmatch(r'[a-z][a-z0-9_.-]{0,63}',name) or name in self.namespaces or version!='1':
            raise ValueError('Conflicting/reserved namespace or incompatible namespace version')
        self.namespaces[name]=version
    def _insert(self,command):
        if command.language!=VERSION or command.namespace not in self.namespaces:raise ValueError('Incompatible or unknown namespace')
        if not re.fullmatch(r'[A-Z](?:0|[1-9][0-9]{0,2})',command.opcode):raise ValueError('Invalid opcode')
        if not re.fullmatch(r'[a-z][a-z0-9_.-]{0,127}',command.name):raise ValueError('Invalid semantic name')
        if (command.namespace,command.opcode) in self._commands or any(c.namespace==command.namespace and c.name==command.name for c in self._commands.values()):raise ValueError('Duplicate opcode/semantic identity')
        keys=[p.key for p in command.parameters];names=[p.name for p in command.parameters]
        if len(keys)>16 or len(set(keys))!=len(keys) or len(set(names))!=len(names) or any(not re.fullmatch('[A-Z]',k) for k in keys):raise ValueError('Invalid parameter keys')
        if any(p.default_kind not in {'required','static','runtime'} for p in command.parameters):raise ValueError('Invalid default kind')
        coordinate_names=[name for name,_ in command.coordinate_parameters]
        if (len(coordinate_names)!=len(set(coordinate_names)) or any(name not in names for name in coordinate_names)
                or any(kind not in {'point_x','point_y','point_z','point','voxel','point_samples','recorded_sequence'} for _,kind in command.coordinate_parameters)):
            raise ValueError('Invalid coordinate parameter metadata')
        if command.available and command.category=='skill' and command.skill not in {'observe_environment','inspect_inventory','list_recipes'}:
            if command.skill not in self.skills._definitions:raise ValueError('No existing skill for command')
            fields=self.skills._definitions[command.skill].parameters.model_fields
            if any(p.name not in fields and not (command.namespace=='core' and command.opcode=='M0' and p.name=='mode') for p in command.parameters):raise ValueError('Parameter is not a skill field')
        self._commands[command.namespace,command.opcode]=command
    def register_setting(self,setting,*,_core=False):
        if setting.namespace=='core' and not _core:raise ValueError('Core namespace protected')
        if not setting.values and setting.cyclic:raise ValueError('Only finite enums can cycle')
        if setting.values and (len(setting.values)!=len(set(setting.values)) or setting.default not in setting.values):raise ValueError('Invalid ordered enum/default')
        choices=tuple(setting.values)+('?', 'status')
        adapter=TypeAdapter(Literal[choices]) if setting.values else TypeAdapter(Annotated[float,Field(ge=.1,le=120)] | Literal['?','status'])
        p=Parameter('V','value','enum' if setting.values else 'setting_number',adapter,
                    'runtime' if setting.cyclic else 'required','cycle' if setting.cyclic else None,choices if setting.values else ())
        description=setting.description or 'Modal setting: get with ?/status; set value; omitted cycles ordered enum.'
        c=Command(setting.namespace,setting.opcode,setting.name,description,(p,),None,frozenset({'settings'}),category='setting')
        self._insert(c);self.settings[setting.namespace,setting.opcode]=setting
    def register_event(self,name,opcode,*,namespace='core',_core=False):
        if namespace=='core' and not _core:raise ValueError('Core namespace protected')
        if not re.fullmatch(r'(?:[a-z][a-z0-9_.-]*:)?[a-z][a-z0-9_.-]{0,127}',name) or name in self.events:raise ValueError('Invalid/duplicate event')
        self._insert(Command(namespace,opcode,'event.'+name.replace(':','.'),'Server-originated observation event; clients cannot emit it.',(),None,frozenset({'events'}),category='event_out'))
        self.events[name]={'opcode':opcode,'namespace':namespace,'direction':'server_to_client'}
    def register(self,command):
        if command.namespace=='core':raise ValueError('Core is protected; extensions require their own namespace')
        self._insert(command)
    def resolve(self,namespace,opcode):return self._commands.get((namespace,opcode))
    def discover(self,query='',limit=20):
        if not isinstance(query,str) or len(query)>128 or type(limit) is not int or not 1<=limit<=64:raise ValueError('Bounded discovery required')
        query={'navigation':'movement','fighting':'combat','craft':'crafting'}.get(query.lower(),query.lower())
        return [{'opcode':('' if c.namespace=='core' else c.namespace+':')+c.opcode,'command':c.namespace+':'+c.name,
                 'signature':' '.join(p.key for p in c.parameters),'description':c.description[:200],
                 'available':c.available,'category':c.category,'direction':'server_to_client' if c.category=='event_out' else 'client_to_server','permissions':sorted(c.permissions)}
                for c in self._commands.values() if query.lower() in (c.name+' '+c.description+' '+str(c.skill)).lower()][:limit]
    def describe(self,opcode):
        ns,op=opcode.split(':',1) if ':' in opcode else ('core',opcode)
        c=self.resolve(ns,op)
        if c is None:raise ValueError('Unknown command/namespace')
        result=c.describe()
        if (ns,op) in self.settings:result['setting']=self.settings[ns,op].describe()
        return result


@dataclass(frozen=True)
class Setting:
    namespace: str
    opcode: str
    name: str
    values: tuple[str,...]
    default: object
    cyclic: bool = True
    description: str | None = None
    def describe(self):
        result={'name':self.name,'values':list(self.values),'default':self.default,'cyclic':self.cyclic}
        if self.description is not None:result['description']=self.description
        return result


def skill_parameter(skills,skill,name,key,*,runtime=None,kind=None):
    f=skills._definitions[skill].parameters.model_fields[name]
    a=TypeAdapter(Annotated[f.annotation,*f.metadata] if f.metadata else f.annotation)
    schema=a.json_schema();enum=tuple(schema.get('enum',()))
    typ=kind or ('enum' if enum else 'json' if schema.get('type') in {'array','object'} else schema.get('type','json'))
    return Parameter(key,name,typ,a,'runtime' if runtime else 'required' if f.is_required() else 'static',
                     runtime if runtime else None if f.is_required() else f.default,enum)


def default_commands(skills=None):
    r=CommandRegistry(skills);s=r.skills
    def add(op,name,skill,keys,permission,description=None,coordinates=()):
        ps=tuple(skill_parameter(s,skill,n,k,kind='resource' if n=='item' else None) for n,k in keys)
        r._insert(Command('core',op,name,description or s._definitions[skill].description,ps,skill,frozenset({permission}),coordinate_parameters=coordinates))
    # M0 shares all numeric limits with WalkTo; only defaults and spelling are BCL-specific.
    ps=[skill_parameter(s,'walk_to',n,k,runtime=v) for n,k,v in [('x','X','current_x'),('y','Y','reachable_height'),('z','Z','current_z')]]
    ps.append(Parameter('F','mode','enum',TypeAdapter(Literal['normal','fast','sneak']),'static','normal',('normal','fast','sneak')))
    ps.append(skill_parameter(s,'walk_to','arrival_radius','A'))
    ps.extend(skill_parameter(s,'walk_to',name,key) for name,key in
              [('recorded_yaw','H'),('recorded_pitch','P'),('recorded_direction','B')])
    r._insert(Command('core','M0','movement.walk','Navigate using existing walk_to; auto Y requires an observed reachable target cell. F=normal/fast/sneak; A optionally tightens observed arrival. H/P/B carry matching local-human view and direction evidence for bounded grounded checkpoint pulses.',tuple(ps),'walk_to',frozenset({'movement'}),coordinate_parameters=(('x','point_x'),('y','point_y'),('z','point_z'))))
    add('M3','movement.recorded_path','replay_recorded_path',[('samples','T'),('arrival_radius','A')],'movement',
        'Replay one explicit sealed grounded crouch segment; T rows are [x,y,z,yaw,pitch,direction_code].',coordinates=(('samples','point_samples'),))
    add('M4','movement.recorded_sequence','replay_recorded_sequence',[('events','E'),('arrival_radius','A')],'movement',
        'Replay one explicit sealed continuous crouch sequence; E interleaves exact movement samples and exact one-use placements.',coordinates=(('events','recorded_sequence'),))
    add('M5','movement.recorded_drop','replay_recorded_drop',[('edge','Q'),('landing','L'),('yaw','H'),('pitch','P'),('direction','B')],'movement',
        'Replay one sealed bounded native step-off with exact view/direction and require the first recorded grounded landing.',coordinates=(('edge','point'),('landing','point')))
    add('M1','movement.approach','approach',[('target','T'),('position','P'),('terrain','E')],'movement',coordinates=(('position','voxel'),))
    add('M2','movement.dig_step','dig_step',[('direction','D'),('steps','N')],'mining')
    add('C0','crafting.item','craft_item',[('item','I'),('batches','N')],'crafting','Craft recipe batches (NOT desired output count); existing recipe and native station contracts apply.')
    add('C1','crafting.gather_wood','gather_wood',[('count','N'),('terrain','E')],'mining')
    add('C2','crafting.gather_block','gather_block',[('block','B'),('count','N'),('terrain','E'),('excavate','D'),('position','P')],'mining',coordinates=(('position','voxel'),))
    add('C3','crafting.remove_block','remove_block',[('block','B'),('position','P'),('excavate','D')],'mining',coordinates=(('position','voxel'),))
    r._insert(Command('core','I0','inventory.inspect','Fresh observed inventory; does not open a GUI.',(), 'inspect_inventory',frozenset({'observe'})))
    add('I1','inventory.equip','equip_item',[('item','I')],'inventory')
    add('I2','inventory.consume','consume_item',[],'inventory')
    add('I3','inventory.place','place_block',[('block','B'),('support','P'),('face','F'),('auto_position','A'),('recorded_pose','Q'),('recorded_aim','R'),('recorded_sneak','K'),('jump_place','J'),('clear_plants','C')],'inventory',coordinates=(('support','voxel'),('recorded_pose','point'),('recorded_aim','point')))
    add('I4','inventory.place_at','place_at',[('block','B'),('position','P'),('clear_plants','C')],'inventory',coordinates=(('position','voxel'),))
    r._insert(Command('core','V0','view.observe','Fresh bounded client observation, no hidden world queries.',(),'observe_environment',frozenset({'observe'})))
    add('V1','view.interact','interact_with_block',[('target','T'),('position','P'),('terrain','E')],'inventory',coordinates=(('position','voxel'),))
    add('V2','view.aim','aim_at',[('x','X'),('y','Y'),('z','Z')],'movement',coordinates=(('x','point_x'),('y','point_y'),('z','point_z')))
    add('F0','combat.fight','fight',[('duration_seconds','D'),('min_health','H'),('allow_unarmed','U')],'combat')
    for op,name,values,default,description in [
        ('S0','execution_mode',('sync','async'),'sync',None),
        ('S1','coordinate_mode',('absolute','relative'),'absolute','Select global coordinates or capture a persistent session home at execution time. Explicit relative assignments re-home; omitted toggles; ?/status are side-effect-free.'),
        ('S2','movement_mode',('normal','fast','sneak'),'normal',None),
        ('S3','error_mode',('stop','continue'),'stop',None),
        ('S4','timeout_seconds',(),30.,None)]:
        r.register_setting(Setting('core',op,name,values,default,bool(values),description),_core=True)
    for op,name in [('E0','subscribe'),('E1','unsubscribe'),('E2','subscriptions'),('E3','clear')]:
        ps=(Parameter('T','event','string',TypeAdapter(str)),) if op in {'E0','E1'} else ()
        r._insert(Command('core',op,'events.'+name,'Own-session event subscription control.',ps,None,frozenset({'events'}),category='event_control'))
    for name,op in [('player.position','E100'),('player.health','E101'),('inventory.changed','E102'),('command.completed','E103'),('player.dead','E104'),('player.respawned','E105'),('player.not_in_world','E106'),('transport.disconnected','E107')]:r.register_event(name,op,_core=True)
    return r
