"""
Comprehensive pytest suite for the rewindr package.

Run from project root::

    python -m pytest rewindr/tests -q
"""

from __future__ import annotations

import sys
import time
from typing import Any

import pytest

from rewindr import (
    REWIND_SESSION_ATTR,
    ConfigurationError,
    RingBuffer,
    RewindIndexError,
    RewindSession,
    Snapshot,
    TraceRecorder,
    get_session_from_exception,
    rewind_context,
    rewindr,
)
from rewindr.utils import unified_diff_locals


def _dummy_code() -> Any:
    return (lambda: None).__code__


# ---------------------------------------------------------------------------
# RingBuffer
# ---------------------------------------------------------------------------


class TestRingBuffer:
    def _make_snap(self, step: int) -> Snapshot:
        return Snapshot(
            step=step,
            line_no=step + 10,
            locals={"i": step},
            globals={},
            timestamp=time.monotonic(),
            filename="<test>",
            func_name="test",
        )

    def test_basic_push_and_freeze(self) -> None:
        buf = RingBuffer(maxlen=5)
        for i in range(3):
            buf.push(self._make_snap(i))
        history = buf.freeze()
        assert len(history) == 3
        assert history[0].step == 0
        assert history[-1].step == 2

    def test_eviction_when_full(self) -> None:
        buf = RingBuffer(maxlen=3)
        for i in range(5):
            buf.push(self._make_snap(i))
        history = buf.freeze()
        assert len(history) == 3
        assert buf.evicted == 2
        assert history[0].step == 2

    def test_total_pushed_counter(self) -> None:
        buf = RingBuffer(maxlen=3)
        for i in range(7):
            buf.push(self._make_snap(i))
        assert buf.total_pushed == 7

    def test_clear_resets_state(self) -> None:
        buf = RingBuffer(maxlen=5)
        for i in range(3):
            buf.push(self._make_snap(i))
        buf.clear()
        assert len(buf) == 0
        assert buf.total_pushed == 0

    def test_invalid_maxlen_raises(self) -> None:
        with pytest.raises(ValueError):
            RingBuffer(maxlen=0)

    def test_getitem(self) -> None:
        buf = RingBuffer(maxlen=5)
        for i in range(3):
            buf.push(self._make_snap(i))
        assert buf[0].step == 0
        assert buf[-1].step == 2

    def test_is_full(self) -> None:
        buf = RingBuffer(maxlen=2)
        assert not buf.is_full()
        buf.push(self._make_snap(0))
        assert not buf.is_full()
        buf.push(self._make_snap(1))
        assert buf.is_full()


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


class TestSnapshot:
    def _snap(self, step: int = 0, locals_: dict[str, Any] | None = None) -> Snapshot:
        return Snapshot(
            step=step,
            line_no=42,
            locals=locals_ or {"x": 1, "y": 2},
            globals={},
            timestamp=time.monotonic(),
            filename="test.py",
            func_name="my_func",
        )

    def test_get_local_present(self) -> None:
        s = self._snap(locals_={"n": 10})
        assert s.get_local("n") == 10

    def test_get_local_missing_default(self) -> None:
        s = self._snap()
        assert s.get_local("missing", default=99) == 99

    def test_local_names_sorted(self) -> None:
        s = self._snap(locals_={"z": 3, "a": 1, "m": 2})
        assert s.local_names() == ["a", "m", "z"]

    def test_age_increases(self) -> None:
        s = self._snap()
        time.sleep(0.01)
        assert s.age() > 0

    def test_frozen_immutable(self) -> None:
        s = self._snap()
        with pytest.raises((AttributeError, TypeError)):
            s.step = 99  # type: ignore[misc]

    def test_str_is_human_readable(self) -> None:
        s = self._snap(locals_={"n": 7})
        out = str(s)
        assert "Locals:" in out
        assert "n=7" in out


# ---------------------------------------------------------------------------
# Utils
# ---------------------------------------------------------------------------


class TestUnifiedDiffLocals:
    def test_no_change(self) -> None:
        d = {"x": 1, "y": [1, 2]}
        assert unified_diff_locals(d, d) == {}

    def test_value_changed(self) -> None:
        result = unified_diff_locals({"x": 1}, {"x": 2})
        assert result == {"x": {"before": 1, "after": 2}}

    def test_key_added(self) -> None:
        result = unified_diff_locals({}, {"new": 42})
        assert result == {"new": {"before": "<undefined>", "after": 42}}

    def test_key_removed(self) -> None:
        result = unified_diff_locals({"old": 7}, {})
        assert result == {"old": {"before": 7, "after": "<undefined>"}}

    def test_multiple_changes(self) -> None:
        before = {"a": 1, "b": 2, "c": 3}
        after = {"a": 1, "b": 99, "d": 4}
        result = unified_diff_locals(before, after)
        assert "a" not in result
        assert result["b"]["after"] == 99
        assert result["c"]["after"] == "<undefined>"
        assert result["d"]["before"] == "<undefined>"


