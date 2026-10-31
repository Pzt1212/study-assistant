# -*- coding: utf-8 -*-
"""检查 /video/thumb 路由是否注册、为何 404。"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = "D:/study-assistant"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
OUT = ROOT + "/video/_thumb_dbg3_out.txt"
lines = []
from config import Config
from app import create_app
app = create_app(Config)
rules = [str(r) for r in app.url_map.iter_rules()]
lines.append("video rules:")
for r in rules:
    if "/video" in r:
        lines.append("  " + r)
lines.append("has /video/thumb: %s" % any(r == "/video/thumb" for r in rules))
# test_client 直接探测
with app.test_client() as c:
    with c.session_transaction() as s:
        s["_user_id"] = "1"
    for url in ["/video/thumb", "/video/thumb?file=x", "/video/api/local"]:
        rr = c.get(url)
        lines.append("GET %s -> %d" % (url, rr.status_code))
open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print("\n".join(lines))
