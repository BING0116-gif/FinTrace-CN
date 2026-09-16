"""Smoke test: load every page of the read-only FinTrace-CN workbench and
ensure no exception escapes.  Drives the live ``streamlit`` runtime via
``streamlit.testing.v1.AppTest`` so any UI / data wiring regression is
caught before the user opens the app.

Run from the project root:

    .venv\\Scripts\\python.exe scripts\\smoke_workbench.py

Exit code is 0 when every page renders cleanly, 1 otherwise.
"""

from __future__ import annotations

import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
WORKBENCH = str(ROOT / "workbench.py")

# Must stay in sync with NAVIGATION in workbench.py
PAGES = [
    "案例演示",
    "AI Agent 研究",
    "研究总览",
    "市场与行情",
    "财务表现",
    "同行估值",
    "证据与校验",
    "Agent 执行轨迹",
    "研究报告",
    "研究任务",
    "评测与消融",
    "每日复盘",
]


def _check_snapshots() -> None:
    """Print a heads-up if no research / market snapshots are available.

    Pages will still render, but with empty / "未覆盖" placeholders, which
    is the expected behaviour for a fresh checkout.
    """
    snap_dir = ROOT / "data" / "snapshots" / "cn"
    market_dir = ROOT / "data" / "snapshots" / "market"
    research = len(list(snap_dir.glob("*.json"))) if snap_dir.exists() else 0
    market = len(list(market_dir.glob("*.json"))) if market_dir.exists() else 0
    print(f"  · 快照: research={research}  market={market}  "
          f"(pages still render with 未覆盖 placeholders if 0)")


def main() -> int:
    print(f"Smoke test: {WORKBENCH}\n")
    _check_snapshots()
    print()

    fails: list[tuple[str, str]] = []
    for page in PAGES:
        at = AppTest.from_file(WORKBENCH, default_timeout=30)
        at.session_state["workbench_page"] = page
        at.run()
        if at.exception:
            err = at.exception[0]
            fails.append((page, f"{type(err.value).__name__}: {err.value}"))
            print(f"[FAIL] {page}")
            print(f"        → {type(err.value).__name__}: {err.value}")
        else:
            print(f"[ OK ] {page}")

    total = len(PAGES)
    passed = total - len(fails)
    print(f"\n{passed}/{total} pages clean")
    if fails:
        print("\nFailures:")
        for page, msg in fails:
            print(f"  - {page}: {msg}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
