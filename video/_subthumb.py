# -*- coding: utf-8 -*-
"""验证子目录文件的缩略图路由 200。"""
import sys
import urllib.parse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = "D:/study-assistant"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
OUT = ROOT + "/video/_subthumb_out.txt"
lines = []
from config import Config
from app import create_app
from services.video_source import list_local_videos
sub = [x for x in list_local_videos() if "/" in x["file"]][0]
lines.append("file: %s" % sub["file"])
app = create_app(Config)
with app.test_client() as c:
    with c.session_transaction() as s:
        s["_user_id"] = "1"
    q = urllib.parse.quote(sub["file"])
    rr = c.get("/video/thumb?file=" + q)
    lines.append("subdir thumb -> %d %s %s bytes" % (
        rr.status_code, rr.headers.get("Content-Type"), rr.content_length))
open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print("\n".join(lines))
