"""Explicit input phases and asserted native slot programs, never a recipe/route planner."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .machine_actions import MachineParameters, Aim, aim_angles, scene, release
from .skills.core import SkillStop

class Data(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,allow_inf_nan=False)

Button = Literal['forward','back','left','right','jump','sneak','sprint','attack','use']

class Target(Data):
    block: str = Field(pattern=r'^[a-z0-9_.-]+:[a-z0-9_./-]+$',max_length=128)
    position: list[int] = Field(min_length=3,max_length=3)
    face: Literal['up','down','north','south','east','west']

class InputPhase(Data):
    buttons: list[Button] = Field(max_length=9)
    seconds: float = Field(ge=.05,le=30.)
    look: Aim | None = None
    press: Literal['attack','use'] | None = None
    target: Target | None = None
    @model_validator(mode='after')
    def compatible(self):
        keys=set(self.buttons)
        if len(keys)!=len(self.buttons) or {'forward','back'}<=keys or {'left','right'}<=keys:
            raise ValueError('Unique non-opposed controls required')
        if self.look and (self.press or self.target):raise ValueError('Aim in one phase, target-check/press in the next')
        if self.press and {'attack','use'} & keys:raise ValueError('Do not mix one-shot press with held attack/use')
        return self

class InputSequence(MachineParameters):
    timeout_seconds: float = Field(default=35.,ge=.1,le=35.)
    phases: list[InputPhase] = Field(min_length=1,max_length=16)
    @model_validator(mode='after')
    def bounded(self):
        if sum(p.seconds for p in self.phases)>30.:raise ValueError('At most30 seconds of explicit input')
        return self

def target_guard(value,target):
    if target is None:return
    hit=value.get('target') or {}
    if hit.get('kind')!='block' or hit.get('id')!=target.block or any(hit.get(key)!=getattr(target,key) for key in ('position','face')):
        raise SkillStop('blocked','target_changed')

def input_sequence(context,parameters):
    initial=scene(context);actor=initial['actor_session']
    for index,phase in enumerate(parameters.phases):
        end=context.clock()+phase.seconds;pressed=False;angles=None
        context.publish({'phase':'input_phase','index':index})
        while context.clock()<end:
            value=scene(context,actor,initial['health']);target_guard(value,phase.target);context.check()
            # The full next mask changes keys, retaining common owned keys without stop().
            context.player.drive(phase.buttons,6,
                                 wait=False,actor_session=actor)
            if phase.look and angles is None:
                value=scene(context,actor,initial['health']);angles=aim_angles(value,phase.look);context.check()
                context.player.look(*angles,actor_session=actor,duration_ms=phase.look.duration_ms)
            if phase.press and not pressed:
                value=scene(context,actor,initial['health']);target_guard(value,phase.target);context.check()
                context.player.action(phase.press,actor_session=actor);pressed=True
            context.pause(min(.2,max(0.,end-context.clock())))
        if phase.look:
            value=scene(context,actor,initial['health'])
            if angles is None or abs((value['yaw']-angles[0]+180)%360-180)>.25 or abs(value['pitch']-angles[1])>.25:
                raise SkillStop('blocked','rotation_not_observed')
    return release(context,actor)

class Stack(Data):
    item: str | None = Field(default=None,max_length=128,pattern=r'^[a-z0-9_.-]+:[a-z0-9_./-]+$')
    count: int = Field(ge=0,le=99)
    @model_validator(mode='after')
    def empty(self):
        if (self.item is None)!=(self.count==0):raise ValueError('Empty means null item and zero count')
        return self
    def matches(self,value):
        if self.count==0:return value.get('empty') is True
        return value.get('empty') is False and value.get('item')==self.item and value.get('count')==self.count

class SlotCheck(Stack):
    slot: int = Field(ge=0,le=1023)

class SlotStep(Data):
    slot: int = Field(ge=0,le=1023)
    button: int = Field(default=0,ge=0,le=1)
    before: list[SlotCheck] = Field(min_length=1,max_length=16)
    after: list[SlotCheck] = Field(min_length=1,max_length=16)
    carried_before: Stack
    carried_after: Stack
    @model_validator(mode='after')
    def checks(self):
        for checks in (self.before,self.after):
            ids=[c.slot for c in checks]
            if len(set(ids))!=len(ids) or self.slot not in ids:raise ValueError('Unique checks including clicked slot required')
        before={c.slot:(c.item,c.count) for c in self.before}
        after={c.slot:(c.item,c.count) for c in self.after}
        if self.carried_before==self.carried_after and not any(before[n]!=after[n] for n in before.keys() & after.keys()):
            raise ValueError('A changed observed postcondition is required')
        return self

class SlotProgram(MachineParameters):
    timeout_seconds: float = Field(default=35.,ge=.1,le=35.)
    menu_id: int = Field(ge=0)
    steps: list[SlotStep] = Field(min_length=1,max_length=16)

def inventory_read(context,actor,health,menu_id):
    scene(context,actor,health);context.check();value=context.player.inventory();context.check()
    if value.get('actor_session')!=actor:raise SkillStop('blocked','actor_session_changed')
    if not value.get('guarded_inventory') or value.get('menu_id')!=menu_id or not value.get('container_open'):
        raise SkillStop('blocked','inventory_menu_changed')
    return value

def matches(value,checks,carried):
    slots={s['slot']:s for s in value.get('slots',[])}
    return (carried.matches(value.get('carried',{})) and
            all(c.slot in slots and slots[c.slot].get('active') is True and c.matches(slots[c.slot]) for c in checks))

def slot_program(context,parameters):
    initial=scene(context);actor=initial['actor_session']
    for index,step in enumerate(parameters.steps):
        value=inventory_read(context,actor,initial['health'],parameters.menu_id)
        if not matches(value,step.before,step.carried_before):raise SkillStop('blocked','inventory_precondition_changed')
        context.publish({'phase':'asserted_slot_click','index':index,'partial_inventory_state_possible':True})
        context.check()
        context.player.click_slot(step.slot,step.button,'pickup',menu_id=parameters.menu_id,
                                  state_id=value['state_id'],actor_session=actor)
        # Exactly one click. Only observations are repeated, never the action.
        until=min(context.deadline,context.clock()+1.5)
        try:
            while context.clock()<until:
                context.pause(.05)
                value=inventory_read(context,actor,initial['health'],parameters.menu_id)
                if matches(value,step.after,step.carried_after):break
            else:raise SkillStop('failed','inventory_effect_not_observed')
        except SkillStop as error:
            raise SkillStop('failed','inventory_effect_not_observed') from error
    return release(context,actor)
