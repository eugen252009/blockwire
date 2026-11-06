"""Bounded model-authored working notes. Data only; never executable or verified."""
from pydantic import BaseModel,ConfigDict,Field

class MachinePlan(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,allow_inf_nan=False)
    notes:str=Field(max_length=4096,description='Your own short plan, chosen blueprint, material accounting and next steps. Untrusted notes, not verified world facts or executable commands.')
