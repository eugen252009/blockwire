"""Small native action contracts. No resource search, route selection or recipes."""
import math,time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator
from .skills.core import SkillParameters, SkillDefinition, SkillRegistry, SkillResult, SkillStop

KEYS = frozenset({'forward','back','left','right','jump','sneak','sprint','attack','use'})

class MachineParameters(SkillParameters):
    timeout_seconds: float = Field(default=5.,ge=.1,le=5.)

class Pulse(MachineParameters):
    buttons: list[Literal['forward','back','left','right','jump','sneak','sprint']] = Field(min_length=1,max_length=7)
    seconds: float = Field(default=.2,ge=.05,le=2.)
    @model_validator(mode='after')
    def compatible(self):
        keys=set(self.buttons)
        if len(keys)!=len(self.buttons) or {'forward','back'}<=keys or {'left','right'}<=keys:
            raise ValueError('Unique non-opposed controls required')
        return self

class Aim(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,allow_inf_nan=False)
    yaw: float | None = Field(default=None,ge=-180,le=180)
    pitch: float | None = Field(default=None,ge=-90,le=90)
    point: list[float] | None = Field(default=None,min_length=3,max_length=3)
    duration_ms: int = Field(default=200,ge=1,le=1000)
    @model_validator(mode='after')
    def one_form(self):
        if self.point is not None:
            if self.yaw is not None or self.pitch is not None or any(abs(v)>30000000 for v in self.point):
                raise ValueError('Choose bounded point OR yaw/pitch')
        elif self.yaw is None or self.pitch is None:raise ValueError('Both yaw and pitch required')
        return self

class Turn(MachineParameters,Aim):
    pass

def aim_angles(value,parameters):
    if parameters.point is None:return parameters.yaw,parameters.pitch
    eye=value.get('eye_position')
    if not isinstance(eye,list) or len(eye)!=3 or any(type(v)not in (int,float) or not math.isfinite(v) for v in eye):
        raise SkillStop('blocked','eye_position_unavailable')
    dx,dy,dz=(parameters.point[i]-eye[i] for i in range(3))
    if math.hypot(dx,dy,dz)<1e-6:raise SkillStop('blocked','aim_point_at_eye')
    return math.degrees(math.atan2(-dx,dz)),-math.degrees(math.atan2(dy,math.hypot(dx,dz)))

class Press(MachineParameters):
    action: Literal['attack','use']

class Hold(Press):
    # Long native interactions (e.g. mining) need continuity, not a long lease.
    timeout_seconds: float = Field(default=35.,ge=.1,le=35.)
    seconds: float = Field(default=.2,ge=.05,le=30.)

class Select(MachineParameters):
    slot: int = Field(ge=0,le=8)

class Inventory(MachineParameters):
    opened: bool

class Click(MachineParameters):
    menu_id: int = Field(ge=0)
    state_id: int = Field(ge=0)
    slot: int = Field(ge=0,le=1023)
    button: int = Field(default=0,ge=0,le=1)
    mode: Literal['pickup','quick_move'] = 'pickup'
    @field_validator('button',mode='before')
    @classmethod
    def integer_button(cls,value):
        if type(value)is not int:raise ValueError('Strict integer button required')
        return value


def scene(context, actor=None, health=None):
    context.check()
    value=context.player.observe()
    if not value.get('in_world') or not value.get('alive'):raise SkillStop('blocked','live_player_required')
    session=value.get('actor_session')
    if not isinstance(session,str) or not session or (actor is not None and session!=actor):
        raise SkillStop('blocked','actor_session_changed')
    if health is not None and value.get('health',0)<health:raise SkillStop('blocked','health_lost')
    return value


def trace(player, actor):
    data=player.motion_trace(limit=1,actor_session=actor)
    samples=data.get('samples',[])
    if (data.get('profile')!='native_player_motion_ticks_v1' or data.get('actor_session')!=actor
            or not isinstance(samples,list) or len(samples)!=1):raise ValueError('Fresh native motion trace required')
    row=samples[-1]
    if row.get('actor_session')!=actor or type(row.get('client_tick'))is not int or row['client_tick']<0:
        raise ValueError('Fenced native client_tick required')
    # Native MotionTrace uses client_tick; tick is only this adapter's internal key.
    return {**row,'tick':row['client_tick']}


def released(row):
    inputs=row.get('inputs')
    return (row.get('remote_owned_inputs')==[] and isinstance(inputs,dict) and set(inputs)==KEYS
            and all(type(v)is bool and not v for v in inputs.values()))


def confirm_release(player, actor):
    """Read-only cleanup barrier, including cancellation/deadline exits."""
    before=trace(player,actor)
    until=time.monotonic()+1.
    while time.monotonic()<until:
        time.sleep(.05)
        current=trace(player,actor)
        if current['tick']>before['tick'] and released(current):return current['tick']
    raise RuntimeError('Fresh input release not confirmed')


