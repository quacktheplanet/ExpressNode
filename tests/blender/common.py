"""Shared helpers for the in-Blender checks.

Each check script prints one line per check:

    EXPN|{"check": "...", "ok": true, "detail": "..."}

and `EXPN_DONE` at the end; `run_all.py` parses them. A script that dies
early is reported as failed by the runner (no EXPN_DONE).
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import traceback

REPO = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
for _p in (str(REPO), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_failed = []


def check(name: str, ok, detail="") -> bool:
    ok = bool(ok)
    if not ok:
        _failed.append(name)
    print("EXPN|" + json.dumps({"check": name, "ok": ok,
                                "detail": str(detail)}), flush=True)
    return ok


def guard(name: str, fn, *args, **kwargs):
    """Run fn; a raised exception becomes a failed check, not a crash."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001 - report everything
        check(name, False, f"{type(e).__name__}: {e}\n"
                           f"{traceback.format_exc(limit=6)}")
        return None


def register_addon():
    """Register the extension straight from the repo (expressnode.register()),
    the way Blender does after installing it."""
    import expressnode
    expressnode.register()
    return expressnode


def done():
    print(f"EXPN_DONE failed={len(_failed)}", flush=True)
