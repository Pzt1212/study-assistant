# -*- coding: utf-8 -*-
"""统计现有下载文件大小/时长，估算 MB/h。输出到 _sizes_out.txt。"""
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "video", "_sizes_out.txt")
FFPROBE = os.path.join(ROOT, "video", "bin", "ffmpeg-master-latest-win64-gpl", "bin", "ffprobe.exe")
dl_root = os.path.join(ROOT, "video", "downloads")

lines = []
lines.append("ffprobe exists: %s" % os.path.exists(FFPROBE))
total = 0
rows = []
for dirpath, _dirs, files in os.walk(dl_root):
    for f in files:
        p = os.path.join(dirpath, f)
        if not (f.lower().endswith(".mp4") or f.lower().endswith(".flv")):
            continue
        sz = os.path.getsize(p)
        total += sz
        dur = None
        if os.path.exists(FFPROBE):
            try:
                r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                                    "-of", "default=noprint_wrappers=1:nokey=1", p],
                                   capture_output=True, text=True, timeout=60)
                dur = float(r.stdout.strip()) if r.stdout.strip() else None
            except Exception:
                dur = None
        rows.append((sz, dur, os.path.relpath(p, dl_root)))

for sz, dur, rel in sorted(rows, key=lambda r: -r[0]):
    mb = sz / 1048576.0
    if dur:
        mbh = mb / (dur / 3600.0)
        lines.append("%8.1f MB  %7.1f h  %6.0f MB/h  %s" % (mb, dur / 3600.0, mbh, rel))
    else:
        lines.append("%8.1f MB  (no-dur)          %s" % (mb, rel))
lines.append("TOTAL mp4 bytes: %.1f MB" % (total / 1048576.0))
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))
print("written:", OUT)