# ---------------------------------------------------------------------------
# RewindSession
# ---------------------------------------------------------------------------


def _make_session(n: int = 5, with_exception: bool = False) -> RewindSession:
    snaps = [
        Snapshot(
            step=i,
            line_no=i + 10,
            locals={"i": i, "square": i * i},
            globals={},
            timestamp=time.monotonic(),
            filename="test.py",
            func_name="demo",
        )
        for i in range(n)
    ]
    exc: BaseException | None = ZeroDivisionError("division by zero") if with_exception else None
    return RewindSession(history=snaps, exception=exc)


class TestRewindSession:
    def test_rewind_zero_is_last(self) -> None:
        s = _make_session(5)
        snap = s.rewind(0)
        assert snap.step == 4

    def test_rewind_one_is_second_to_last(self) -> None:
        s = _make_session(5)
        snap = s.rewind(1)
        assert snap.step == 3

    def test_rewind_out_of_range(self) -> None:
        s = _make_session(3)
        with pytest.raises(RewindIndexError):
            s.rewind(10)

    def test_rewind_negative_raises(self) -> None:
        s = _make_session(3)
        with pytest.raises(RewindIndexError):
            s.rewind(-1)

    def test_at_positive_index(self) -> None:
        s = _make_session(5)
        assert s.at(0).step == 0
        assert s.at(4).step == 4

    def test_at_negative_index(self) -> None:
        s = _make_session(5)
        assert s.at(-1).step == 4

    def test_at_out_of_range(self) -> None:
        s = _make_session(3)
        with pytest.raises(RewindIndexError):
            s.at(99)

    def test_diff_detects_changes(self) -> None:
        s = _make_session(5)
        delta = s.diff(0, -1)
        assert "i" in delta
        assert delta["i"]["before"] == 0
        assert delta["i"]["after"] == 4

    def test_diff_no_change_same_index(self) -> None:
        s = _make_session(5)
        assert s.diff(0, 0) == {}

    def test_summary_contains_exception(self) -> None:
        s = _make_session(with_exception=True)
        summary = s.summary()
        assert "ZeroDivisionError" in summary

    def test_summary_clean_exit(self) -> None:
        s = _make_session(with_exception=False)
        assert "Finished without raising" in s.summary()

    def test_describe_diff_empty_explains(self) -> None:
        t = time.monotonic()
        s1 = Snapshot(0, 10, {"x": 1}, {}, t, "f.py", "f", "line")
        s2 = Snapshot(1, 10, {"x": 1}, {}, t, "f.py", "f", "line")
        s = RewindSession([s1, s2])
        text = s.describe_diff(0, 1)
        assert "No variables differ" in text
        assert "history index" in text.lower()
        assert "consecutive" in text.lower()

    def test_describe_diff_shows_changes(self) -> None:
        s = _make_session(5)
        text = s.describe_diff(0, -1)
        assert "i:" in text or "Changed variables" in text

    def test_len(self) -> None:
        s = _make_session(7)
        assert len(s) == 7

    def test_repr_shows_tail(self) -> None:
        s = _make_session(10)
        r = repr(s)
        assert "RewindSession" in r
        assert "last5=" in r


# ---------------------------------------------------------------------------
# @rewindr decorator
# ---------------------------------------------------------------------------


