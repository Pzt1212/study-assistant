# -*- coding: utf-8 -*-
"""BBDown 下载 TheGreatStill《ADHD 沉浸式陪伴》→ video/downloads/（视频+音频混流 mp4）。"""
import os
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
BBDOWN = os.path.join(ROOT, "bbdown", "BBDown.exe")
FFMPEG = os.path.join(ROOT, "bin", "ffmpeg-master-latest-win64-gpl", "bin", "ffmpeg.exe")
WORK = os.path.join(ROOT, "downloads")
os.makedirs(WORK, exist_ok=True)

LOG = os.path.join(ROOT, "_dl_video.log")
URL = "https://www.bilibili.com/video/BV1PmDWBKECC"

# -e avc 优先 AVC 编码（兼容好、体积适中）；默认档(未登录最高480P)
cmd = [
    BBDOWN,
    "--ffmpeg-path", FFMPEG,
    "-e", "avc,hevc,av1",
    "--work-dir", WORK,
    URL,
]
print("CMD:", " ".join(cmd), flush=True)
try:
    with open(LOG, "w", encoding="utf-8", errors="replace") as lf:
        p = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, timeout=1500)
    print("exit", p.returncode)
except Exception as exc:
    print("EXC", exc)
