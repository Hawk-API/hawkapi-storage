"""Plugin entry point + DI helpers."""

from __future__ import annotations

import contextlib
from typing import Any
from weakref import WeakKeyDictionary

from hawkapi import HTTPException, Request

from ._base import Storage


class _StateNamespace:
    storage: Any


# WeakKeyDictionary avoids the ``id(app)`` ABA hazard if an app is GC'd and
# Python reuses the address for a new object.
_ACTIVE: WeakKeyDictionary[Any, Storage] = WeakKeyDictionary()
_LAST: list[Storage | None] = [None]


def init_storage(app: Any, *, storage: Storage) -> Storage:
    """Attach a :class:`Storage` to ``app.state.storage`` and register it for DI lookup."""
    if getattr(app, "state", None) is None:
        app.state = _StateNamespace()
    app.state.storage = storage
    with contextlib.suppress(TypeError):
        _ACTIVE[app] = storage
    _LAST[0] = storage
    return storage


def resolve_storage(app: Any) -> Storage | None:
    if app is None:
        return _LAST[0]
    try:
        found = _ACTIVE.get(app)
    except TypeError:
        found = None
    if found is not None:
        return found
    state = getattr(app, "state", None)
    if state is not None and hasattr(state, "storage"):
        return state.storage  # type: ignore[no-any-return]
    return _LAST[0]


def get_storage(request: Request) -> Storage:
    found = resolve_storage(request.scope.get("app"))
    if found is None:
        raise HTTPException(500, detail="Storage not configured — call init_storage(app, ...)")
    return found


__all__ = ["get_storage", "init_storage", "resolve_storage"]
