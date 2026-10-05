"""Theme tokens and app-level styling aligned with the three target mockups.

设计语言（对齐图1/图2/图3）：深海军蓝侧栏、白卡片 + 极浅阴影、蓝色竖条区块
标题、下划线式 Tab、绿色打勾 stepper、tabular-nums 数字。
"""

from __future__ import annotations

import streamlit as st


TOKENS = {
    "navy": "#102A43", "blue": "#1F6FEB", "green": "#159570", "amber": "#D99400",
    "coral": "#D9534F", "canvas": "#F7F8FA", "card": "#FFFFFF", "border": "#E5EAF0",
    "text": "#172B4D", "muted": "#627D98",
    # A 股行情语义与芯片配色（UI_REDESIGN_PLAN_V2 §2）
    "red_up": "#D9534F",      # 涨（A 股红涨，与 coral 同源）
    "green_down": "#159570",  # 跌（绿跌）
    "chip_bg": "#EEF3F8",     # 证据 chip 底色
    "chip_text": "#1F6FEB",
}

# 状态色语义表（全站唯一）：可验证=green / 需核查=amber / 冲突阻断=coral /
# 信息主操作=blue；涨=red_up，跌=green_down。


def apply() -> None:
    """Apply the shared design language; semantics remain native Streamlit."""
    st.markdown(f"""
<style>
:root {{ --ft-navy:{TOKENS['navy']}; --ft-blue:{TOKENS['blue']}; --ft-green:{TOKENS['green']}; --ft-amber:{TOKENS['amber']}; --ft-coral:{TOKENS['coral']}; --ft-border:{TOKENS['border']}; --ft-text:{TOKENS['text']}; --ft-muted:{TOKENS['muted']}; --ft-red-up:{TOKENS['red_up']}; --ft-green-down:{TOKENS['green_down']}; --ft-chip-bg:{TOKENS['chip_bg']}; --ft-chip-text:{TOKENS['chip_text']}; }}
html, body, .stApp, [data-testid="stMarkdownContainer"], .stMarkdown {{ font-variant-numeric: tabular-nums; }}
.stApp {{ background:{TOKENS['canvas']}; }}
.block-container {{ max-width:1480px; padding-top:1rem; }}

/* ---------- 侧栏：海军蓝 + 品牌 + 导航高亮（对齐图1） ---------- */
[data-testid="stSidebar"] {{
  background:linear-gradient(180deg,{TOKENS['navy']} 0%,#0C2135 100%);
  border-right:none;
}}
[data-testid="stSidebar"] * {{ color:#F7FAFC; }}
[data-testid="stSidebar"] [data-baseweb="select"] * {{ color:{TOKENS['text']} !important; }}
[data-testid="stSidebar"] hr {{ border-color:rgba(255,255,255,.14); }}
.ft-brand {{ padding:.2rem .25rem .9rem; border-bottom:1px solid rgba(255,255,255,.12); margin-bottom:.8rem; }}
.ft-brand-name {{ font-size:1.18rem; font-weight:800; letter-spacing:-.01em; color:#FFFFFF; }}
.ft-brand-sub {{ font-size:.74rem; color:rgba(247,250,252,.62); margin-top:.15rem; }}
[data-testid="stSidebar"] [data-testid="stSidebarNav"] a,
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"],
[data-testid="stSidebar"] [data-testid="stNavLink"],
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] {{
  border-radius:9px; padding:7px 12px; margin:1px 0;
  font-size:.9rem; font-weight:600; transition:background .12s ease;
  border-left:3px solid transparent;
}}
[data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover,
[data-testid="stSidebar"] [data-testid="stNavLink"]:hover,
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover {{
  background:rgba(255,255,255,.09);
}}
[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"],
[data-testid="stSidebar"] [data-testid="stNavLink"][aria-current="page"],
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] {{
  background:{TOKENS['blue']}; color:#FFFFFF !important;
  border-left:3px solid rgba(255,255,255,.65);
}}
[data-testid="stSidebar"] [data-testid="stSidebarNav"] span,
[data-testid="stSidebar"] [data-testid="stNavLink"] span {{ color:inherit; }}
[data-testid="stSidebar"] [data-testid="stSidebarNav"] svg,
[data-testid="stSidebar"] [data-testid="stNavLink"] svg {{ fill:currentColor; }}

/* ---------- 卡片：白底 + 细边 + 极浅阴影（对齐三图） ---------- */
[data-testid="stMetric"], [data-testid="stMetricValue"] {{ font-variant-numeric: tabular-nums; }}
[data-testid="stMetric"] {{
  background:{TOKENS['card']}; border:1px solid {TOKENS['border']};
  border-radius:12px; padding:.9rem 1rem;
  box-shadow:0 1px 3px rgba(16,42,67,.05);
}}
[data-testid="stVerticalBlockBorderWrapper"] > div {{
  border-color:{TOKENS['border']} !important; border-radius:12px !important;
  background:{TOKENS['card']}; box-shadow:0 1px 3px rgba(16,42,67,.05) !important;
}}
.ft-card {{ background:{TOKENS['card']}; border:1px solid {TOKENS['border']}; border-radius:12px; padding:16px; box-shadow:0 1px 3px rgba(16,42,67,.05); }}

/* ---------- 蓝条区块标题（对齐图2/图3「| 相对估值」） ---------- */
.ft-section {{ display:flex; align-items:center; gap:.55rem; margin:1.15rem 0 .5rem; }}
.ft-section-bar {{ width:4px; height:17px; background:{TOKENS['blue']}; border-radius:2px; flex:none; }}
.ft-section-title {{ font-size:1.06rem; font-weight:800; color:{TOKENS['text']}; letter-spacing:-.01em; }}
.ft-section-hint {{ color:{TOKENS['muted']}; font-size:.78rem; margin-left:.15rem; }}
.ft-section-action {{ margin-left:auto; }}
.ft-section-link {{ color:{TOKENS['blue']}; font-size:.8rem; font-weight:600; text-decoration:none; }}

/* ---------- 下划线式 Tab（对齐图3 顶部 Tab 行） ---------- */
.stTabs [data-baseweb="tab-list"] {{ gap:6px; border-bottom:1px solid {TOKENS['border']}; }}
.stTabs [data-baseweb="tab"] {{
  padding:7px 14px; border-radius:8px 8px 0 0; font-weight:600;
  color:{TOKENS['muted']}; font-size:.9rem; border-bottom:2px solid transparent;
}}
.stTabs [data-baseweb="tab"]:hover {{ color:{TOKENS['blue']}; background:rgba(31,111,235,.05); }}
.stTabs [data-baseweb="tab"][aria-selected="true"] {{
  color:{TOKENS['blue']}; border-bottom:2px solid {TOKENS['blue']}; background:transparent;
}}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display:none; }}

/* ---------- 通用文本与 chips ---------- */
.ft-eyebrow {{ color:{TOKENS['muted']}; font-size:.75rem; letter-spacing:.08em; text-transform:uppercase; font-weight:700; }}
.ft-context {{ background:{TOKENS['card']}; border:1px solid {TOKENS['border']}; border-radius:12px; padding:.7rem 1rem; margin-bottom:1.1rem; box-shadow:0 1px 3px rgba(16,42,67,.05); }}
.ft-evidence {{ color:{TOKENS['blue']}; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.8rem; }}
.ft-small {{ color:{TOKENS['muted']}; font-size:.86rem; }}
.ft-up {{ color:{TOKENS['red_up']}; font-weight:700; font-variant-numeric:tabular-nums; }}
.ft-down {{ color:{TOKENS['green_down']}; font-weight:700; font-variant-numeric:tabular-nums; }}
.ft-list-row {{ display:flex; align-items:center; gap:.5rem; padding:.42rem .2rem;
  border-bottom:1px dashed {TOKENS['border']}; font-size:.85rem; }}
.ft-list-row:last-child {{ border-bottom:none; }}
.ft-list-count {{ margin-left:auto; color:{TOKENS['muted']}; font-weight:700; font-variant-numeric:tabular-nums; }}

/* ---------- 数据表 ---------- */
.stDataFrame, [data-testid="stDataFrame"] {{
  border:1px solid {TOKENS['border']} !important; border-radius:10px !important;
  overflow:hidden; box-shadow:0 1px 3px rgba(16,42,67,.04);
}}

/* ---------- 主按钮 ---------- */
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{
  background:{TOKENS['blue']} !important; border-color:{TOKENS['blue']} !important;
  border-radius:10px !important; font-weight:700 !important;
  box-shadow:0 1px 3px rgba(31,111,235,.35) !important;
}}
.stButton > button[kind="primary"]:hover {{ background:#1858C4 !important; }}
.stPageLink {{ font-weight:600; }}
.stPageLink[href*="research_tasks"] {{ color:{TOKENS['blue']} !important; }}
</style>
""", unsafe_allow_html=True)
