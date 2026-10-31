# -*- coding: utf-8 -*-
"""把单项实测遗留的 .P1.mp4/.P1.m4a 用绝对路径 ffmpeg 混流为最终 mp4。"""
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIDEO = os.path.join(ROOT, "video")
FFMPEG = os.path.join(VIDEO, "bin", "ffmpeg-master-latest-win64-gpl", "bin", "ffmpeg.exe")
OUT = os.path.join(VIDEO, "_mux_out.txt")

workdir = os.path.join(VIDEO, "downloads", "长程6小时以上")
found = []
for dirpath, _dirs, files in os.walk(workdir):
    for f in files:
        if f.startswith("115851357325223.P1.") and (f.endswith(".mp4") or f.endswith(".m4a")):
            found.append(os.path.join(dirpath, f))
mp4 = [p for p in found if p.endswith(".mp4")]
m4a = [p for p in found if p.endswith(".m4a")]
lines = ["parts: %s" % [os.path.basename(p) for p in found]]

final_name = "【ADHD】这是我能给你的最高级“作弊码”：10小时，切断一切杂音.mp4"
final_path = os.path.join(workdir, final_name)

if mp4 and m4a and not os.path.exists(final_path):
    cmd = [FFMPEG, "-y", "-i", mp4[0], "-i", m4a[0],
           "-c", "copy", "-movflags", "+faststart", final_path]
    lines.append("CMD: " + " ".join(cmd))
    log = os.path.join(VIDEO, "_mux.log")
    try:
        with open(log, "w", encoding="utf-8", errors="replace") as lf:
            rc = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT).returncode
        lines.append("rc=%d" % rc)
    except Exception as exc:
        lines.append("EXC %s: %s" % (type(exc).__name__, exc))
    if os.path.exists(final_path):
        sz = os.path.getsize(final_path) / 1048576.0
        lines.append("final: %.1f MB %s" % (sz, final_name))
        for p in mp4 + m4a:
            if os.path.exists(p):
                os.remove(p)
                lines.append("removed part: " + os.path.relpath(p, workdir))
    else:
        lines.append("FINAL NOT CREATED")
else:
    lines.append("skip: mp4=%s m4a=%s final_exists=%s" % (bool(mp4), bool(m4a), os.path.exists(final_path)))

open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print("\n".join(lines))
