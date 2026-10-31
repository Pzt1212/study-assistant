# -*- coding: utf-8 -*-
"""下载并解压 BBDown win-x64 到 video/（ghfast.top 镜像优先）。"""
import io
import os
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
DEST_DIR = os.path.join(ROOT, "bbdown")
os.makedirs(DEST_DIR, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36"
REL = "nilaoda/BBDown/releases/download/1.6.3/BBDown_1.6.3_20240814_win-x64.zip"
URLS = [
    "https://github.com/" + REL,
    "https://ghfast.top/https://github.com/" + REL,
    "https://gh-proxy.com/https://github.com/" + REL,
    "https://ghproxy.net/https://github.com/" + REL,
]
out = []
for url in URLS:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = resp.read()
        if len(data) < 100000:
            raise RuntimeError("too small")
        zf = zipfile.ZipFile(io.BytesIO(data))
        zf.extractall(DEST_DIR)
        out.append(f"[OK] {url.split('/')[2]} -> {len(data)} bytes, {len(zf.namelist())} files")
        break
    except Exception as exc:
        out.append(f"[FAIL] {url.split('/')[2]}: {exc!r}")
with open(os.path.join(ROOT, "_bb_dl.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(out))
print("\n".join(out))
