# -*- coding: utf-8 -*-
"""网络诊断：测试 bilibili view API 与普通 https，输出到文件。"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT = r"D:\study-assistant\video\_netdiag_out.txt"
lines = []
try:
    import requests
    lines.append("requests version: %s" % requests.__version__)
    for name, url in [
        ("view-api", "https://api.bilibili.com/x/web-interface/view?bvid=BV1xPqTBWEtv"),
        ("www-bili", "https://www.bilibili.com/"),
    ]:
        try:
            r = requests.get(url, timeout=20,
                             headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
            lines.append("%s -> HTTP %d  len=%d" % (name, r.status_code, len(r.content)))
            if name == "view-api":
                j = r.json()
                lines.append("  code=%s title=%s" % (j.get("code"), (j.get("data") or {}).get("title")))
        except Exception as exc:
            lines.append("%s -> EXC %s: %s" % (name, type(exc).__name__, exc))
except Exception as exc:
    lines.append("requests import EXC: %s: %s" % (type(exc).__name__, exc))

open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print("written:", OUT)
