"""
exceptions.py
-------------
Custom exception hierarchy for the rewindr package.

All rewindr exceptions derive from RewindrError so callers can catch the
whole family with a single ``except RewindrError`` clause if desired.
"""

from __future__ import annotations


class RewindrError(Exception):
    """Base class for all rewindr exceptions."""


class RewindIndexError(RewindrError, IndexError):
    """
    Raised when :py:meth:`~rewindr.session.RewindSession.rewind` or
    :py:meth:`~rewindr.session.RewindSession.at` receives an out-of-range
    step index.
    """


class TracerAlreadyActiveError(RewindrError):
    """
    Raised when :py:meth:`~rewindr.tracer.TraceRecorder.start` is called
    on a recorder that is already recording.
    """


class NoHistoryError(RewindrError):
    """
    Raised when an operation requires at least one snapshot but the
    history is empty (e.g. the traced function returned immediately).
    """


class ConfigurationError(RewindrError):
    """
    Raised for invalid configuration values, such as a non-positive
    ``steps`` argument.
    """
