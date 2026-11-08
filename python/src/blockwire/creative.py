"""Strict SDK envelopes for bounded native Creative building mechanics."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator
from .schematic import PROFILES

PROFILE = 'grounded_creative_v1'
FIELDS = {
    'probe': set(),
    'material': {'item', 'slot', 'expected_item', 'expected_count'},
    'place': {'token', 'position'},
    'remember': {'token', 'position'},
    'toggle': {'token', 'position', 'open'},
    'check': {'ticket'},
    'remove': {'ticket', 'token', 'position'},
}


class CreativeRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', allow_inf_nan=False)
    action: Literal['probe', 'material', 'place', 'remember', 'toggle', 'check', 'remove']
    actor_session: str = Field(min_length=1, max_length=128)
    item: str | None = None
    slot: int | None = Field(default=None, ge=0, le=8)
    expected_item: str | None = None
    expected_count: int | None = Field(default=None, ge=0, le=64)
    token: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    ticket: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    position: list[int] | None = Field(default=None, min_length=3, max_length=3)
    open: bool | None = None

    @model_validator(mode='after')
    def envelope(self):
        fields = self.model_fields_set - {'action', 'actor_session'}
        if fields != FIELDS[self.action] or any(getattr(self, key) is None for key in fields):
            raise ValueError('Exact action-specific fields required')
        if self.action == 'material':
            if self.item not in PROFILES or self.expected_item not in {'', *PROFILES}:
                raise ValueError('Unsupported Creative material')
            if (self.expected_item == '') != (self.expected_count == 0):
                raise ValueError('Invalid asserted slot contents')
        if self.position is not None:
            x, y, z = self.position
            if abs(x) > 29_999_984 or abs(z) > 29_999_984 or not -2048 <= y <= 2048:
                raise ValueError('Position outside supported bounds')
        return self


class ObservedState(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    id: str = Field(min_length=1, max_length=128, pattern=r'^[a-z0-9_.-]+:[a-z0-9_./-]+$')
    properties: dict[str, str] = Field(max_length=32)
    position: list[int] = Field(min_length=3, max_length=3)

    @field_validator('properties')
    @classmethod
    def bounded_properties(cls, value):
        import re
        if any(not re.fullmatch(r'[a-z0-9_]{1,64}', key) or not re.fullmatch(r'[a-z0-9_.-]{1,64}', item)
               for key, item in value.items()):
            raise ValueError('Malformed block properties')
        return value


def native_call(player, action: str, *, actor_session: str, **arguments):
    request = CreativeRequest(action=action, actor_session=actor_session, **arguments)
    return player.backend.call('creative', **request.model_dump(exclude_none=True, mode='json'))
