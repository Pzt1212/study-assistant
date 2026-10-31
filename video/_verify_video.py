# -*- coding: utf-8 -*-
"""验证：list_local_videos 递归扫描 + /video/api/local + 子目录文件可播放。"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OUT = os.path.join(ROOT, "video", "_verify_out.txt")
lines = []

from services.video_source import list_local_videos  # noqa: E402
loc = list_local_videos()
lines.append("list_local_videos -> %d items" % len(loc))
for v in loc[:8]:
    lines.append("  [%s] %s  (%.1f MB)" % (v["folder"] or "-", v["title"][:40], v["size"] / 1048576.0))
nested = [v for v in loc if "/" in v["file"]]
lines.append("nested (subdir) items: %d" % len(nested))

from config import Config  # noqa: E402
from app import create_app  # noqa: E402
app = create_app(Config)
with app.test_client() as c:
    with c.session_transaction() as s:
        s["_user_id"] = "1"
    r = c.get("/video/api/local")
    lines.append("GET /video/api/local -> %d" % r.status_code)
    try:
        j = r.get_json()
        lines.append("  ok=%s count=%d" % (j.get("ok"), len(j.get("local", []))))
        sample = [x for x in j.get("local", []) if "/" in x["file"]]
        if sample:
            f = sample[0]["file"]
            lines.append("  nested sample file: %s" % f)
            rr = c.get("/video/files/" + f)
            lines.append("  GET /video/files/%s -> %d (len=%s)" % (f, rr.status_code, rr.content_length))
    except Exception as exc:
        lines.append("  parse EXC %s: %s" % (type(exc).__name__, exc))

open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print("\n".join(lines))
