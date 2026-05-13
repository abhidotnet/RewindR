"""
utils.py
--------
Small, stateless helper functions shared across the rewindr package.
"""

from __future__ import annotations

import inspect
import linecache
import os
from typing import Any


_UNDEFINED = object()  # sentinel for "variable did not exist"


def same_filepath(a: str, b: str) -> bool:
    """Return True if *a* and *b* refer to the same source file path."""
    if a == "<unknown>" or b == "<unknown>":
        return a == b
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def unified_diff_locals(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """
    Compute a variable-level diff between two locals dicts.

    Parameters
    ----------
    before, after:
        Snapshots of ``frame.f_locals`` at two different steps.

    Returns
    -------
    dict
        Keys are variable names whose value differed.  Each entry is
        ``{"before": <value or <undefined>>, "after": <value or <undefined>>}``.

    Notes
    -----
    Comparison uses ``!=`` so numpy arrays and other objects that
    implement ``__eq__`` element-wise will need special handling by the
    caller.  For maximum safety we wrap the comparison in a try/except.
    """
    changed: dict[str, dict[str, Any]] = {}
    all_keys = set(before) | set(after)

    for key in all_keys:
        val_before = before.get(key, _UNDEFINED)
        val_after = after.get(key, _UNDEFINED)

        try:
            same = val_before is val_after or val_before == val_after
        except Exception:
            # Objects with broken __eq__; treat as different
            same = False

        if not same:
            changed[key] = {
                "before": val_before if val_before is not _UNDEFINED else "<undefined>",
                "after": val_after if val_after is not _UNDEFINED else "<undefined>",
            }

    return changed


def resolve_filename(func: Any) -> str:
    """
    Return the absolute source filename for *func*.

    Falls back to ``<unknown>`` if the source cannot be determined
    (e.g. for built-ins or functions defined in a REPL).
    """
    try:
        raw = inspect.getfile(func)
        return os.path.abspath(raw)
    except (TypeError, OSError):
        return "<unknown>"


def clamp(value: int, lo: int, hi: int) -> int:
    """Return *value* clamped to the inclusive range [lo, hi]."""
    return max(lo, min(value, hi))


def source_line_preview(
    filename: str,
    line_no: int,
    *,
    max_len: int = 72,
) -> str:
    """
    Return a single stripped source line for display, or empty if unavailable.

    Uses :mod:`linecache` so callers need not open files manually.
    """
    if not filename or filename == "<unknown>" or line_no < 1:
        return ""
    text = linecache.getline(filename, line_no)
    stripped = text.strip()
    if not stripped:
        return ""
    if len(stripped) <= max_len:
        return stripped
    return stripped[: max_len - 1] + "…"


def format_diff_locals(delta: dict[str, dict[str, Any]]) -> str:
    """
    Pretty-print the dict returned by :meth:`~rewindr.session.RewindSession.diff`.
    """
    if not delta:
        return "(no differing locals)"
    lines: list[str] = []
    for name in sorted(delta):
        change = delta[name]
        lines.append(f"  {name}: {change['before']!r} → {change['after']!r}")
    return "\n".join(lines)


def format_snapshot_locals(locals_: dict[str, Any], max_vars: int = 10) -> str:
    """
    Return a compact string representation of a locals dict.

    Parameters
    ----------
    locals_:
        The locals dict from a Snapshot.
    max_vars:
        Maximum number of variables to include before truncating.
    """
    items = list(locals_.items())[:max_vars]
    parts = [f"{k}={v!r}" for k, v in items]
    suffix = f" … (+{len(locals_) - max_vars} more)" if len(locals_) > max_vars else ""
    return "{" + ", ".join(parts) + suffix + "}"
