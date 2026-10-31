# -*- coding: utf-8 -*-
"""解析 BV 清单 → 标题/时长/分类，生成 manifest，供按分类下载与预算控制。"""
import json
import re
import sys
import time

sys.path.insert(0, ".")
from services.video_source import resolve_bili  # noqa: E402

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

# 分类关键词（按用户清单风格）
CAT_RULES = [
    ("脑波调校", ("ADHD", "脑波", "γ", "Gamma", "40Hz")),
    ("助眠深夜", ("助眠", "失眠", "梦", "晚安", "睡觉", "入梦", "入睡")),
    ("白噪音", ("白噪音", "纯音乐", "纯音乐", "壁炉", "安静", "静默", "死寂")),
    ("沉浸自习", ("自习", "刷题", "学习", "心流", "专注", "沉浸", "番茄", "倒计时", "深度", "补习", "作业")),
    ("PLAYLIST", ("Playlist", "playlist", "Funk", "R&B", "音乐")),
    ("强制专注", ("强制", "重启", "关机", "屏蔽", "隔离")),
]


def classify(title):
    t = title or ""
    for cat, kws in CAT_RULES:
        for kw in kws:
            if kw.lower() in t.lower():
                return cat
    return "其它"


items = []
for i, bv in enumerate(BVS):
    try:
        info = resolve_bili("https://www.bilibili.com/video/" + bv)
        title = (info.get("title") or "").strip()
        dur = info.get("duration")
        cat = classify(title)
        items.append({"bvid": bv, "title": title, "duration": dur, "category": cat})
        print(f"[{i+1}/{len(BVS)}] {cat}  {info.get('duration')}s  {title[:40]}", flush=True)
    except Exception as exc:
        print(f"[{i+1}/{len(BVS)}] FAIL {bv}: {type(exc).__name__} {exc}", flush=True)
    time.sleep(0.4)

with open("_manifest.json", "w", encoding="utf-8") as fh:
    json.dump(items, fh, ensure_ascii=False, indent=2)
print("RESULT items:", len(items))
