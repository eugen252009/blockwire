"""Process-local actor ownership; the native connection lease is the cross-process fence."""
import threading

_LOCK = threading.Lock()
_OWNERS: dict[int, tuple[object, object, object]] = {}
BUSY = "A skill owns player control; cancel it and await terminal status first"


def _actor(player):
    return getattr(player, "backend", player)


def claim_control(player, cancel=None):
    actor = _actor(player)
    lease = object()
    with _LOCK:
        if id(actor) in _OWNERS:
            raise RuntimeError(BUSY)
        # Retain the actor while claimed, so its id cannot be recycled.
        _OWNERS[id(actor)] = (actor, lease, cancel)
    return lease


def release_control(player, lease):
    with _LOCK:
        entry = _OWNERS.get(id(_actor(player)))
        if entry is None or entry[1] is not lease:
            raise RuntimeError("Obsolete control lease")
        del _OWNERS[id(_actor(player))]


def cancel_control(player):
    """Request the current owner to stop; never imply that cleanup is complete."""
    with _LOCK:
        entry = _OWNERS.get(id(_actor(player)))
        cancel = entry[2] if entry else None
    if cancel is not None:
        cancel()


def control_busy(player):
    with _LOCK:
        return id(_actor(player)) in _OWNERS
