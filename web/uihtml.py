# -*- coding: utf-8 -*-
"""
ui.py를 스트림릿 없이 쓰는 다리.

⚠️ 핵심 발상: ui.py의 부품들(kpi, donut, gauge …)은 어차피
   HTML 문자열을 만들어 st.markdown()에 넘길 뿐이다.
   그렇다면 st.markdown이 '화면에 그리는' 대신 '문자열을 모아주게' 바꾸면,
   같은 코드가 같은 HTML을 뱉는다 → 디자인이 어긋날 수가 없다.
   부품을 다시 그리지 않는 이유가 이것이다.
"""
import contextvars
import sys
import types
from contextlib import contextmanager

_buf = contextvars.ContextVar("kh_buf", default=None)

_st = types.ModuleType("streamlit")


def _markdown(html, unsafe_allow_html=False, **k):
    b = _buf.get()
    if b is not None:
        b.append(str(html))


def _noop(*a, **k):
    return None


def _cache(*a, **k):
    if a and callable(a[0]):
        return a[0]
    return lambda f: f


_st.markdown = _markdown
for _n in ("caption", "write", "divider", "error", "warning", "info",
           "success", "container", "columns", "button", "spinner"):
    setattr(_st, _n, _noop)
_st.cache_data = _cache
_st.cache_resource = _cache
_st.context = types.SimpleNamespace(headers={}, cookies={})
_st.query_params = {}
sys.modules["streamlit"] = _st

import os
_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _cand in (os.environ.get("KH_BRAIN", ""), _PARENT):
    if _cand and os.path.exists(os.path.join(_cand, "ui.py")):
        sys.path.insert(0, _cand)   # ui.py는 web/의 부모 폴더에 있다
        break
import ui                      # noqa: E402  (가짜 streamlit을 심은 뒤에)


@contextmanager
def capture():
    buf = []
    tok = _buf.set(buf)
    try:
        yield buf
    finally:
        _buf.reset(tok)


def render(fn, *a, **k):
    """ui.py 부품 하나를 불러 HTML 문자열로 받는다."""
    with capture() as b:
        fn(*a, **k)
    return "".join(b)
