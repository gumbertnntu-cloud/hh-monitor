from __future__ import annotations

import sys
from pathlib import Path


def _ensure_src_on_path() -> None:
    root = Path(__file__).resolve().parent.parent
    src = root / "src"
    if src.exists():
        sys.path.insert(0, str(src))


_ensure_src_on_path()


def _run() -> int:
    from hh_monitor.app import main

    return main()


if __name__ == "__main__":
    raise SystemExit(_run())
