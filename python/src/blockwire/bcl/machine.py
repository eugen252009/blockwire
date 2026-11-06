"""Action-only registry/profile. Existing BCL/1 compiler and FIFO remain authoritative."""
import json
from .registry import CommandRegistry, Command, Setting, skill_parameter
from ..machine_actions import action_registry

PROFILE='machine-v1'
STATE_EVENTS={'state.scene':'E120','state.inventory':'E121','state.navigation':'E122','state.crafting':'E125'}
CONTROL_EVENTS={'control.released':'E123','control.quarantined':'E124'}
TABLE={
    'input_sequence':('G3',{'phases':'P'}),
    'slot_program':('M6',{'menu_id':'M','steps':'S'}),
    'pulse':('G1',{'buttons':'B','seconds':'D'}),
    'turn':('G2',{'yaw':'Y','pitch':'P','point':'Q','duration_ms':'D'}),
    'press':('M1',{'action':'A'}),
    'hold':('M2',{'action':'A','seconds':'D'}),
    'select_slot':('M3',{'slot':'S'}),
    'inventory_screen':('M4',{'opened':'O'}),
    'click_slot':('M5',{'menu_id':'M','state_id':'I','slot':'S','button':'B','mode':'C'}),
}


def machine_commands():
    registry=CommandRegistry(action_registry());registry.machine_profile=True
    # Private journal defaults only: do not import/register the legacy command set.
    for opcode,name,values,default in [
        ('S0','execution_mode',('sync','async'),'async'),
        ('S1','coordinate_mode',('absolute','relative'),'absolute'),
        ('S2','movement_mode',('normal','fast','sneak'),'normal'),
        ('S3','error_mode',('stop','continue'),'stop'),
        ('S4','timeout_seconds',(),35.)]:
        registry.settings['core',opcode]=Setting('core',opcode,name,values,default,bool(values))
    for name,opcode in [('player.position','E100'),('player.health','E101'),('inventory.changed','E102'),
                        ('command.completed','E103'),('player.dead','E104'),('player.respawned','E105'),
                        ('player.not_in_world','E106'),('transport.disconnected','E107')]:
        registry.events[name]={'opcode':opcode,'namespace':'core','direction':'server_to_client'}
    for name,(opcode,keys) in TABLE.items():
        keys={**keys,'timeout_seconds':'T'}
        definition=registry.skills._definitions[name]
        parameters=tuple(skill_parameter(registry.skills,name,field,key) for field,key in keys.items())
        permissions=({'movement','inventory','mining','combat'} if name=='input_sequence' else
                     {'movement'} if name in {'pulse','turn'} else
                     {'inventory','mining','combat'} if name in {'press','hold'} else
                     {'inventory','crafting'} if name in {'click_slot','slot_program'} else {'inventory'})
        registry._insert(Command('core',opcode,'action.'+name,definition.description,parameters,name,
                                 frozenset(permissions)))
    for name,opcode in {**STATE_EVENTS,**CONTROL_EVENTS}.items():
        # Metadata only; server events are NOT client action opcodes.
        registry.events[name]={'opcode':opcode,'namespace':'core','direction':'server_to_client'}
    return registry


def encode_action(registry,name,parameters):
    if not getattr(registry,'machine_profile',False) or name not in TABLE:
        raise ValueError('Unknown machine action/profile')
    if not isinstance(parameters,dict):raise ValueError('Typed action parameters required')
    registry.skills.prepare(name,parameters)
    if len(json.dumps(parameters,allow_nan=False).encode())>8192:raise ValueError('Action bound')
    opcode,keys=TABLE[name];keys={**keys,'timeout_seconds':'T'}
    # JSON encoding, never interpolation of executable model source.
    def literal(value):
        encoded=json.dumps(value,allow_nan=False,separators=(',',':'))
        return json.dumps(encoded) if isinstance(value,(dict,list)) else encoded
    return opcode+' '+ ' '.join(keys[key]+'='+literal(value) for key,value in sorted(parameters.items()))
