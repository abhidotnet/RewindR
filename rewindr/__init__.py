"""
rewindr
=======
Lightweight time-travel debugging for Python.

Provides a decorator and context manager that snapshot local variable state
at every executed source line, store those snapshots in a configurable ring
buffer, and expose them for post-mortem inspection after an exception — or
after a clean exit — without re-running the code.

Quick start
-----------
**Decorator**::

    from rewindr import rewindr

    @rewindr(steps=100)
    def process(data):
        for i, item in enumerate(data):
            result = transform(item)   # crashes on bad input
        return result

    session = process(my_data)

    if session.exception:
        print(session.summary())
        crashed_at  = session.rewind(0)   # last snapshot (crash site)
        one_before  = session.rewind(1)   # one line before
        print(session.diff(-3, -1))       # what changed over last 2 steps

**Context manager**::

    from rewindr import rewind_context

    with rewind_context(steps=200) as ref:
        risky_code()

    session = ref.session
    print(session.summary())

Public API
----------
- :func:`rewindr`              — decorator factory and ``with`` manager
- :func:`rewind_context`       — context-manager factory (alias pattern)
- :class:`RewindSession`       — history navigation & diff
- :class:`Snapshot`            — single captured execution state
- :class:`RingBuffer`          — fixed-capacity snapshot buffer
- :class:`TraceRecorder`       — low-level sys.settrace engine
- :exc:`RewindrError`          — base exception class
- :exc:`RewindIndexError`      — out-of-range step index
- :exc:`ConfigurationError`    — invalid configuration value
"""

from .buffer import RingBuffer
from .context import (
    REWIND_SESSION_ATTR,
    SessionRef,
    get_session_from_exception,
    rewind_context,
)
from .decorator import RewindConfigurable, rewindr
from .exceptions import (
    ConfigurationError,
    NoHistoryError,
    RewindIndexError,
    RewindrError,
    TracerAlreadyActiveError,
)
from .session import RewindSession
from .snapshot import Snapshot
from .tracer import TraceRecorder

__all__ = [
    "rewindr",
    "RewindConfigurable",
    "rewind_context",
    "RewindSession",
    "SessionRef",
    "Snapshot",
    "RingBuffer",
    "TraceRecorder",
    "RewindrError",
    "RewindIndexError",
    "ConfigurationError",
    "NoHistoryError",
    "TracerAlreadyActiveError",
    "REWIND_SESSION_ATTR",
    "get_session_from_exception",
]

__version__ = "0.1.0"
__author__ = "rewindr contributors"
