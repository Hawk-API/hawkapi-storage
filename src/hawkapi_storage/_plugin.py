"""Plugin entry point + DI helpers."""

from __future__ import annotations

from typing import Any

from hawkapi import HTTPException, Request

from ._base import Storage


class _StateNamespace:
    storage: Any


_ACTIVE: dict[int, Storage] = {}
_LAST: list[Storage | None] = [None]


def init_storage(app: Any, *, storage: Storage) -> Storage:
    """Attach a :class:`Storage` to ``app.state.storage`` and register it for DI lookup."""
    if getattr(app, "state", None) is None:
        app.state = _StateNamespace()
    app.state.storage = storage
    _ACTIVE[id(app)] = storage
    _LAST[0] = storage
    return storage


def resolve_storage(app: Any) -> Storage | None:
    if app is None:
        return _LAST[0]
    found = _ACTIVE.get(id(app))
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
