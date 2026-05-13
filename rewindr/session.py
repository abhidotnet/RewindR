"""
session.py
----------
RewindSession — the object handed back to the caller after tracing ends.

It wraps the frozen list of Snapshots and exposes a human-friendly API
for navigating backwards through execution history and diffing variable
state between two steps.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from .exceptions import RewindIndexError
from .snapshot import Snapshot
from .utils import (
    format_diff_locals,
    format_snapshot_locals,
    source_line_preview,
    unified_diff_locals,
)


class RewindSession:
    """
    A post-mortem view of a traced execution.

    Attributes
    ----------
    history:
        Ordered list of Snapshots (oldest index 0 → newest index -1).
        If the ring buffer was full the very oldest steps are absent;
        ``evicted`` tells you how many were dropped.
    exception:
        The exception that terminated the function, or ``None`` on a
        clean return.
    evicted:
        Number of snapshots that were dropped because the ring buffer
        was too small.  If non-zero, consider raising ``steps=``.

    Examples
    --------
    >>> @rewindr(steps=100)
    ... def buggy(n):
    ...     for i in range(n):
    ...         result = 1 / (n - i)   # ZeroDivisionError when i == n
    ...     return result
    ...
    >>> session = buggy(5)
    >>> session.rewind(1)         # snapshot one step before the crash
    >>> session.diff(-3, -1)      # what changed in the last two steps
    """

    def __init__(
        self,
        history: list[Snapshot],
        exception: Optional[BaseException] = None,
        evicted: int = 0,
    ) -> None:
        self.history: list[Snapshot] = history
        self.exception: Optional[BaseException] = exception
        self.evicted: int = evicted

    def rewind(self, n: int) -> Snapshot:
        """
        Return the snapshot *n* steps back from the most recent one.

        ``rewind(0)`` → last snapshot (crash site).
        ``rewind(1)`` → one step before that.

        Parameters
        ----------
        n:
            Non-negative integer.  Must be < ``len(history)``.

        Raises
        ------
        RewindIndexError
            If *n* is out of range.
        """
        if not self.history:
            raise RewindIndexError("History is empty — nothing to rewind to.")
        if n < 0:
            raise RewindIndexError(f"n must be non-negative, got {n}.")
        if n >= len(self.history):
            raise RewindIndexError(
                f"Cannot rewind {n} steps; only {len(self.history)} snapshots available."
            )
        return self.history[-(n + 1)]

    def at(self, step: int) -> Snapshot:
        """
        Return the snapshot at absolute index *step* (0 = oldest).

        Parameters
        ----------
        step:
            Index into ``history``.  Negative indexing is supported
            (``-1`` = newest).

        Raises
        ------
        RewindIndexError
            If *step* is out of range.
        """
        try:
            return self.history[step]
        except IndexError:
            raise RewindIndexError(
                f"Step {step} is out of range for history of length {len(self.history)}."
            ) from None

    def diff(self, a: int, b: int) -> dict[str, dict[str, Any]]:
        """
        Compare local variable state between two snapshots.

        Returns a dict mapping variable names that *changed* between
        snapshot *a* and snapshot *b* to ``{"before": …, "after": …}``.
        Variables that appear in only one snapshot are included with the
        other side set to ``<undefined>``.

        Parameters
        ----------
        a, b:
            Indices into ``history`` (supports negative indexing).

        Returns
        -------
        dict
            ``{var_name: {"before": value_at_a, "after": value_at_b}}``
            Empty dict if the two snapshots have identical locals.

        Examples
        --------
        >>> delta = session.diff(0, -1)
        >>> for name, change in delta.items():
        ...     print(f"{name}: {change['before']!r} → {change['after']!r}")
        """
        snap_a = self.at(a)
        snap_b = self.at(b)
        return unified_diff_locals(snap_a.locals, snap_b.locals)

    def describe_diff(self, a: int, b: int) -> str:
        """
        Human-readable comparison of locals between two history indices.

        Use this when :meth:`diff` returns ``{}`` and you want confirmation
        of *what* was compared and *why* nothing changed.
        """
        snap_a = self.at(a)
        snap_b = self.at(b)
        ia = self.history.index(snap_a)
        ib = self.history.index(snap_b)
        delta = unified_diff_locals(snap_a.locals, snap_b.locals)

        def _one(idx: int, snap: Snapshot) -> str:
            base = os.path.basename(snap.filename) if snap.filename else snap.filename
            src = source_line_preview(snap.filename, snap.line_no, max_len=56)
            code = f" `{src}`" if src else ""
            return (
                f"  [{idx}] step={snap.step} line={snap.line_no} [{snap.event}] "
                f"{base}{code}"
            )

        header = [
            "Locals diff (shallow copy of frame.f_locals at each snapshot):",
            f"  From history index {ia} → {ib}  (step {snap_a.step} → {snap_b.step}).",
            _one(ia, snap_a),
            _one(ib, snap_b),
            "",
        ]
        if not delta:
            header.append("No variables differ between these two snapshots.")
            if (
                snap_a.line_no == snap_b.line_no
                and snap_a.event == snap_b.event
                and snap_a.step != snap_b.step
            ):
                header.append(
                    "They are consecutive captures at the same source line and event "
                    "(locals were identical both times — common right before/after a no-op step)."
                )
            elif snap_a.step == snap_b.step:
                header.append("Same snapshot index twice — nothing to compare.")
            return "\n".join(header)

        header.append("Changed variables:")
        header.append(format_diff_locals(delta))
        return "\n".join(header)

    def summary(self) -> str:
        """
        Return a compact human-readable summary of the session.

        Includes step count, exception info, and the last few snapshots.
        """
        n = len(self.history)
        lines: list[str] = [
            f"RewindSession — {n} snapshot(s) of traced lines/returns"
            + (f" ({self.evicted} oldest evicted — increase steps=)" if self.evicted else ""),
        ]
        if self.exception:
            lines.append(
                f"  ✗ Exception: {type(self.exception).__name__}: {self.exception}"
            )
        else:
            lines.append("  ✓ Finished without raising")

        if self.history:
            tail = self.history[-1]
            fn = tail.func_name
            src = os.path.basename(tail.filename) if tail.filename else tail.filename
            lines.append(f"  Traced: {fn}()  in  {src}")
        lines.extend(
            [
                "",
                "Legend: step = capture counter from the start of this run (0-based).",
                "        line = 1-based source line.  → = last snapshot (where tracing stopped).",
                "",
            ]
        )

        if not self.history:
            return "\n".join(lines)

        omitted = n - 5
        if omitted > 0:
            lines.append(f"… {omitted} earlier snapshot(s) not shown (showing last 5 of {n})")
        recent = self.history[-5:]
        total = n
        for i, snap in enumerate(recent):
            hist_idx = n - len(recent) + i
            snap_num = hist_idx + 1
            marker = "→" if snap is self.history[-1] else " "
            preview = source_line_preview(snap.filename, snap.line_no, max_len=64)
            if not preview:
                preview = "—"
            lines.append(
                f"  {marker} #{snap_num}/{total}  hist[{hist_idx}]  step={snap.step:4d}  "
                f"line={snap.line_no:4d}  [{snap.event:<8}]  {preview}"
            )
        return "\n".join(lines)

    def __repr__(self) -> str:  # noqa: D105
        exc_name = type(self.exception).__name__ if self.exception else "None"
        parts: list[str] = [
            f"<RewindSession len={len(self.history)} evicted={self.evicted} "
            f"exception={exc_name}"
        ]
        if self.history:
            parts.append(" last5=")
            tail = self.history[-5:]
            snap_bits = [
                f"(L{s.line_no},{s.event},{format_snapshot_locals(s.locals, max_vars=3)})"
                for s in tail
            ]
            parts.append(" | ".join(snap_bits))
        parts.append(">")
        return "".join(parts)

    def __len__(self) -> int:
        return len(self.history)
