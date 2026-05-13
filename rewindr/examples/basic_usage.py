"""
examples/basic_usage.py
-----------------------
Demonstrates the core rewindr API:
  1. @rewindr decorator catching a ZeroDivisionError
  2. rewind_context() tracing a block of code
  3. .diff() to inspect what changed between two steps
"""

from __future__ import annotations

from rewindr import rewind_context, rewindr


# ---------------------------------------------------------------------------
# Example 1 — Decorator: catch a ZeroDivisionError mid-loop
# ---------------------------------------------------------------------------


@rewindr(steps=100)
def compute_ratios(values: list[float]) -> list[float]:
    """Compute 1/x for each value in the list."""
    results: list[float] = []
    for i, val in enumerate(values):
        ratio = 1.0 / val
        results.append(ratio)
    return results


def demo_decorator() -> None:
    print("=" * 60)
    print("Demo 1: @rewindr decorator")
    print("=" * 60)

    data = [4.0, 2.0, 0.0, 1.0]
    session = compute_ratios(data)

    print(session.summary())
    print()

    if session.exception:
        crash = session.rewind(0)
        print(f"Crash at line {crash.line_no}:")
        print(f"  locals = {crash.locals}")
        print()

        if len(session.history) >= 2:
            delta = session.diff(-2, -1)
            print("Variables that changed in the final step:")
            for name, change in delta.items():
                print(f"  {name}: {change['before']!r} → {change['after']!r}")


# ---------------------------------------------------------------------------
# Example 2 — Context manager: trace a block
# ---------------------------------------------------------------------------


def demo_context() -> None:
    print()
    print("=" * 60)
    print("Demo 2: rewind_context()")
    print("=" * 60)

    try:
        with rewind_context(steps=50) as ref:
            total = 0
            for i in range(5):
                total += i
            bad = total / 0
    except ZeroDivisionError:
        pass

    session = ref.session
    assert session is not None
    print(session.summary())
    print()
    print(f"Total snapshots captured: {len(session)}")
    if session.evicted:
        print(f"  ({session.evicted} additional snapshots were evicted)")


# ---------------------------------------------------------------------------
# Example 3 — diff() walkthrough
# ---------------------------------------------------------------------------


@rewindr(steps=200)
def build_list(n: int) -> None:
    """Incrementally build a list; inspect state evolution with diff()."""
    items: list[int] = []
    for i in range(n):
        items.append(i * i)
    _ = sum(items)


def demo_diff() -> None:
    print()
    print("=" * 60)
    print("Demo 3: .diff() walkthrough")
    print("=" * 60)

    session = build_list(4)
    print(f"Captured {len(session)} snapshots.\n")

    if len(session) >= 2:
        mid = len(session) // 2
        delta = session.diff(0, mid)
        print(f"Diff between snapshot 0 and snapshot {mid}:")
        if delta:
            for name, change in delta.items():
                print(f"  {name!r}: {change['before']!r} → {change['after']!r}")
        else:
            print("  (no differences)")


if __name__ == "__main__":
    demo_decorator()
    demo_context()
    demo_diff()
