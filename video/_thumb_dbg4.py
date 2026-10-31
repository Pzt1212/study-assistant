# -*- coding: utf-8 -*-
"""真实文件：同一进程内 ensure_thumbnail vs 路由。"""
import os
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = "D:/study-assistant"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
OUT = ROOT + "/video/_thumb_dbg4_out.txt"
lines = []
from config import Config
from app import create_app
from services.video_source import ensure_thumbnail, _DL_DIR, _THUMB_DIR, _thumb_abs

rel = "【ADHD】沉浸式陪伴&情绪安抚｜切断同龄人内卷焦虑｜强行抚平炸毛神经｜ TheGreatStill.mp4"
lines.append("DL_DIR=%s" % _DL_DIR)
lines.append("THUMB_DIR=%s" % _THUMB_DIR)
out = _thumb_abs(rel)
lines.append("cache=%s exists=%s size=%s" % (out, os.path.isfile(out),
             os.path.getsize(out) if os.path.isfile(out) else "-"))
res = ensure_thumbnail(rel)
lines.append("ensure -> %r" % res)

app = create_app(Config)
import urllib.parse
q = urllib.parse.quote(rel)
with app.test_client() as c:
    with c.session_transaction() as s:
        s["_user_id"] = "1"
    rr = c.get("/video/thumb?file=" + q)
    lines.append("GET encoded -> %d type=%s bytes=%s" % (
        rr.status_code, rr.headers.get("Content-Type"), rr.content_length))
open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print("\n".join(lines))
