# -*- coding: utf-8 -*-
"""直接调用 ensure_thumbnail 验证真实实现。"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = "D:/study-assistant"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
OUT = ROOT + "/video/_thumb_dbg2_out.txt"
lines = []
from services.video_source import ensure_thumbnail

rel = "【ADHD】沉浸式陪伴&情绪安抚｜切断同龄人内卷焦虑｜强行抚平炸毛神经｜ TheGreatStill.mp4"
res = ensure_thumbnail(rel)
lines.append("ensure_thumbnail -> %r" % res)
if res:
    lines.append("size=%d" % os.path.getsize(res))
open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print("\n".join(lines))
