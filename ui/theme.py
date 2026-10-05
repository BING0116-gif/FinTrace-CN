"""Theme tokens and lightweight app-level styling."""

from __future__ import annotations

import streamlit as st


TOKENS = {
    "navy": "#102A43", "blue": "#1F6FEB", "green": "#159570", "amber": "#D99400",
    "coral": "#D9534F", "canvas": "#F7F8FA", "card": "#FFFFFF", "border": "#E5EAF0",
    "text": "#172B4D", "muted": "#627D98",
}


def apply() -> None:
    """Apply only requested product styling; semantics remain native Streamlit."""
    st.markdown(f"""
<style>
:root {{ --ft-navy:{TOKENS['navy']}; --ft-blue:{TOKENS['blue']}; --ft-green:{TOKENS['green']}; --ft-amber:{TOKENS['amber']}; --ft-coral:{TOKENS['coral']}; --ft-border:{TOKENS['border']}; --ft-text:{TOKENS['text']}; --ft-muted:{TOKENS['muted']}; }}
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
[data-testid="stMetric"] {{ background:{TOKENS['card']}; border:1px solid {TOKENS['border']}; border-radius:12px; padding:.9rem 1rem; }}
[data-testid="stVerticalBlockBorderWrapper"] > div {{ border-color:{TOKENS['border']} !important; border-radius:12px !important; background:{TOKENS['card']}; }}
</style>
""", unsafe_allow_html=True)