def release(context, actor):
    """Observe a NEW tick after stop; never upgrade the input receipt into proof."""
    context.check();before=trace(context.player,actor)['tick'];context.player.stop()
    until=min(context.deadline,context.clock()+1.)
    while context.clock()<until:
        scene(context,actor)
        row=trace(context.player,actor)
        if row['tick']>before and released(row):
            return SkillResult(status='succeeded',reason='command_postcondition_observed',
                text='Command finished and native input release observed; gameplay outcome is unverified.',
                details={'gameplay_verified':False,'release_tick':row['tick'],'release_observed_monotonic_ns':time.monotonic_ns()})
        context.pause(.05)
    raise SkillStop('failed','input_release_not_observed')


def pulse(context, parameters):
    initial=scene(context);actor=initial['actor_session'];until=context.clock()+parameters.seconds
    buttons=parameters.buttons if isinstance(parameters,Pulse) else [parameters.action]
    while context.clock()<until:
        scene(context,actor,initial['health']);context.check()
        # Never lease more than six ticks; renew only after fresh state/cancel checks.
        ticks=min(6,max(1,math.ceil((until-context.clock())/.05)))
        context.player.drive(buttons,ticks,wait=False,actor_session=actor)
        context.pause(min(.2,max(0.,until-context.clock())))
    return release(context,actor)


def turn(context, parameters):
    initial=scene(context);actor=initial['actor_session'];context.check()
    yaw,pitch=aim_angles(initial,parameters)
    context.player.look(yaw,pitch,actor_session=actor,duration_ms=parameters.duration_ms)
    while True:
        current=scene(context,actor,initial['health'])
        if abs((current['yaw']-yaw+180)%360-180)<=.25 and abs(current['pitch']-pitch)<=.25:
            return release(context,actor)
        context.pause(.05)


def press(context, parameters):
    actor=scene(context)['actor_session'];context.check()
    context.player.action(parameters.action,actor_session=actor)
    return release(context,actor)


def select(context, parameters):
    actor=scene(context)['actor_session'];context.check()
    context.player.hotbar(parameters.slot,actor_session=actor)
    value=context.player.inventory()
    if value.get('actor_session')!=actor:raise SkillStop('blocked','actor_session_changed')
    if value.get('selected_hotbar')!=parameters.slot:raise SkillStop('blocked','selection_not_observed')
    return release(context,actor)


def inventory(context, parameters):
    actor=scene(context)['actor_session'];context.check()
    if parameters.opened:context.player.open_inventory(actor_session=actor)
    else:
        before=context.player.inventory()
        if before.get('actor_session')!=actor:raise SkillStop('blocked','actor_session_changed')
        if before.get('carried',{}).get('empty') is not True:raise SkillStop('blocked','cursor_requires_recovery')
        grid=range(1,10 if before.get('menu_type')=='CraftingMenu' else 5) if before.get('menu_type') in {'InventoryMenu','CraftingMenu'} else ()
        if any(s.get('slot') in grid and s.get('empty') is not True for s in before.get('slots',[])):
            raise SkillStop('blocked','crafting_grid_requires_recovery')
        context.check();context.player.close_screen(actor_session=actor)
    value=context.player.inventory()
    if value.get('actor_session')!=actor:raise SkillStop('blocked','actor_session_changed')
    if value.get('container_open') is not parameters.opened:raise SkillStop('blocked','inventory_state_not_observed')
    return release(context,actor)


def click(context, parameters):
    actor=scene(context)['actor_session'];context.check()
    context.player.click_slot(parameters.slot,parameters.button,parameters.mode,
        menu_id=parameters.menu_id,state_id=parameters.state_id,actor_session=actor)
    return release(context,actor)


def action_registry():
    from .machine_manipulation import InputSequence, SlotProgram, input_sequence, slot_program
    registry=SkillRegistry()
    for name,model,handler,description in [
        ('input_sequence',InputSequence,input_sequence,'Execute explicit timed key masks and optional single presses, retaining common keys between phases. No route/target selection or retries. Up to16 phases/30 seconds, six-tick leases.'),
        ('slot_program',SlotProgram,slot_program,'Execute up to16 explicit pickup clicks with caller-specified before/after slot and cursor assertions. Fresh native state IDs per click. No recipe, slot or material selection; no retries or rollback.'),
        ('pulse',Pulse,pulse,'Hold explicit movement buttons briefly. No pathfinding, distance or damage guarantee.'),
        ('turn',Turn,turn,'Aim at an explicit world-space point OR yaw/pitch using native camera rotation. No target selection or movement.'),
        ('press',Press,press,'One native attack/use press. No equip, retry or placement/harvest success claim.'),
        ('hold',Hold,pulse,'Request an attack/use hold for up to30 seconds via renewable six-tick actor-fenced leases. No target selection or harvest guarantee.'),
        ('select_slot',Select,select,'Select a hotbar slot; no item search or inventory rearrangement.'),
        ('inventory_screen',Inventory,inventory,'Open/close the native player inventory; no recipe selection.'),
        ('click_slot',Click,click,'One guarded menu/state/slot click. Refresh IDs from events before another click.')]:
        registry.register(SkillDefinition(name,description,model,handler))
    return registry
