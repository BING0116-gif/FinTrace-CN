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

# Legacy labels remain covered as a compatibility contract. Modular page paths
# below cover the redesign navigation registry.
PAGES = [
    "案例演示",
    "CARD-15 Demo",
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

# Modular redesign pages are exercised through Streamlit's real navigation
# runtime as well as the legacy compatibility labels above.
MODULAR_PAGE_PATHS = [
    "app_pages/overview.py",
    "app_pages/research_tasks.py",
    "app_pages/documents.py",
    "app_pages/financial_analysis.py",
    "app_pages/report_checker.py",
    "app_pages/valuation.py",
    "app_pages/memo.py",
    "app_pages/audit_replay.py",
    "app_pages/daily_review.py",
    "app_pages/evaluations.py",
    "app_pages/demo.py",
    "app_pages/card15_demo.py",
    "app_pages/legacy_compat.py",
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

    modular_at = AppTest.from_file(WORKBENCH, default_timeout=30)
    modular_at.session_state["selected_snapshot_id"] = "600519.SH_20260810_tushare_v1"
    modular_at.run()
    for page_path in MODULAR_PAGE_PATHS:
        modular_at.switch_page(page_path)
        modular_at.run()
        if modular_at.exception:
            err = modular_at.exception[0]
            fails.append((page_path, f"{type(err.value).__name__}: {err.value}"))
            print(f"[FAIL] {page_path}")
            print(f"        → {type(err.value).__name__}: {err.value}")
        else:
            print(f"[ OK ] {page_path}")

    total = len(PAGES) + len(MODULAR_PAGE_PATHS)
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
