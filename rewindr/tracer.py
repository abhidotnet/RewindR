"""
tracer.py
---------
Core tracing engine for rewindr.

TraceRecorder installs a sys.settrace hook that fires on executed lines
inside the dynamic extent of a single *target* code object (typically
``wrapped.__code__``).  On each qualifying event it captures a
:class:`~rewindr.snapshot.Snapshot` and pushes it into the supplied
:class:`~rewindr.buffer.RingBuffer`.

Design decisions
~~~~~~~~~~~~~~~~
* Frames are recorded only when ``co_filename`` matches the target file
  **and** the frame sits under an invocation of ``target_code`` (walk
  ``f_back``).  This skips stdlib / site-packages and unrelated same-file
  helpers that are not on the call stack under the traced entrypoint.
* Globals are filtered to a lightweight subset (see ``_filter_globals``).
* The previous trace function is restored on :meth:`stop`, so nested
  ``rewindr`` / ``rewind_context`` usage composes correctly.
* :meth:`copy.copy` is used for locals so mutable containers reflect the
  state at capture time without full deep copies.
* On an ``exception`` trace event, tracing is stopped automatically to
  avoid recording unrelated frames during unwinding.
"""

from __future__ import annotations

import copy
import sys
import time
from types import CodeType, FrameType
from typing import Any, Callable, Optional

from .buffer import RingBuffer
from .snapshot import Snapshot
from .utils import same_filepath


def _filter_globals(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Return a lightweight subset of a globals dict.

    Excludes:
    - dunder names (``__name__``, ``__builtins__``, …)
    - callable objects (functions, classes) — they don't change
      meaningfully between steps and are expensive to copy.
    - module objects — not copyable and rarely interesting as state.
    - anything that raises on copy (silently skipped).
    """
    import types as std_types

    result: dict[str, Any] = {}
    for k, v in raw.items():
        if k.startswith("__"):
            continue
        if callable(v):
            continue
        if isinstance(v, std_types.ModuleType):
            continue
        try:
            result[k] = copy.copy(v)
        except Exception:
            pass  # skip un-copyable values
    return result


class TraceRecorder:
    """
    Installs and manages a ``sys.settrace`` hook for a single tracing session.

    Parameters
    ----------
    buffer:
        Pre-constructed RingBuffer where Snapshots will be stored.
    target_filename:
        Absolute path of the source file that contains ``target_code``.
    target_func_name:
        Human-readable name (``__name__``) used in snapshots.
    target_code:
        Code object whose dynamic extent (itself and callees on the same
        stack) may produce snapshots.

    Thread safety
    --------------
    ``sys.settrace`` is *per-thread*.  Do not share one TraceRecorder
    across threads.
    """

    def __init__(
        self,
        buffer: RingBuffer,
        target_filename: str,
        target_func_name: str,
        target_code: CodeType,
    ) -> None:
        self._buffer = buffer
        self._target_filename = target_filename
        self._target_func_name = target_func_name
        self._target_code: CodeType = target_code

        self._step: int = 0
        self._active: bool = False
        self._exception: Optional[BaseException] = None
        self._prev_trace: Optional[Callable[..., Any]] = None

    def start(self) -> None:
        """Install the trace hook and begin recording."""
        if self._active:
            return
        self._active = True
        self._prev_trace = sys.gettrace()
        sys.settrace(self._global_tracer)

    def stop(self) -> None:
        """
        Uninstall the trace hook and restore the previous tracer.

        Safe to call multiple times; subsequent calls are no-ops.
        """
        if not self._active:
            return
        self._active = False
        sys.settrace(self._prev_trace)

    @property
    def exception(self) -> Optional[BaseException]:
        """The exception that terminated tracing, or None if clean exit."""
        return self._exception

    @property
    def step_count(self) -> int:
        """Total number of snapshots captured (including evicted ones)."""
        return self._step

    def _under_target(self, frame: FrameType | None) -> bool:
        """True if walking ``f_back`` from *frame* reaches ``target_code``."""
        f: FrameType | None = frame
        while f is not None:
            if f.f_code is self._target_code:
                return True
            f = f.f_back
        return False

    def _frame_is_instrumentable(self, frame: FrameType) -> bool:
        if not same_filepath(frame.f_code.co_filename, self._target_filename):
            return False
        return self._under_target(frame)

    def _global_tracer(
        self,
        frame: FrameType,
        event: str,
        arg: Any,
    ) -> Optional[Callable[..., Any]]:
        if not self._active:
            return None

        if event == "call" and self._frame_is_instrumentable(frame):
            return self._local_tracer

        return self._global_tracer

    def _local_tracer(
        self,
        frame: FrameType,
        event: str,
        arg: Any,
    ) -> Optional[Callable[..., Any]]:
        if not self._active:
            return None

        if not self._frame_is_instrumentable(frame):
            return None

        if event == "line":
            self._capture(frame, "line")

        elif event == "exception":
            exc_value: BaseException = arg[1]
            if self._exception is None:
                self._exception = exc_value
            self._capture(frame, "exception")
            self.stop()

        elif event == "return":
            self._capture(frame, "return")
            return None

        return self._local_tracer

    def _capture(self, frame: FrameType, event: str) -> None:
        """Build a Snapshot from the current frame state and push it."""
        safe_locals: dict[str, Any] = {}
        for k, v in frame.f_locals.items():
            try:
                safe_locals[k] = copy.copy(v)
            except Exception:
                safe_locals[k] = repr(v)

        snapshot = Snapshot(
            step=self._step,
            line_no=frame.f_lineno,
            locals=safe_locals,
            globals=_filter_globals(frame.f_globals),
            timestamp=time.monotonic(),
            filename=frame.f_code.co_filename,
            func_name=frame.f_code.co_name,
            event=event,
        )
        self._buffer.push(snapshot)
        self._step += 1
