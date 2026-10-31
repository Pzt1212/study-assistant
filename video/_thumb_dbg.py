# -*- coding: utf-8 -*-
"""调试 ensure_thumbnail：逐步打印，不吞异常。"""
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = "D:/study-assistant"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
OUT = ROOT + "/video/_thumb_dbg_out.txt"
lines = []

from services import video_source as vs

lines.append("_DL_DIR=%s exists=%s" % (vs._DL_DIR, os.path.isdir(vs._DL_DIR)))
lines.append("_THUMB_DIR=%s" % vs._THUMB_DIR)
lines.append("ffmpeg=%s exists=%s" % (vs._FFMPEG_EXE, os.path.exists(vs._FFMPEG_EXE)))

rel = "【ADHD】沉浸式陪伴&情绪安抚｜切断同龄人内卷焦虑｜强行抚平炸毛神经｜ TheGreatStill.mp4"
full = os.path.normpath(os.path.join(vs._DL_DIR, rel))
lines.append("full=%s isfile=%s" % (full, os.path.isfile(full)))

out = vs._thumb_abs(rel)
lines.append("out=%s cached_exists=%s" % (out, os.path.isfile(out)))

os.makedirs(vs._THUMB_DIR, exist_ok=True)
tmp = out + ".tmp"
cmd = [vs._FFMPEG_EXE, "-y", "-ss", "1", "-i", full, "-frames:v", "1",
       "-vf", "scale=480:-2", "-q:v", "4", tmp]
lines.append("CMD: " + " ".join(cmd))
log = ROOT + "/video/_thumb_dbg_err.txt"
try:
    with open(log, "w", encoding="utf-8", errors="replace") as lf:
        r = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, timeout=90)
    lines.append("rc=%d" % r.returncode)
except Exception as exc:
    lines.append("EXC %s: %s" % (type(exc).__name__, exc))
lines.append("tmp exists=%s" % os.path.isfile(tmp))
if os.path.isfile(tmp):
    lines.append("tmp size=%d" % os.path.getsize(tmp))

open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print("\n".join(lines))
