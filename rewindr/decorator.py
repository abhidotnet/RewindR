"""
decorator.py
------------
Public :func:`rewindr` entrypoint — decorator factory, function wrapper,
and ``with`` statement support via :class:`RewindConfigurable`.
"""

from __future__ import annotations

import functools
from types import CodeType
from typing import Any, Callable, Optional, TypeVar, overload

from .buffer import RingBuffer
from .context import (
    SessionRef,
    attach_session_to_exception,
    build_session,
    validate_steps,
)
from .session import RewindSession
from .tracer import TraceRecorder
from .utils import resolve_filename

F = TypeVar("F", bound=Callable[..., Any])


def _decorate(func: F, steps: int) -> F:
    """Wrap *func* so each call returns a :class:`RewindSession`."""
    validate_steps(steps)
    target_file = resolve_filename(func)
    target_code: CodeType = func.__code__

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> RewindSession:
        buffer = RingBuffer(maxlen=steps)
        recorder = TraceRecorder(
            buffer,
            target_file,
            func.__name__,
            target_code=target_code,
        )
        recorder.start()
        try:
            func(*args, **kwargs)
        except BaseException as exc:
            recorder.stop()
            session = build_session(buffer, recorder, exception=exc)
            attach_session_to_exception(exc, session)
            return session
        else:
            recorder.stop()
            return build_session(buffer, recorder, exception=None)

    return wrapper  # type: ignore[return-value]


class RewindConfigurable:
    """
    Object returned by ``rewindr(steps=…)``.

    * ``__call__(func)`` → decorated function.
    * ``__enter__ / __exit__`` → context manager (same as ``rewind_context``).
    """

    __slots__ = ("_steps", "_block")

    def __init__(self, steps: int) -> None:
        self._steps = validate_steps(steps)
        self._block: Any = None  # lazily created for context use

    def __call__(self, func: F) -> F:
        return _decorate(func, self._steps)

    def __enter__(self) -> SessionRef:
        from .context import SessionRef as _SR, _RewindBlock

        ref = _SR()
        self._block = _RewindBlock(self._steps, ref, caller_frame_depth=2)
        return self._block.__enter__()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        if self._block is not None:
            self._block.__exit__(exc_type, exc_val, exc_tb)
        self._block = None


@overload
def rewindr(__func: F, *, steps: int = ...) -> F: ...


@overload
def rewindr(*, steps: int = ...) -> RewindConfigurable: ...


def rewindr(
    __func: Optional[F] = None,
    *,
    steps: int = 50,
) -> RewindConfigurable | F:
    """
    Lightweight time-travel tracing.

    **As a decorator** (``@rewindr`` or ``@rewindr(steps=…)``) — each call
    executes the wrapped function and returns a :class:`RewindSession`.

    **As a context manager** — ``with rewindr(steps=100) as ref:`` then read
    ``ref.session`` after the block.

    Parameters
    ----------
    steps:
        Ring-buffer capacity (most recent *steps* snapshots are kept).
    """
    if __func is not None:
        if not callable(__func):
            raise TypeError("@rewindr requires a callable when used without keyword steps")
        return _decorate(__func, steps)
    return RewindConfigurable(steps)
