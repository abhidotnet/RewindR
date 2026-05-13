"""
snapshot.py
-----------
Dataclass representing a single captured execution state.

Each Snapshot is an immutable record of what the interpreter saw
at one particular source line: the line number, a shallow copy of
locals/globals, a monotonic timestamp, and the source location.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from .utils import format_snapshot_locals, source_line_preview


@dataclass(frozen=True)
class Snapshot:
    """
    A frozen record of interpreter state at a single executed line.

    Attributes
    ----------
    step:       Monotonically increasing index within the session (0-based).
    line_no:    Source line number that was about to execute.
    locals:     Shallow copy of frame.f_locals at capture time.
    globals:    Filtered shallow copy of frame.f_globals (no dunders, no callables).
    timestamp:  time.monotonic() value at capture time.
    filename:   Absolute path of the source file being traced.
    func_name:  Name of the function (or '<module>') being traced.
    event:      Trace event type: 'line' | 'exception' | 'call' | 'return'.
    """

    step: int
    line_no: int
    locals: dict[str, Any]
    globals: dict[str, Any]
    timestamp: float
    filename: str
    func_name: str
    event: str = "line"

    def get_local(self, name: str, default: Any = None) -> Any:
        """Return the value of a local variable, or *default* if absent."""
        return self.locals.get(name, default)

    def local_names(self) -> list[str]:
        """Sorted list of local variable names captured in this snapshot."""
        return sorted(self.locals.keys())

    def age(self, reference: float | None = None) -> float:
        """
        Elapsed seconds between this snapshot and *reference* (defaults to now).
        Useful for building relative timelines.
        """
        ref = reference if reference is not None else time.monotonic()
        return ref - self.timestamp

    def describe(
        self,
        *,
        max_source: int = 78,
        max_vars: int = 14,
    ) -> str:
        """
        Multi-line, human-oriented description (used by :meth:`__str__`).
        """
        base = os.path.basename(self.filename) if self.filename else self.filename
        src = source_line_preview(self.filename, self.line_no, max_len=max_source)
        code = f"`{src}`" if src else "(source text unavailable - REPL, dynamic code, or missing file)"
        hints: dict[str, str] = {
            "line": "Interpreter reached this line; locals reflect state before it runs.",
            "return": "Returning from the function; locals include the value being returned.",
            "exception": "An exception was raised; tracing may stop after this snapshot.",
            "call": "A call is in progress at this frame.",
        }
        hint = hints.get(self.event, "Trace event recorded at this point.")
        lines = [
            f"Snapshot  step={self.step}  {base}:{self.line_no}  [{self.event}]  {self.func_name}()",
            f"  {hint}",
            f"  Code: {code}",
            f"  Locals: {format_snapshot_locals(self.locals, max_vars=max_vars)}",
        ]
        return "\n".join(lines)

    def __str__(self) -> str:  # noqa: D105
        return self.describe()

    def __repr__(self) -> str:  # noqa: D105
        local_preview = ", ".join(
            f"{k}={v!r}" for k, v in list(self.locals.items())[:4]
        )
        if len(self.locals) > 4:
            local_preview += ", ..."
        return (
            f"<Snapshot step={self.step} line={self.line_no} "
            f"func={self.func_name!r} locals=({local_preview})>"
        )
