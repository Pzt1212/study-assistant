# -*- coding: utf-8 -*-
"""按分类统计时长/预估大小，排序生成 ≤20GB 的下载队列。"""
import json

import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "_manifest.json"), "r", encoding="utf-8") as fh:
    items = json.load(fh)

# 480P 实测码率约 0.1MB/s（250MB/2400s）→ 每视频大小
GB = 20.0
rate_kbps = 0.105  # MB/s
MAX_MB = GB * 1024

for it in items:
    it["est_mb"] = round(it["duration"] * rate_kbps, 1)

cats = {}
for it in items:
    cats.setdefault(it["category"], []).append(it)
print("=== 分类统计 ===")
for c, lst in cats.items():
    tot_mb = sum(x["est_mb"] for x in lst)
    print(f"{c}: {len(lst)} 个  共约 {tot_mb/1024:.1f} GB")

# 按分类内时长升序（先下短的能多装），构造预算队列
print("\n=== 预算队列（≤20GB，短→长）===")
queue = []
used = 0.0
skip = 0
for c in sorted(cats):
    for it in sorted(cats[c], key=lambda x: x["duration"]):
        if used + it["est_mb"] / 1024 > GB:
            skip += 1
            continue
        queue.append(it)
        used += it["est_mb"] / 1024

print(f"纳入 {len(queue)} 个，剩余预算 ≈{GB-used:.2f}GB，跳过 {skip} 个")
sizes = [it["est_mb"] for it in queue]
print("预计总大小 ≈ %.2f GB" % (sum(sizes)/1024))

with open(os.path.join(ROOT, "_queue.json"), "w", encoding="utf-8") as fh:
    json.dump([{"bvid": x["bvid"], "category": x["category"]} for x in queue],
              fh, ensure_ascii=False, indent=2)
