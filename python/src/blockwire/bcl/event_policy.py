"""Future chat routing is LOCAL data filtering, never command authorization.

No chat source is installed/registered by this module. A trusted native provider
must supply sender identity, distance and mention metadata before enabling it.
"""
from dataclasses import dataclass
from typing import Literal
import math

@dataclass(frozen=True)
class ChatFilter:
    mode: Literal['all','mentions','players','nearby'] = 'mentions'
    players: frozenset[str] = frozenset()
    radius: float = 16.
    def __post_init__(self):
        if self.mode not in {'all','mentions','players','nearby'}:raise ValueError('Unknown local chat filter')
        if type(self.radius) not in (int,float) or not math.isfinite(self.radius) or not 0<self.radius<=64:raise ValueError('Bounded chat radius required')
        if len(self.players)>32 or any(not isinstance(p,str) or len(p)>128 for p in self.players):raise ValueError('Bounded sender identity set required')
    def __call__(self,name,data,identity):
        if name!='player.chat':return True
        if not isinstance(data,dict):return False
        if self.mode=='all':return True
        if self.mode=='mentions':
            mentions=data.get('mentions',[])
            return isinstance(mentions,list) and len(mentions)<=32 and identity['agent_id'] in mentions
        if self.mode=='players':return data.get('sender_uuid') in self.players
        distance=data.get('distance')
        return type(distance) in (int,float) and math.isfinite(distance) and 0<=distance<=self.radius
