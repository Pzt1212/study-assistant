# -*- coding: utf-8 -*-
"""ffprobe 探测现有 mp4 的真实时长（stdout 写文件，避免管道 EPERM）。"""
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "video", "_probe_out.txt")
FFPROBE = os.path.join(ROOT, "video", "bin", "ffmpeg-master-latest-win64-gpl", "bin", "ffprobe.exe")
dl_root = os.path.join(ROOT, "video", "downloads")
TMP = os.path.join(ROOT, "video", "_probe_tmp.txt")

targets = []
for dirpath, _dirs, files in os.walk(dl_root):
    for f in files:
        if f.lower().endswith(".mp4") or f.lower().endswith(".m4a"):
            targets.append(os.path.join(dirpath, f))

lines = []
for p in targets:
    size_mb = os.path.getsize(p) / 1048576.0
    lines.append("FILE %.1f MB  %s" % (size_mb, os.path.relpath(p, dl_root)))
    try:
        with open(TMP, "w", encoding="utf-8", errors="replace") as fh:
            r = subprocess.run(
                [FFPROBE, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", p],
                stdout=fh, stderr=fh, timeout=90,
            )
        txt = open(TMP, encoding="utf-8", errors="replace").read().strip()
        try:
            d = float(txt)
            lines.append("  dur=%6.1f s (%4.1f h)  MB/h=%.0f" % (d, d / 3600.0, size_mb / (d / 3600.0) if d else 0))
        except ValueError:
            lines.append("  dur-unparsed: %r" % txt[:80])
    except Exception as exc:
        lines.append("  probe-fail: %s: %s" % (type(exc).__name__, exc))

with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))
print("written:", OUT)
