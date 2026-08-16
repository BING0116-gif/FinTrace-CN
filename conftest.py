"""Test bootstrap: keep the default temp dir usable under restricted sandboxes.

On some sandboxed local setups a leftover ``pytest-of-*`` subdir in the OS temp
root (``%LOCALAPPDATA%\\Temp``) carries permissions that make every
``tmp_path``-based test error with ``PermissionError`` regardless of the code
under test.  Separately, the runtime wraps ``os.remove``/``os.rmdir`` with a
bulk-delete safeguard that raises if too many files are removed in one turn;
that safeguard is intentionally skipped for paths *under* the OS temp root.

So we point ``tempfile.tempdir`` at a **unique per-run subdir of the OS temp
root**: deletions there bypass the safeguard (plain ``os.remove``), and the
fresh path sidesteps the stale ``pytest-of-*`` dir that triggers the permission
error.  The directory is freshly created (never force-cleaned), so reuse is
always safe and the offline suite stays hermetic and portable.
"""

from __future__ import annotations

import tempfile


try:
    _run = tempfile.mkdtemp(prefix="fintrace-pytest-", dir=tempfile.gettempdir())
    tempfile.tempdir = _run
except Exception:  # pragma: no cover - defensive only
    # Leave tempfile untouched; tests that need tmp will surface the underlying
    # environment issue rather than silently misbehaving.
    pass
