"""Finite typed action lists. No variables, branches, loops or source evaluation."""
from typing import Annotated,Literal,Union
from pydantic import BaseModel,ConfigDict,Field,create_model
from .machine_actions import action_registry

class StrictCall(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,allow_inf_nan=False)

_calls=tuple(create_model(name+'_Call',__base__=StrictCall,
             name=(Literal[name],...),parameters=(definition.parameters,...))
             for name,definition in action_registry()._definitions.items())
MachineAction=Annotated[Union[_calls],Field(discriminator='name')]

class Composition(StrictCall):
    actions:list[MachineAction]=Field(min_length=1,max_length=32)


def operation_cost(name,parameters):
    _,params=action_registry().prepare(name,parameters)
    if name=='slot_program':return len(params.steps)
    if name=='input_sequence':return len(params.phases)+sum(p.press is not None for p in params.phases)+sum(p.look is not None for p in params.phases)
    return 1


def source(actions):
    from .bcl.machine import machine_commands,encode_action
    from .bcl.compiler import compile_bcl
    batch=Composition.model_validate({'actions':actions});registry=machine_commands()
    text='\n'.join(encode_action(registry,row.name,row.parameters.model_dump()) for row in batch.actions)
    compile_bcl(text,registry)  # Whole composition validated before dispatch.
    return text
