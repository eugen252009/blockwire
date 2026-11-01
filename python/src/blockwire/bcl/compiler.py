"""Bounded BCL/1 lexer/parser/type checker. Never connects to Minecraft."""
from dataclasses import dataclass
import hashlib
import json
import math
import re
from .registry import VERSION,DEFAULT_PERMISSIONS

@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    phase: str = 'compile'
    line: int = 1
    column: int = 1
    opcode: str | None = None
    command: str | None = None
    parameter: str | None = None
    expected: object = None
    actual: object = None
    def to_dict(self):return self.__dict__.copy()

class BCLError(ValueError):
    def __init__(self,diagnostic):
        self.diagnostic=diagnostic
        super().__init__(diagnostic.message)

@dataclass(frozen=True)
class Token:
    text: str
    column: int
    quoted: bool = False
    prefix: str = ''

@dataclass(frozen=True)
class Binding:
    parameter: str
    supplied: bool
    value: object = None
    def to_dict(self):return {'parameter':self.parameter,'supplied':self.supplied,'value':json.loads(self.value) if self.supplied else None}

@dataclass(frozen=True)
class Operation:
    namespace: str
    opcode: str
    command: str
    bindings: tuple[Binding,...]
    line: int
    column: int
    def to_dict(self):return {**{k:getattr(self,k) for k in ('namespace','opcode','command','line','column')},'bindings':[b.to_dict() for b in self.bindings]}

@dataclass(frozen=True)
class Program:
    version: str
    registry_digest: str
    operations: tuple[Operation,...]
    def to_dict(self):return {'version':self.version,'registry_digest':self.registry_digest,'operations':[o.to_dict() for o in self.operations]}
    @property
    def digest(self):return hashlib.sha256(json.dumps(self.to_dict(),sort_keys=True,allow_nan=False).encode()).hexdigest()


def registry_digest(registry):
    return hashlib.sha256(json.dumps({'language':VERSION,'namespaces':registry.namespaces,
        'commands':[registry.describe(('' if c.namespace=='core' else c.namespace+':')+c.opcode) for c in registry._commands.values()],
        'events':registry.events,
        'skills':registry.skills.describe()},sort_keys=True,allow_nan=False).encode()).hexdigest()


def lex(line,number):
    tokens=[];i=0
    while i<len(line):
        if line[i].isspace():i+=1;continue
        if line[i] in '#;':break
        start=i
        while i<len(line) and not line[i].isspace() and line[i] not in '\"#;':i+=1
        prefix=line[start:i]
        if i<len(line) and line[i]=='\"':
            try:value,end=json.JSONDecoder().raw_decode(line[i:])
            except (ValueError,RecursionError):raise BCLError(Diagnostic('INVALID_STRING','Expected a JSON double-quoted string with valid escapes.',line=number,column=i+1))
            i+=end
            if not isinstance(value,str) or (i<len(line) and not line[i].isspace() and line[i] not in '#;'):
                raise BCLError(Diagnostic('INVALID_STRING','Characters after a quoted value.',line=number,column=i+1))
            tokens.append(Token(value,start+1,True,prefix))
        else:tokens.append(Token(prefix,start+1))
        if len(tokens)>33:raise BCLError(Diagnostic('PROGRAM_LIMIT','Too many tokens on a line.',line=number,column=start+1))
    return tokens


