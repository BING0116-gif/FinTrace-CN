"""Offline UI regression tests for the V2 interface redesign.

覆盖 UI_REDESIGN_PLAN_V2 §7：
- 导航注册表快照（业务 8 项 + 「高级」分组）；
- chip 组件不把裸 evidence ID 输出到明面（字符串断言）；
- 关键页面在 demo 快照下可离线渲染（快照缺失时跳过，保持测试离线独立）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

BUSINESS_TITLES = ["总览", "研究任务", "文档与证据", "财务分析", "研判核查", "估值", "投资备忘录", "审计回放", "每日复盘"]
ADVANCED_TITLES = ["案例演示", "CARD-15 Demo", "AI Agent 研究", "Agent 执行轨迹", "评测与消融", "旧版页面入口"]


def test_navigation_registry_snapshot() -> None:
    from services.navigation import ADVANCED_PAGES, BUSINESS_PAGES, pages

    assert [title for _, title, _ in BUSINESS_PAGES] == BUSINESS_TITLES
    assert [title for _, title, _ in ADVANCED_PAGES] == ADVANCED_TITLES
    registry = pages()
    assert list(registry.keys()) == ["", "高级"]
    # st.Page 的 title 属性依赖运行时上下文；注册表快照用模块级元组断言。
    assert len(registry[""]) == len(BUSINESS_PAGES)
    assert len(registry["高级"]) == len(ADVANCED_PAGES)
    assert all(page is not None for page in registry[""] + registry["高级"])


def test_legacy_aliases_cover_old_page_names() -> None:
    from app_pages.legacy_compat import LEGACY_ALIASES

    for legacy_name, target in LEGACY_ALIASES.items():
        assert target.startswith("app_pages/"), legacy_name
        assert (ROOT / target).exists(), legacy_name


def test_evidence_chip_keeps_full_id_out_of_visible_surface() -> None:
    """完整 evidence ID 只允许出现在 chip 的 title 悬浮属性中出现一次。"""
    from ui.chips import _chip_html, _short_evidence_id, evidence_chip

    raw_id = "fact_600519_SH_revenue_2024FY"
    chip = _chip_html(
        f"年报证据 <span style='opacity:.75'>· {_short_evidence_id(raw_id)}</span>",
        f"证据编号 {raw_id} · 来源 年报",
        bg="#EEF3F8", fg="#1F6FEB",
    )
    assert chip.count(raw_id) == 1
    title_index = chip.index("title=")
    visible_head = chip[:title_index]
    visible_tail = chip[chip.index(">", chip.index(">", title_index) + 1):]
    assert raw_id not in visible_head + visible_tail
    assert raw_id not in _short_evidence_id(raw_id)
    # evidence_chip 是纯渲染入口，导入即可用；detail 为空时不产生 expander。
    assert callable(evidence_chip)


def test_tech_and_status_chips_hide_raw_snapshot_id() -> None:
    from ui.chips import _chip_html

    snapshot_id = "600519.SH_20260810_tushare_v1"
    chip = _chip_html("⚙ 快照版本", f"快照版本：{snapshot_id}", bg="#EEF3F8", fg="#627D98")
    assert chip.count(snapshot_id) == 1
    assert chip.index(snapshot_id) > chip.index("title=")


def _has_demo_snapshots() -> bool:
    snap_dir = ROOT / "data" / "snapshots" / "cn"
    return snap_dir.exists() and any(snap_dir.glob("*.json"))


@pytest.mark.skipif(not _has_demo_snapshots(), reason="demo snapshots not generated on this machine")
def test_overview_and_valuation_render_offline() -> None:
    """demo 快照下总览与估值页可离线渲染（AppTest 驱动真实导航运行时）。"""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "workbench.py"), default_timeout=120)
    catalog_dir = ROOT / "data" / "snapshots" / "cn"
    at.session_state["selected_snapshot_id"] = sorted(p.stem for p in catalog_dir.glob("*.json"))[0]
    at.run()
    for page_path in ("app_pages/overview.py", "app_pages/valuation.py", "app_pages/research_review.py"):
        at.switch_page(page_path)
        at.run()
        assert not at.exception, f"{page_path}: {at.exception[0].value if at.exception else ''}"


def test_stepper_and_theme_tokens_present() -> None:
    from ui.stepper import _dot_state
    from ui.theme import TOKENS

    for key in ("red_up", "green_down", "chip_bg", "chip_text"):
        assert key in TOKENS
    assert _dot_state("verified")[1] == TOKENS["green"]
    assert _dot_state("blocked")[1] == TOKENS["coral"]
    assert _dot_state("warning")[1] == TOKENS["amber"]
    assert _dot_state("unknown")[1] not in {TOKENS["green"], TOKENS["coral"], TOKENS["amber"]}
