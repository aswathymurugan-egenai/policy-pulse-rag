"""Idempotent update of one key in a dotenv file."""

import os
import re
import tempfile
from pathlib import Path


def upsert_env_value(path: Path, key: str, value: str) -> None:
    """Set `key=value` in the file, creating it if needed.

    Other lines and comments stay as they are. The file is rewritten through a temporary file and a
    rename, and only when the content changes, so running it twice leaves the bytes identical.
    """
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    updated = _with_value(original, key, value)
    if updated == original and path.exists():
        return
    _write_atomically(path, updated)


def _with_value(text: str, key: str, value: str) -> str:
    assignment = f"{key}={value}"
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=.*$")
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if pattern.match(line):
            lines[index] = assignment
            return "\n".join(lines) + "\n"
    lines.append(assignment)
    return "\n".join(lines) + "\n"


def _write_atomically(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f"{path.name}.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
