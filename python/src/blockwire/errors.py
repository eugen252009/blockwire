"""Typed failure domains: an explicit native rejection is NOT a broken TLS connection."""
from enum import Enum

class FaultKind(str,Enum):
    TRANSPORT='transport.disconnected'
    ACTOR='actor_session_changed'
    DEAD='player.dead'
    NOT_IN_WORLD='player.not_in_world'
    PRECONDITION='operation.rejected'
    INVARIANT='invariant.violation'

_LIFECYCLE={'actor_session_changed':FaultKind.ACTOR,'player_dead':FaultKind.DEAD,'not_in_world':FaultKind.NOT_IN_WORLD}
_LEGACY={**_LIFECYCLE,**{k:FaultKind.PRECONDITION for k in ('close_screen_first','stale_menu','no_container_screen','target_entity_changed')}}

def classify(error):
    kind=getattr(error,'fault_kind',None)
    if kind is not None:return FaultKind(kind)
    return _LEGACY.get(str(error),FaultKind.TRANSPORT)

class InvariantViolation(RuntimeError):
    fault_kind=FaultKind.INVARIANT

class NativeOperationError(RuntimeError):
    """Mixin contract; client.NativeRejected combines it with legacy BridgeError."""
    def __init__(self,code):
        super().__init__(code);self.code=code
        self.fault_kind=_LIFECYCLE.get(code,FaultKind.PRECONDITION)
