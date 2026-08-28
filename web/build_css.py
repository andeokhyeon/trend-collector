# -*- coding: utf-8 -*-
"""
ui.py의 CSS를 뽑아 static/app.css 로 저장한다.

⚠️ 디자인의 원본은 여전히 ui.py 하나다. 여기서 손으로 고치지 않는다.
   ui.py를 고친 뒤 이 파일을 한 번 돌리면 웹 화면에도 반영된다.
       python build_css.py
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import uihtml                                  # 가짜 streamlit을 심는다

css = uihtml.ui._build_css()
m = re.search(r"<style>(.*)</style>", css, re.S)
pure = m.group(1) if m else css
out = os.path.join(HERE, "static", "app.css")
io.open(out, "w", encoding="utf-8").write(pure)
print(f"저장: {out} ({len(pure):,}자)")
