"""Crash- and concurrency-safe file writing shared by the file-backed stores.

A plain `Path.write_text` truncates the target before writing, so a crash
mid-write (or two concurrent writes) can leave a half-written file behind —
for the JSON roster that means every later read raises JSONDecodeError.
Writing a sibling temp file and then `os.replace`-ing it into place makes
the swap atomic on POSIX and Windows alike: readers see either the old
file or the new one, never a truncated one.
"""
from __future__ import annotations

import os
import pathlib
import tempfile


def atomic_write_text(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Same directory as the target, so os.replace stays on one filesystem.
    handle, temp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_name, path)
    except BaseException:
        pathlib.Path(temp_name).unlink(missing_ok=True)
        raise
