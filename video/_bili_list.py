# -*- coding: utf-8 -*-
"""多接口探测 TheGreatStill(mid=113861412) 的视频列表与分区。"""
import json
import re
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
MID = 113861412
out = []


def get(url, referer="https://space.bilibili.com/" + str(MID) + "/video"):
    headers = {"User-Agent": UA, "Accept": "application/json", "Referer": referer}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=25) as resp:
        body = resp.read().decode("utf-8", "replace")
    try:
        return json.loads(body)
    except Exception:
        return body


candidates = [
    ("space/arc v2", f"https://api.bilibili.com/x/space/arc/search?mid={MID}&ps=50&pn=1&order=pubdate"),
    ("space/wbi/arc", f"https://api.bilibili.com/x/space/wbi/arc/search?mid={MID}&ps=50&pn=1&order=pubdate"),
    ("space/top/arc", f"https://api.bilibili.com/x/space/top/arc?vmid={MID}&ps=50&pn=1&order=pubdate"),
    ("newlist", f"https://api.bilibili.com/x/series/recArchivesByKeywords?mid={MID}&keywords=&ps=50&pn=1"),
]

for name, url in candidates:
    try:
        r = get(url)
        if isinstance(r, str):
            out.append(f"== {name} [non-json] {r[:160]}")
            continue
        code = r.get("code")
        data = r.get("data")
        lst = (data or {}).get("list", {}).get("vlist") or (data or {}).get("list") or []
        out.append(f"== {name} code={code} type={type(data).__name__} items={len(lst) if isinstance(lst,list) else '?'}")
        if isinstance(lst, list):
            for v in lst[:12]:
                out.append(f"   BV={v.get('bvid')} title={v.get('title')} tname={v.get('tname')} len={v.get('length')} published={v.get('created')}")
    except Exception as exc:
        out.append(f"== {name} [EXC] {type(exc).__name__} {exc}")

with open("_bili_list.txt", "w", encoding="utf-8") as fh:
    fh.write("\n".join(out))
print("\n".join(out))
