# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = "D:/study-assistant"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
OUT = ROOT + "/video/_verify_btn_out.txt"
lines = []
from config import Config
from app import create_app
app = create_app(Config)
with app.test_client() as c:
    with c.session_transaction() as s:
        s["_user_id"] = "1"
    r = c.get("/video")
    lines.append("GET /video -> %d" % r.status_code)
    html = r.get_data(as_text=True)
    lines.append("has btn-background: %s" % ("btn-background" in html))
    lines.append("has bg-label text: %s" % ("后台播放 · 切页续播" in html))
    lines.append("has btn-ghost btn-sm(背景播放旧样式 gone): %s" % ("btn-ghost btn-sm\" id=\"btn-background" not in html))
open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print("\n".join(lines))
