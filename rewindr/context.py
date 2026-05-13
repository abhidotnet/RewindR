"""
context.py
----------
Context-manager support for rewindr: ``SessionRef`` and ``rewind_context``.

``with rewindr(steps=50):`` is implemented via :class:`RewindConfigurable`
in :mod:`rewindr.decorator`, which delegates here for frame/code resolution.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from types import FrameType
from typing import Any, Optional

from .buffer import RingBuffer
from .exceptions import ConfigurationError
from .session import RewindSession
from .tracer import TraceRecorder

# Attribute name used when attaching :class:`~rewindr.session.RewindSession`
# to a raised :class:`BaseException`.
REWIND_SESSION_ATTR: str = "rewind_session"


@dataclass
class SessionRef:
    """
    Mutable handle populated when a ``rewindr`` / ``rewind_context`` block ends.

    While recording, ``session`` is ``None``.  After the block finishes
    (normally or with an exception), ``session`` references the frozen
    :class:`~rewindr.session.RewindSession`.
    """

    session: Optional[RewindSession] = None

    def __repr__(self) -> str:  # noqa: D105
        if self.session is None:
            return "<SessionRef (recording — session not yet available)>"
        return f"<SessionRef session={self.session!r}>"


def validate_steps(steps: int) -> int:
    """Return *steps* if valid, else raise :class:`ConfigurationError`."""
    if steps < 1:
        raise ConfigurationError(f"steps must be >= 1, got {steps}")
    return steps


def build_session(
    buffer: RingBuffer,
    recorder: TraceRecorder,
    exception: Optional[BaseException] = None,
) -> RewindSession:
    """Freeze *buffer* into a :class:`RewindSession` using recorder metadata."""
    exc = exception if exception is not None else recorder.exception
    return RewindSession(
        history=buffer.freeze(),
        exception=exc,
        evicted=buffer.evicted,
    )


def attach_session_to_exception(exc: BaseException, session: RewindSession) -> None:
    """Attach *session* to *exc* for post-mortem inspection."""
    setattr(exc, REWIND_SESSION_ATTR, session)


def get_session_from_exception(exc: BaseException) -> Optional[RewindSession]:
    """Return the session attached to *exc*, if any."""
    return getattr(exc, REWIND_SESSION_ATTR, None)


class _RewindBlock:
    """Internal context manager implementation."""

    def __init__(self, steps: int, ref: SessionRef, *, caller_frame_depth: int = 1) -> None:
        self._steps = validate_steps(steps)
        self._ref = ref
        self._caller_frame_depth = caller_frame_depth
        self._buffer: RingBuffer = RingBuffer(maxlen=self._steps)
        self._recorder: Optional[TraceRecorder] = None

    def __enter__(self) -> SessionRef:
        # depth ``1`` → ``with rewind_context(...)``; ``2`` when wrapped by
        # :class:`RewindConfigurable.__enter__`.
        frame: FrameType = sys._getframe(self._caller_frame_depth)
        code = frame.f_code
        filename = frame.f_code.co_filename
        self._recorder = TraceRecorder(
            self._buffer,
            filename,
            code.co_name,
            target_code=code,
        )
        self._recorder.start()
        return self._ref

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        if self._recorder is not None:
            self._recorder.stop()
        assert self._recorder is not None
        session = build_session(self._buffer, self._recorder)
        self._ref.session = session
        if exc_val is not None:
            attach_session_to_exception(exc_val, session)


def rewind_context(*, steps: int = 50) -> _RewindBlock:
    """
    Trace the body of ``with rewind_context(...)`` in the *caller* function.

    Parameters
    ----------
    steps:
        Ring-buffer capacity (most recent *steps* snapshots are retained).

    Returns
    -------
    _RewindBlock
        Context manager whose ``__enter__`` returns a :class:`SessionRef`.
    """
    return _RewindBlock(steps, SessionRef(), caller_frame_depth=1)
