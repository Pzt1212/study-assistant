# -*- coding: utf-8 -*-
"""为 downloads 下全部本地视频预生成封面帧缓存（独立进程跑，服务端仅读缓存）。"""
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = "D:/study-assistant"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
OUT = ROOT + "/video/_pregen_out.txt"
lines = []
from services.video_source import ensure_thumbnail, list_local_videos

loc = list_local_videos()
lines.append("videos: %d" % len(loc))
ok = fail = 0
t0 = time.time()
for v in loc:
    t1 = time.time()
    res = ensure_thumbnail(v["file"])
    if res:
        ok += 1
        lines.append("OK  %4.1fs  %s" % (time.time() - t1, v["file"][:60]))
    else:
        fail += 1
        lines.append("FAIL      %s" % v["file"][:60])
lines.append("done ok=%d fail=%d took=%.0fs" % (ok, fail, time.time() - t0))
open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print("done ok=%d fail=%d" % (ok, fail))
