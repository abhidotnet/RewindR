"""
buffer.py
---------
Fixed-capacity ring buffer for Snapshot objects.

Uses collections.deque with maxlen so old snapshots are automatically
evicted when the buffer is full — zero allocation overhead on push.
"""

from __future__ import annotations

from collections import deque
from typing import Iterator

from .snapshot import Snapshot


class RingBuffer:
    """
    A fixed-capacity FIFO buffer that automatically drops the oldest
    entry when capacity is exceeded.

    Parameters
    ----------
    maxlen:
        Maximum number of snapshots to retain (default 50).
        When the buffer is full the oldest snapshot is silently discarded.

    Examples
    --------
    >>> buf = RingBuffer(maxlen=3)
    >>> for i in range(5):
    ...     buf.push(make_snapshot(i))   # only last 3 are kept
    >>> len(buf)
    3
    """

    def __init__(self, maxlen: int = 50) -> None:
        if maxlen < 1:
            raise ValueError(f"maxlen must be >= 1, got {maxlen}")
        self._maxlen: int = maxlen
        self._buffer: deque[Snapshot] = deque(maxlen=maxlen)
        self._total_pushed: int = 0  # ever-increasing; survives eviction

    def push(self, snapshot: Snapshot) -> None:
        """Append *snapshot* to the buffer, evicting the oldest if full."""
        self._buffer.append(snapshot)
        self._total_pushed += 1

    def freeze(self) -> list[Snapshot]:
        """
        Return an immutable ordered copy of current buffer contents
        (oldest → newest).  The buffer itself is not modified.
        """
        return list(self._buffer)

    def clear(self) -> None:
        """Discard all snapshots and reset internal counters."""
        self._buffer.clear()
        self._total_pushed = 0

    @property
    def maxlen(self) -> int:
        """Maximum capacity of the buffer."""
        return self._maxlen

    @property
    def total_pushed(self) -> int:
        """
        Total snapshots ever pushed (including evicted ones).
        Useful for diagnosing how much history was lost.
        """
        return self._total_pushed

    @property
    def evicted(self) -> int:
        """Number of snapshots silently dropped due to overflow."""
        return max(0, self._total_pushed - self._maxlen)

    def is_full(self) -> bool:
        """Return True when the buffer has reached capacity."""
        return len(self._buffer) == self._maxlen

    def __len__(self) -> int:
        return len(self._buffer)

    def __iter__(self) -> Iterator[Snapshot]:
        return iter(self._buffer)

    def __getitem__(self, index: int) -> Snapshot:
        """index 0 = oldest, index -1 = newest."""
        return self._buffer[index]

    def __repr__(self) -> str:  # noqa: D105
        return (
            f"<RingBuffer len={len(self)} maxlen={self._maxlen} "
            f"total_pushed={self._total_pushed}>"
        )