def compile_bcl(source,registry,*,permissions=DEFAULT_PERMISSIONS,version=VERSION):
    def fail(code,message,line=1,column=1,**details):raise BCLError(Diagnostic(code,message,line=line,column=column,**details))
    if version!=VERSION:fail('UNSUPPORTED_VERSION','Only BCL/1 is supported.',actual=version,expected=VERSION)
    if not isinstance(source,str) or len(source)>16384:fail('PROGRAM_LIMIT','Source must be a string of at most 16384 characters.')
    ops=[];header=False
    for line_number,line in enumerate(source.splitlines(),1):
        tokens=lex(line,line_number)
        if not tokens:continue
        first=tokens[0]
        if first.text.startswith('BCL/'):
            if header or ops or len(tokens)!=1 or first.text!=VERSION or first.quoted:fail('UNSUPPORTED_VERSION','Invalid/incompatible version header.',line_number,first.column,actual=first.text)
            header=True;continue
        if len(ops)>=32:fail('PROGRAM_LIMIT','At most 32 operations per batch.',line_number)
        match=re.fullmatch(r'(?:(?P<ns>[a-z][a-z0-9_.-]{0,63}):)?(?P<op>[A-Z](?:0|[1-9][0-9]{0,2}))',first.text)
        if not match or first.quoted:fail('UNKNOWN_COMMAND','Expected an uppercase numeric opcode.',line_number,first.column,opcode=first.text)
        ns,opcode=match['ns'] or 'core',match['op']
        details={'opcode':first.text}
        if ns not in registry.namespaces:fail('UNKNOWN_NAMESPACE','Extension namespace is not installed/selected.',line_number,first.column,**details)
        command=registry.resolve(ns,opcode)
        if command is None:fail('UNKNOWN_COMMAND','Opcode is not registered in this namespace.',line_number,first.column,**details)
        details['command']=ns+':'+command.name
        if command.category=='event_out':fail('DIRECTION_DENIED','Clients cannot emit authoritative server events.',line_number,first.column,**details)
        if not command.available:fail('UNSUPPORTED_CAPABILITY','Command is documented but unavailable.',line_number,first.column,**details)
        if not command.permissions<=frozenset(permissions):fail('PERMISSION_DENIED','Command exceeds operator-selected permissions.',line_number,first.column,expected=sorted(command.permissions),**details)
        assigned={};positional=0
        for token in tokens[1:]:
            key=None;value=token.text
            if token.quoted:
                if token.prefix:
                    m=re.fullmatch(r'([A-Z])=?',token.prefix)
                    if not m:fail('INVALID_ARGUMENT','Invalid prefix before quoted value.',line_number,token.column,**details)
                    key=m[1]
            elif re.match('[A-Z]',value):
                key=value[0];value=value[1:]
                if value.startswith('='):value=value[1:]
            if key is None:
                if positional>=len(command.parameters):fail('INVALID_ARGUMENT','Too many positional arguments.',line_number,token.column,actual=value,**details)
                param=command.parameters[positional];positional+=1
            else:
                param=next((p for p in command.parameters if p.key==key),None)
                if param is None:fail('UNKNOWN_PARAMETER','Unknown parameter key.',line_number,token.column,parameter=key,**details)
            if param.name in assigned:fail('DUPLICATE_ARGUMENT','A parameter may be assigned only once.',line_number,token.column,parameter=param.key,**details)
            try:
                if value=='null' and not token.quoted:parsed=None
                elif param.kind=='integer':
                    if token.quoted or not re.fullmatch(r'[+-]?[0-9]+',value):raise ValueError()
                    parsed=int(value)
                elif param.kind=='setting_number':
                    if value in {'?','status'}:parsed=value
                    elif token.quoted or not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?',value):raise ValueError()
                    else:parsed=float(value)
                elif param.kind=='number':
                    if token.quoted or not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?',value):raise ValueError()
                    parsed=float(value)
                    if not math.isfinite(parsed):raise ValueError()
                elif param.kind=='boolean':
                    if token.quoted or value not in {'true','false'}:raise ValueError()
                    parsed=value=='true'
                elif param.kind=='json':
                    from ..llm import strict_json
                    # strict_json is object-only; other JSON values still need duplicate/nonfinite rejection.
                    parsed=strict_json('{"v":'+value+'}')['v']
                else:parsed=value
                if param.kind=='resource' and parsed is not None and not re.fullmatch(r'[a-z0-9_.-]+:[a-z0-9_./-]+',parsed):raise ValueError()
                parsed=param.adapter.validate_python(parsed,strict=True)
            except (ValueError,TypeError,OverflowError,RecursionError):
                fail('INVALID_ENUM_VALUE' if param.enum else 'INVALID_ARGUMENT','Value does not satisfy the command/skill contract.',line_number,token.column,
                     parameter=param.key,expected=list(param.enum) if param.enum else param.adapter.json_schema(),actual=value,**details)
            # Freeze structured arguments as canonical JSON, thaw only into the existing strict skill adapter.
            assigned[param.name]=param.adapter.dump_python(parsed,mode='json')
        for p in command.parameters:
            if p.name not in assigned and p.default_kind=='required':fail('MISSING_REQUIRED_ARGUMENT','Required parameter missing.',line_number,first.column,parameter=p.key,**details)
        if command.category=='event_control' and 'event' in assigned and assigned['event'] not in registry.events:
            fail('UNSUPPORTED_CAPABILITY','Event is not registered by an installed provider.',line_number,first.column,actual=assigned['event'],**details)
        # Validate the complete skill envelope statically; runtime defaults are represented, never guessed.
        if command.skill in registry.skills._definitions:
            values={p.name:assigned[p.name] if p.name in assigned else p.default for p in command.parameters if p.name in assigned or p.default_kind=='static'}
            if command.namespace=='core' and command.opcode=='M0':
                values={k:v for k,v in values.items() if k!='mode'}
                for n in ('x','y','z'):values.setdefault(n,0.)
            try:registry.skills.prepare(command.skill,values)
            except (ValueError,TypeError):fail('INVALID_ARGUMENT','Arguments do not satisfy the existing skill contract.',line_number,first.column,**details)
        ops.append(Operation(ns,opcode,command.name,tuple(Binding(p.name,p.name in assigned,json.dumps(assigned[p.name],allow_nan=False) if p.name in assigned else None) for p in command.parameters),line_number,first.column))
    if not ops:fail('EMPTY_PROGRAM','At least one command required.')
    return Program(VERSION,registry_digest(registry),tuple(ops))


def arguments(operation,command):
    """Immutable IR values are stored as canonical JSON; missing is a separate supplied flag."""
    return {b.parameter:json.loads(b.value) for b in operation.bindings if b.supplied}


def compile_report(source,registry,**kwargs):
    try:return {'ok':True,'program':compile_bcl(source,registry,**kwargs).to_dict(),'diagnostics':[]}
    except BCLError as e:return {'ok':False,'program':None,'diagnostics':[e.diagnostic.to_dict()]}
