# rewindR

**rewindR** (`import rewindr`) is a small, pure-Python helper for *lightweight time-travel debugging*: it records shallow snapshots of local (and filtered global) state as your code runs, keeps only the most recent *N* steps in a ring buffer, and hands you a **`RewindSession`** after the call finishes or after an exception—so you can inspect earlier states without re-running the function.

## Why time-travel debugging?

When something fails deep inside a loop or a long function, the stack trace shows *where* you crashed, not *how* you got there. A short history of variable assignments (line number + `locals()` + timestamp) answers questions like: “What was `i` two iterations ago?”, “When did this list become empty?”, or “What changed between the last two executed lines?”—without sprinkling `print` everywhere or restarting under a heavy debugger.

## Installation

From the repository root (editable install):

```bash
pip install -e ".[dev]"
```

Or once published:

```bash
pip install rewindR
```

Requires **Python 3.10+**. There are **no C extensions**—everything uses the interpreter’s tracing hooks.

## Quickstart

```python
from rewindr import rewindr

@rewindr(steps=100)
def risky(n: int) -> float:
    acc = 0.0
    for i in range(n):
        acc += 1.0 / (n - i)  # ZeroDivisionError on last iteration when n>0
    return acc

session = risky(3)

print(session.summary())
print(session.rewind(1).locals)   # one step before the last snapshot
print(session.diff(-2, -1))       # what changed between the last two steps
```

## Decorator usage

- **`@rewindr`** — uses the default ring buffer size (50).
- **`@rewindr(steps=200)`** — keep the last 200 snapshots.

The wrapped function is invoked for side effects; the **return value of the wrapper is always a `RewindSession`**, not the original function’s return value. On a **clean run**, `session.exception` is `None`. If the wrapped function raises, the **exception is swallowed** and the same `RewindSession` is returned so you can assign `session = my_func(...)` without a `try`/`except` block. The exception object is still attached on **`rewind_session`** for compatibility with tools that catch by type.

```python
from rewindr import rewindr, get_session_from_exception

@rewindr(steps=50)
def boom() -> None:
    x = 1
    y = 0
    _ = x / y

session = boom()
assert isinstance(session.exception, ZeroDivisionError)
exc = session.exception
assert get_session_from_exception(exc) is session
print(session.rewind(0).locals)
```

## Context manager usage

You can trace an arbitrary block in the **caller function** with either API:

```python
from rewindr import rewind_context, rewindr

with rewind_context(steps=50) as ref:
    a = 1
    b = a + 1

session = ref.session

with rewindr(steps=50) as ref2:
    c = b + 1

session2 = ref2.session
```

After the block, **`ref.session`** is populated. If the block raises, the session is still stored on **`ref.session`**, and the same object is attached to the exception under **`rewind_session`**.

## Inspecting snapshots

Each **`Snapshot`** includes:

- **`line_no`** — current line in the traced frame.
- **`locals`** — shallow `copy.copy` per name where possible; otherwise `repr(...)`.
- **`globals`** — filtered shallow snapshot (no dunders, callables, or modules).
- **`timestamp`** — `time.monotonic()` at capture (relative timing, not wall clock).
- **`event`** — `"line"`, `"call"`, `"return"`, or `"exception"`.

`RewindSession.history` is ordered **oldest → newest**.

## Diffing snapshots

```python
delta = session.diff(0, -1)  # supports negative indices like list indexing
for name, change in delta.items():
    print(name, change["before"], "->", change["after"])
```

Only bindings that differ (by `==`, with a safe fallback) appear. Missing names show as `"<undefined>"`.

## Performance notes

- Tracing uses **`sys.settrace`**, which has **significant overhead**—suitable for debugging hotspots, tests, or narrow code paths—not production servers.
- Snapshots use **shallow copies** of locals to balance fidelity and cost; deeply nested structures are **not** deep-copied.
- The ring buffer caps memory; increase **`steps`** only as needed.

## Limitations

- **Per-thread** tracing (`sys.settrace`); multi-threaded code is only traced on the thread where the recorder runs.
- **No async** (`async`/`await`) story yet; tracing async coroutines is subtle and not a goal of v0.1.
- **Filtered globals** and **best-effort locals** (`copy.copy` / `repr`) mean some objects may be incomplete or expensive.
- **Context manager** scope is the **containing function**’s code object (the `with` lives in that frame); you cannot narrow to “only lines inside the `with`” without AST rewriting.
- **Security**: snapshots may contain secrets from locals—treat sessions like logs.

## Roadmap

- Optional **deep-copy** strategies and size budgets per snapshot.
- **Richer diff** (recursive dict/list diff, custom comparators).
- **Async** and **thread** helpers.
- **Optional** `sys.setprofile` mode for lower granularity / different trade-offs.
- **Serialization** of `RewindSession` for CI artifacts.

## Development

```bash
python -m pytest rewindr/tests -q
python rewindr/examples/basic_usage.py
```

## License

MIT (see `pyproject.toml`).
