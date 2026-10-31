# -*- coding: utf-8 -*-
"""检查 manifest 与现有下载，输出筛选建议（写入 out 文件，避免管道 EPERM）。"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "video", "_inspect_out.txt")

# 排除关键词（放松/助眠类，与 manifest2 一致并稍扩展）
EXCLUDE = ("助眠", "失眠", "梦", "晚安", "睡觉", "入梦", "入睡", "白噪音", "纯音乐",
           "壁炉", "音乐", "Playlist", "playlist", "Funk", "R&B", "轻音乐", "冥想",
           "放松", "昏沉", "入眠", "睡眠", "晚安电台", "深夜电台")

MIN_DUR, MAX_DUR = 40 * 60, 12 * 3600  # 40min ~ 12h


def is_exclude(title):
    t = (title or "").lower()
    return any(k.lower() in t for k in EXCLUDE)


items = json.load(open(os.path.join(ROOT, "_manifest.json"), encoding="utf-8"))
lines = []
lines.append("TOTAL manifest: %d" % len(items))
lines.append("")

# 已有下载文件名（用于判断哪些 BV 已下）
dl_root = os.path.join(ROOT, "video", "downloads")
already = set()
for dirpath, _dirs, files in os.walk(dl_root):
    for f in files:
        if f.lower().endswith(".mp4") or f.lower().endswith(".flv"):
            already.add(f)

ok = []
excluded = []
for it in items:
    bv = it.get("bvid", "")
    title = (it.get("title") or "").strip()
    dur = it.get("duration") or 0
    tag = "EXCL" if is_exclude(title) else ("LEN" if not (MIN_DUR <= dur <= MAX_DUR) else "OK")
    rec = (tag, bv, dur, title)
    if tag == "OK":
        ok.append(rec)
    else:
        excluded.append(rec)

lines.append("== KEEP (%d) ==" % len(ok))
for tag, bv, dur, title in sorted(ok, key=lambda r: -r[2]):
    lines.append("%s %8ds %4.1fh %s" % (bv, dur, dur / 3600.0, title))
lines.append("")
lines.append("== DROP-EXCL keywords (%d) ==" % len([x for x in excluded if x[0] == 'EXCL']))
for tag, bv, dur, title in sorted([x for x in excluded if x[0] == 'EXCL'], key=lambda r: -r[2]):
    lines.append("%s %8ds %4.1fh %s" % (bv, dur, dur / 3600.0, title))
lines.append("")
lines.append("== DROP-LENGTH out of 40m-12h (%d) ==" % len([x for x in excluded if x[0] == 'LEN']))
for tag, bv, dur, title in sorted([x for x in excluded if x[0] == 'LEN'], key=lambda r: -r[2]):
    lines.append("%s %8ds %4.1fh %s" % (bv, dur, dur / 3600.0, title))
lines.append("")

# 粗略估算 KEEP 清单总时长
total_s = sum(r[2] for r in ok)
lines.append("KEEP total duration: %d h (assuming 480P ~500-900MB/h est)" % int(total_s // 3600))

with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))
print("written:", OUT)
