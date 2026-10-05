"""PDF 双栏高亮核查器（UI_REDESIGN_PLAN_V2 P2-1）。

左栏 pdf.js 内嵌渲染 PDF（文本层可选中），右栏声明列表；点击声明即滚动并
高亮 PDF 中对应句子。PDF 原文仅来自本会话上传材料（内存），不落盘、不外传。
方案原文指定 st.components.v1，因 v1 已弃用，改用 st.html 注入（同等能力）。
"""

from __future__ import annotations

import base64
import json

import streamlit as st

_PDFJS = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174"
_CSS = """
<style>
.ft-pdf-split { display:flex; gap:12px; align-items:stretch; height:560px;
  border:1px solid #E5EAF0; border-radius:12px; overflow:hidden; background:#F7F8FA; }
.ft-pdf-left { flex:1.4; overflow:auto; padding:12px; }
.ft-pdf-right { flex:1; overflow:auto; padding:12px; background:#FFFFFF;
  border-left:1px solid #E5EAF0; }
.ft-pdf-page { margin:0 auto 10px; width:fit-content; background:#fff;
  box-shadow:0 1px 3px rgba(16,42,67,.12); position:relative; }
.ft-pdf-left canvas { display:block; }
.ft-pdf-text { position:absolute; inset:0; overflow:hidden; line-height:1;
  opacity:.999; }
.ft-pdf-text span { position:absolute; color:transparent; cursor:text; }
.ft-pdf-text span.ft-hl { background:rgba(217,148,0,.45); border-radius:2px; }
.ft-claim { border:1px solid #E5EAF0; border-radius:10px; padding:.5rem .7rem;
  margin-bottom:.5rem; cursor:pointer; font-size:.84rem; line-height:1.5; }
.ft-claim:hover { background:rgba(31,111,235,.06); }
.ft-claim b { color:#1F6FEB; font-size:.72rem; }
</style>
"""


def render(pdf_bytes: bytes, highlights: list[str], *, height: int = 560) -> None:
    """渲染双栏核查器：左 PDF、右声明列表（点击高亮）。

    highlights：需要高亮的声明原句列表（来自已核查 Claim）。
    """
    if not pdf_bytes:
        st.caption("没有可渲染的 PDF。")
        return
    b64 = base64.b64encode(pdf_bytes).decode("ascii")
    claims_payload = json.dumps(
        [{"id": index + 1, "text": (text or "")[:400]} for index, text in enumerate(highlights)],
        ensure_ascii=False,
    )
    html = f"""
<div id="ft-pdf-app">
  <div class="ft-pdf-split" style="height:{height}px">
    <div class="ft-pdf-left" id="ft-pdf-pages"></div>
    <div class="ft-pdf-right" id="ft-claims">
      <div style="font-size:.78rem;color:#627D98;margin-bottom:.5rem">
        点击声明 → 左侧 PDF 滚动并高亮对应句子</div>
    </div>
  </div>
</div>
<script src="{_PDFJS}/pdf.min.js"></script>
<script>
(function () {{
  const CLAIMS = {claims_payload};
  const app = document.getElementById('ft-pdf-app');
  const pagesEl = app.querySelector('#ft-pdf-pages');
  const claimsEl = app.querySelector('#ft-claims');
  pdfjsLib.GlobalWorkerOptions.workerSrc = '{_PDFJS}/pdf.worker.min.js';
  const raw = atob('{b64}');
  const data = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) data[i] = raw.charCodeAt(i);

  function norm(s) {{ return (s || '').replace(/\\s+/g, '').toLowerCase(); }}
  // 取声明中的显著片段（≥8 字符）用于匹配文本层 span
  function keysOf(text) {{
    const t = norm(text);
    const keys = new Set();
    if (t.length >= 8) {{
      keys.add(t.slice(0, 16));
      keys.add(t.slice(-16));
      for (let i = 0; i + 12 <= t.length; i += 12) keys.add(t.slice(i, i + 12));
    }}
    return Array.from(keys).filter(k => k.length >= 8);
  }}

  let spans = [];
  function clearHighlights() {{
    spans.forEach(span => span.classList && span.classList.remove('ft-hl'));
  }}
  function highlightClaim(text) {{
    clearHighlights();
    const keys = keysOf(text);
    if (!keys.length) return 0;
    let hits = 0;
    spans.forEach(span => {{
      const content = norm(span.textContent);
      if (!content) return;
      if (keys.some(key => content.indexOf(key) !== -1)) {{
        span.classList.add('ft-hl');
        hits += 1;
      }}
    }});
    return hits;
  }}

  CLAIMS.forEach(claim => {{
    const div = document.createElement('div');
    div.className = 'ft-claim';
    div.innerHTML = '<b>声明 ' + claim.id + '</b><br>' + document.createTextNode(claim.text).textContent;
    div.addEventListener('click', function () {{
      highlightClaim(claim.text);
      const first = app.querySelector('.ft-hl');
      if (first) first.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
    }});
    claimsEl.appendChild(div);
  }});

  pdfjsLib.getDocument({{ data: data }}).promise.then(function (doc) {{
    const maxPages = Math.min(doc.numPages, 30);
    for (let n = 1; n <= maxPages; n++) {{
      doc.getPage(n).then(function (page) {{
        const scale = 1.35;
        const viewport = page.getViewport({{ scale: scale }});
        const holder = document.createElement('div');
        holder.className = 'ft-pdf-page';
        holder.style.width = viewport.width + 'px';
        holder.style.height = viewport.height + 'px';
        const canvas = document.createElement('canvas');
        canvas.width = viewport.width; canvas.height = viewport.height;
        const textLayer = document.createElement('div');
        textLayer.className = 'ft-pdf-text';
        holder.appendChild(canvas); holder.appendChild(textLayer);
        pagesEl.appendChild(holder);
        page.render({{ canvasContext: canvas.getContext('2d'), viewport: viewport }}).promise
          .then(function () {{
            return pdfjsLib.renderTextLayer({{
              textContentSource: page.streamTextContent(),
              container: textLayer,
              viewport: viewport,
            }}).promise;
          }}).then(function () {{
            spans = spans.concat(Array.prototype.slice.call(textLayer.querySelectorAll('span')));
            if (CLAIMS.length && spans.length && !app.dataset.auto) {{
              app.dataset.auto = '1';
              highlightClaim(CLAIMS[0].text);
            }}
          }}).catch(function () {{ /* 文本层失败时仍显示画布 */ }});
      }});
    }}
  }}).catch(function () {{
    pagesEl.innerHTML = '<div style="color:#627D98;padding:1rem">PDF 渲染失败（需要网络加载 pdf.js）。</div>';
  }});
}})();
</script>
"""
    st.markdown(_CSS, unsafe_allow_html=True)
    st.html(html)


def disclaimer() -> None:
    st.caption(
        "PDF 原文仅来自本会话上传材料，渲染在本地浏览器内完成；"
        f"高亮只是定位辅助，不改变声明的核查状态。"
    )
