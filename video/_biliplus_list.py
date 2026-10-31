# -*- coding: utf-8 -*-
"""用 BiliPlus 代理拉 TheGreatStill 视频列表（绕 B 站强风控）。"""
import json
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
MID = 113861412
out = []


def get(url, referer=None):
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


cands = [
    ("biliplus space", f"https://api.biliplus.com/api/space/video?mid={MID}&pn=1&ps=50"),
    ("biliplus arc", f"https://api.biliplus.com/x/space/arc/search?mid={MID}&pn=1&ps=50"),
    ("biliplus search", f"https://api.biliplus.com/api/search?keyword=TheGreatStill&type=user"),
]
for name, url in cands:
    try:
        r = get(url, referer="https://space.bilibili.com/%d" % MID)
        out.append(f"== {name} code={r.get('code')} msg={r.get('message')} keys={list(r.keys())[:6]}")
        # 抓 vlist
        vlist = ((r.get("data") or {}).get("list") or {}).get("vlist") or (r.get("data") or {}).get("vlist") or []
        d = r.get("data")
        if isinstance(d, dict) and "list" in d and isinstance(d["list"], list):
            vlist = d["list"]
        if isinstance(vlist, list):
            for v in vlist[:20]:
                out.append(f"   BV={v.get('bvid')} title={v.get('title')} tname={v.get('tname')} len={v.get('length')}")
    except Exception as exc:
        out.append(f"== {name} [EXC] {type(exc).__name__} {exc}")

with open("_biliplus_list.txt", "w", encoding="utf-8") as fh:
    fh.write("\n".join(out))
print("\n".join(out))
