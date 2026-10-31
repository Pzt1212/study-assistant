# -*- coding: utf-8 -*-
"""下载 ffmpeg（BBDown 混流必需）。优先 ghfast.top 镜像的 BtbN ffmpeg release。"""
import io
import os
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN_DIR = os.path.join(ROOT, "video", "bin")
os.makedirs(BIN_DIR, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36"

# BtbN/FFmpeg-Builds 的 win64-gpl essentials（体积较小：仅 ffmpeg/ffprobe/ffplay）
REL = ("BtbN/FFmpeg-Builds/releases/download/latest/"
       "ffmpeg-master-latest-win64-gpl.zip")
URLS = [
    "https://ghfast.top/https://github.com/" + REL,
    "https://gh-proxy.com/https://github.com/" + REL,
    "https://ghproxy.net/https://github.com/" + REL,
    "https://github.com/" + REL,
]
out = []
for url in URLS:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=900) as resp:
            data = resp.read()
        if len(data) < 5 * 1024 * 1024:
            raise RuntimeError("too small")
        zf = zipfile.ZipFile(io.BytesIO(data))
        zf.extractall(BIN_DIR)
        out.append(f"[OK] {url.split('/')[2]} -> {len(data)} bytes")
        break
    except Exception as exc:
        out.append(f"[FAIL] {url.split('/')[2]}: {type(exc).__name__} {exc}")
with open(os.path.join(ROOT, "video", "_ffmpeg.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(out))
print("\n".join(out))
