"""Theme tokens and lightweight app-level styling."""

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
    """Apply only requested product styling; semantics remain native Streamlit."""
    st.markdown(f"""
<style>
:root {{ --ft-navy:{TOKENS['navy']}; --ft-blue:{TOKENS['blue']}; --ft-green:{TOKENS['green']}; --ft-amber:{TOKENS['amber']}; --ft-coral:{TOKENS['coral']}; --ft-border:{TOKENS['border']}; --ft-text:{TOKENS['text']}; --ft-muted:{TOKENS['muted']}; --ft-red-up:{TOKENS['red_up']}; --ft-green-down:{TOKENS['green_down']}; --ft-chip-bg:{TOKENS['chip_bg']}; --ft-chip-text:{TOKENS['chip_text']}; }}
.stApp {{ background:{TOKENS['canvas']}; }}
[data-testid="stSidebar"] {{ background:{TOKENS['navy']}; }}
[data-testid="stSidebar"] * {{ color:#F7FAFC !important; }}
[data-testid="stSidebar"] [data-baseweb="select"] * {{ color:{TOKENS['text']} !important; }}
[data-testid="stSidebar"] hr {{ border-color:rgba(255,255,255,.16); }}
.block-container {{ max-width:1480px; padding-top:1.2rem; }}
.ft-eyebrow {{ color:{TOKENS['muted']}; font-size:.75rem; letter-spacing:.08em; text-transform:uppercase; font-weight:700; }}
.ft-context {{ background:{TOKENS['card']}; border:1px solid {TOKENS['border']}; border-radius:12px; padding:.7rem 1rem; margin-bottom:1.1rem; }}
.ft-evidence {{ color:{TOKENS['blue']}; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.8rem; }}
.ft-small {{ color:{TOKENS['muted']}; font-size:.86rem; }}
/* 数字统一等宽数位，卡片 12px 圆角 / 1px 边框 / 无阴影（flat） */
[data-testid="stMetric"], [data-testid="stMetricValue"] {{ font-variant-numeric: tabular-nums; }}
[data-testid="stMetric"] {{ background:{TOKENS['card']}; border:1px solid {TOKENS['border']}; border-radius:12px; padding:.9rem 1rem; box-shadow:none; }}
[data-testid="stVerticalBlockBorderWrapper"] > div {{ border-color:{TOKENS['border']} !important; border-radius:12px !important; background:{TOKENS['card']}; box-shadow:none !important; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ box-shadow:none !important; }}
.ft-card {{ background:{TOKENS['card']}; border:1px solid {TOKENS['border']}; border-radius:12px; padding:16px; }}
.ft-up {{ color:{TOKENS['red_up']}; font-weight:600; font-variant-numeric:tabular-nums; }}
.ft-down {{ color:{TOKENS['green_down']}; font-weight:600; font-variant-numeric:tabular-nums; }}
</style>
""", unsafe_allow_html=True)
