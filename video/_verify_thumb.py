# -*- coding: utf-8 -*-
"""验证：/video 页面含缩略图与可点卡片；/video/thumb 抽帧返回 jpeg。"""
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = "D:/study-assistant"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
OUT = ROOT + "/video/_verify_thumb_out.txt"
lines = []

from config import Config
from app import create_app
from services.video_source import list_local_videos

app = create_app(Config)
loc = list_local_videos()
lines.append("local videos: %d" % len(loc))
small = None
for v in loc:
    if v["ext"] == "mp4" and v["size"] > 5 * 1048576:
        small = v
        break
if not small:
    small = loc[0]
lines.append("thumb target: %s (%.1f MB)" % (small["file"], small["size"] / 1048576.0))

with app.test_client() as c:
    with c.session_transaction() as s:
        s["_user_id"] = "1"
    r = c.get("/video")
    html = r.get_data(as_text=True)
    lines.append("GET /video -> %d" % r.status_code)
    lines.append("has js-local-card: %s" % ("js-local-card" in html))
    lines.append("has img.vthumb count: %d" % html.count('class="vthumb"'))
    t0 = time.time()
    import urllib.parse
    q = urllib.parse.quote(small["file"])
    rr = c.get("/video/thumb?file=" + q)
    lines.append("GET /video/thumb -> %d  type=%s  bytes=%s  took=%.1fs" % (
        rr.status_code, rr.headers.get("Content-Type"), rr.content_length, time.time() - t0))
    t1 = time.time()
    rr2 = c.get("/video/thumb?file=" + q)
    lines.append("GET cached -> %d  bytes=%s  took=%.1fs" % (
        rr2.status_code, rr2.content_length, time.time() - t1))
    # 穿越防护
    rr3 = c.get("/video/thumb?file=..%2F..%2Fconfig.py")
    lines.append("traversal guard -> %d" % rr3.status_code)

open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print("\n".join(lines))
