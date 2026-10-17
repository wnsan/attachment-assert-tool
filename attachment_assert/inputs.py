"""Accept paths, bytes, file objects and Playwright Download objects as candidates."""
from __future__ import annotations

import inspect
import os
import tempfile
from pathlib import Path


def _suggested_name(obj) -> str | None:
    name = getattr(obj, "suggested_filename", None)
    if callable(name):  # some wrappers expose it as a method
        name = name()
    return name if isinstance(name, str) and name else None


def materialize(candidate, name: str | None = None) -> tuple[Path, str]:
    """Return (path on disk, display name) for *candidate*.

    Supported: str / os.PathLike, bytes / bytearray / memoryview, binary file objects,
    and Playwright *sync* ``Download`` objects (anything with ``.path()`` / ``.save_as()``).
    """
    if isinstance(candidate, (str, os.PathLike)):
        p = Path(candidate)
        return p, name or p.name

    if isinstance(candidate, (bytes, bytearray, memoryview)):
        return _write_temp(bytes(candidate), name or "candidate"), name or "candidate"

    if hasattr(candidate, "read") and callable(candidate.read):
        data = candidate.read()
        if inspect.isawaitable(data):
            raise TypeError("async file objects are not supported; read the bytes first")
        fname = name or os.path.basename(getattr(candidate, "name", "") or "") or "candidate"
        return _write_temp(data, fname), fname

    if hasattr(candidate, "save_as") or hasattr(candidate, "path"):
        fname = name or _suggested_name(candidate) or "download"
        saver = getattr(candidate, "save_as", None)
        if callable(saver):
            target = Path(tempfile.mkdtemp(prefix="attachment_assert_")) / fname
            res = saver(str(target))
            if inspect.isawaitable(res):
                res.close()
                raise TypeError(
                    "got an async Playwright Download; use `await assert_matches_async(...)` "
                    "or pass `await download.path()`"
                )
            return target, fname
        res = candidate.path()
        if inspect.isawaitable(res):
            res.close()
            raise TypeError("got an async Playwright Download; use `await assert_matches_async(...)`")
        return Path(res), fname

    raise TypeError(f"unsupported candidate type: {type(candidate).__name__}")


async def amaterialize(candidate, name: str | None = None) -> tuple[Path, str]:
    """Async variant: also accepts Playwright *async* ``Download`` objects."""
    saver = getattr(candidate, "save_as", None)
    if callable(saver) and inspect.iscoroutinefunction(saver):
        fname = name or _suggested_name(candidate) or "download"
        target = Path(tempfile.mkdtemp(prefix="attachment_assert_")) / fname
        await saver(str(target))
        return target, fname
    return materialize(candidate, name)


def _write_temp(data: bytes, fname: str) -> Path:
    folder = Path(tempfile.mkdtemp(prefix="attachment_assert_"))
    path = folder / (os.path.basename(fname) or "candidate")
    path.write_bytes(data)
    return path
