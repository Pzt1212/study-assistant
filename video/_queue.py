# -*- coding: utf-8 -*-
"""生成最终下载队列 video/_queue.json：从 _manifest.json 按新规则筛选并分类、排序。"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "video", "_queue.json")

EXCLUDE = ("助眠", "失眠", "梦", "晚安", "睡觉", "入梦", "入睡", "白噪音", "纯音乐",
           "壁炉", "音乐", "Playlist", "playlist", "Funk", "R&B", "轻音乐", "冥想",
           "放松", "昏沉", "入眠", "睡眠")
MIN_DUR, MAX_DUR = 40 * 60, 12 * 3600
# 用户确认跳过的明显非学习项
SKIP_BV = {"BV1XctB6PEZG", "BV19eFMzwER9", "BV1xPqTBWEtv"}


def is_exclude(title):
    t = (title or "").lower()
    return any(k.lower() in t for k in EXCLUDE)


def bucket(dur):
    h = dur / 3600.0
    if h >= 6:
        return "长程6小时以上"
    if h >= 2:
        return "中程2-6小时"
    return "短程40分钟-2小时"


items = json.load(open(os.path.join(ROOT, "_manifest.json"), encoding="utf-8"))
queue = []
for it in items:
    bv = it.get("bvid", "")
    title = (it.get("title") or "").strip()
    dur = it.get("duration") or 0
    if bv in SKIP_BV:
        continue
    if is_exclude(title):
        continue
    if not (MIN_DUR <= dur <= MAX_DUR):
        continue
    queue.append({"bvid": bv, "title": title, "duration": dur, "dir": bucket(dur)})

queue.sort(key=lambda x: -x["duration"])
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(queue, fh, ensure_ascii=False, indent=1)
print("queue:", len(queue))
from collections import Counter
print(Counter(q["dir"] for q in queue))
print("total hours: %.1f" % (sum(q["duration"] for q in queue) / 3600.0))
