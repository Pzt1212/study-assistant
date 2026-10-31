# -*- coding: utf-8 -*-
import json
import urllib.request

UA = "Mozilla/5.0 study-assistant/1.0"
out = []
url = "https://api.github.com/repos/nilaoda/BBDown/releases/latest"
req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        rel = json.loads(resp.read().decode("utf-8", "replace"))
    out.append(f"tag: {rel.get('tag_name')}")
    for a in (rel.get("assets") or []):
        n = a.get("name", "")
        # 关注 win-x64 自包含（免 .NET 环境）
        if "win" in n.lower() and ("x64" in n.lower() or "amd64" in n.lower()):
            out.append(f"asset: {n} -> {a.get('browser_download_url')} ({a.get('size')} bytes)")
except Exception as exc:
    out.append(f"[FAIL] {exc!r}")
with open("_bb_release.txt", "w", encoding="utf-8") as fh:
    fh.write("\n".join(out))
print("\n".join(out))
