# -*- coding: utf-8 -*-
"""重新解析全部 BV → manifest。然后按新规则：排除助眠/放松，仅保留 40min~12h 的学习类。"""
import json
import os
import sys
import time

sys.path.insert(0, ".")
from services.video_source import resolve_bili  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BVS = """BV1XctB6PEZG BV1sJt66fE7p BV1Cst66xEzb BV1WHt66tEr3 BV1sAtr68Ekv
BV1Tft66AE7j BV1ATtr6oEP6 BV1cutr6xE5B BV1Y2t663EuD BV13mt666Et2
BV1gotd6SEhA BV1CF4y6NE9v BV1mutB6ZEUr BV14GtB6dEbC BV1dZtq6KEA5
BV1aftq6vEmz BV1LRtq6uEwr BV1vRtq6MEjT BV1aPtB6wEGu BV1jetB6rEDD
BV1qitB6gEA5 BV1oVi6BaE1K BV1hCqwBHEfr BV1rKqABiE5J BV1pwqABuEtj
BV182qwBJErm BV1UpisB3EeY BV1TRDuBNEmK BV1hDSUBjEjo BV1XtDvBmEb6
BV1Q5DfB1EBH BV15zQLBYEim BV1mAdfBDEB1 BV1xQixBgEwU BV1xPqTBWEtv
BV1qvqPBvEd2 BV12prgBkExN BV1vj6gBXE51 BV1JL6xBzENw BV1s4MR6QE9x
BV1chGF6KEst BV1VS3D6wEFo BV1RbMd6uExy BV1wEMZ6REgw BV18KuF6rEpX
BV1msM16wEDH BV1SWMm66Exo BV1XYjr6UEfq BV1HKjq6QECe BV12Yjc64EJy
BV1eBLD6VEoy BV1tWjM62Eyv BV16Yj46pE1i BV1xUfFBdEFV BV1UXfKB7EV9
BV1D7fyBREH8 BV1rNftBfEFo BV19icqzjELd BV1RsZWBiEGS BV1YScpz3E82
BV1r3Z2ByEaG BV1J8ZaBKEYQ BV1LhfVB1EcE BV11RffBdEE7 BV1PmF4zKE4e
BV1VvFJzcEY5 BV1oiFvzyERq BV1VmcuzKETy BV14UFQzrEMY BV19eFMzwER9
BV1xRzZBuExe BV1xx6BBnErW BV1Er6BBgEE9 BV1cG6ABVEnb BV1cXFLzAEQA
BV12HzEBbE85 BV1a2rQBMEbf BV1w46oBYEwn BV1uvzQBZEG9 BV1tdzDBsEkJ
BV1w7zcBMEg8""".split()

# 排除关键词（放松/助眠类）
EXCLUDE = ("助眠", "失眠", "梦", "晚安", "睡觉", "入梦", "入睡", "白噪音", "纯音乐",
           "壁炉", "音乐", "Playlist", "playlist", "Funk", "R&B", "轻音乐", "冥想",
           "放松", "昏沉", "入眠", "睡眠")


def is_exclude(title):
    t = (title or "")
    return any(k.lower() in t.lower() for k in EXCLUDE)


items = []
for i, bv in enumerate(BVS):
    try:
        info = resolve_bili("https://www.bilibili.com/video/" + bv)
        title = (info.get("title") or "").strip()
        dur = info.get("duration") or 0
        items.append({"bvid": bv, "title": title, "duration": dur})
        print(f"[{i+1}/{len(BVS)}] {dur}s {title[:36]}", flush=True)
    except Exception as exc:
        print(f"[{i+1}/{len(BVS)}] FAIL {bv}: {type(exc).__name__}", flush=True)
    time.sleep(0.35)

with open(os.path.join(ROOT, "_manifest.json"), "w", encoding="utf-8") as fh:
    json.dump(items, fh, ensure_ascii=False, indent=2)
print("manifest items:", len(items))