class TestRewindrDecorator:
    def test_clean_function_returns_session(self) -> None:
        @rewindr(steps=50)
        def add(a: int, b: int) -> int:
            result = a + b
            return result

        session = add(2, 3)
        assert isinstance(session, RewindSession)
        assert session.exception is None

    def test_exception_captured(self) -> None:
        @rewindr(steps=50)
        def boom(n: int) -> float:
            x = 1 / n
            return x

        session = boom(0)
        assert session.exception is not None
        assert isinstance(session.exception, ZeroDivisionError)

    def test_exception_has_session_attribute(self) -> None:
        @rewindr(steps=50)
        def boom() -> None:
            raise ValueError("x")

        session = boom()
        assert session.exception is not None
        assert getattr(session.exception, REWIND_SESSION_ATTR) is session
        assert get_session_from_exception(session.exception) is session

    def test_history_non_empty(self) -> None:
        @rewindr(steps=50)
        def loop(n: int) -> int:
            total = 0
            for i in range(n):
                total += i
            return total

        session = loop(5)
        assert len(session.history) > 0

    def test_locals_captured_correctly(self) -> None:
        @rewindr(steps=50)
        def assign() -> int:
            x = 10
            y = 20
            z = x + y
            return z

        session = assign()
        z_snaps = [s for s in session.history if "z" in s.locals]
        assert z_snaps
        assert z_snaps[-1].locals["z"] == 30

    def test_step_limit_respected(self) -> None:
        @rewindr(steps=5)
        def many_lines() -> None:
            a = 1
            b = 2
            c = 3
            d = 4
            e = 5
            f = 6
            g = 7
            h = 8
            i = 9
            j = 10

        session = many_lines()
        assert len(session.history) <= 5

    def test_invalid_steps_raises(self) -> None:
        with pytest.raises(ConfigurationError):
            rewindr(steps=0)

    def test_rewind_on_crash_site(self) -> None:
        @rewindr(steps=50)
        def crash() -> None:
            values = [1, 2, 3]
            _ = values[99]

        session = crash()
        crash_snap = session.rewind(0)
        assert crash_snap is not None

    def test_preserves_function_name(self) -> None:
        @rewindr(steps=10)
        def my_named_func() -> None:
            pass

        assert my_named_func.__name__ == "my_named_func"

    def test_bare_decorator_syntax(self) -> None:
        @rewindr
        def inc(x: int) -> int:
            return x + 1

        session = inc(1)
        assert isinstance(session, RewindSession)


# ---------------------------------------------------------------------------
# rewind_context & with rewindr(...)
# ---------------------------------------------------------------------------


class TestRewindContext:
    def test_basic_context(self) -> None:
        with rewind_context(steps=50) as ref:
            x = 1
            y = 2
            _ = x + y

        assert ref.session is not None
        assert isinstance(ref.session, RewindSession)

    def test_with_rewindr_context_manager(self) -> None:
        with rewindr(steps=50) as ref:
            a = 1
            b = a + 1
            _ = b * 2

        assert ref.session is not None
        assert isinstance(ref.session, RewindSession)

    def test_exception_in_context(self) -> None:
        ref_holder: dict[str, Any] = {}

        with pytest.raises(ZeroDivisionError):
            with rewind_context(steps=50) as ref:
                ref_holder["r"] = ref
                _ = 1 / 0

        ref = ref_holder["r"]
        assert ref.session is not None

    def test_invalid_steps_raises(self) -> None:
        with pytest.raises(ConfigurationError):
            rewind_context(steps=-1)

    def test_session_ref_repr_before(self) -> None:
        ctx = rewind_context(steps=10)
        ref = ctx.__enter__()
        assert "recording" in repr(ref)
        ctx.__exit__(None, None, None)

    def test_session_ref_repr_after(self) -> None:
        with rewind_context(steps=10) as ref:
            _ = 42
        assert "RewindSession" in repr(ref)


# ---------------------------------------------------------------------------
# TraceRecorder
# ---------------------------------------------------------------------------


class TestTraceRecorder:
    def test_stop_is_idempotent(self) -> None:
        buf = RingBuffer(maxlen=10)
        recorder = TraceRecorder(buf, "<test>", "f", target_code=_dummy_code())
        recorder.stop()
        recorder.stop()

    def test_start_stop_restores_trace(self) -> None:
        original = sys.gettrace()
        buf = RingBuffer(maxlen=10)
        recorder = TraceRecorder(buf, "<test>", "f", target_code=_dummy_code())
        recorder.start()
        recorder.stop()
        assert sys.gettrace() is original


# ---------------------------------------------------------------------------
# Edge cases: recursion & large locals
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_deep_recursion(self) -> None:
        @rewindr(steps=500)
        def loop_many() -> None:
            x = 0
            for i in range(200):
                x = i * i
            _ = x

        session = loop_many()
        assert isinstance(session, RewindSession)
        assert len(session.history) > 50

    def test_large_locals_dict(self) -> None:
        @rewindr(steps=30)
        def big() -> None:
            d = {f"k{i}": i for i in range(400)}
            _ = sum(d.values())

        session = big()
        assert len(session.history) >= 1
        last = session.rewind(0)
        assert "d" in last.locals
        assert isinstance(last.locals["d"], dict)
        assert len(last.locals["d"]) == 400
