# -*- coding: utf-8 -*-
"""查 TheGreatStill 的空间视频列表（绕过 412 搜索，用 space arc API + 已知BV反查mid）。"""
import json
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
out = []


def get(url, referer="https://www.bilibili.com/"):
    headers = {"User-Agent": UA, "Accept": "application/json", "Referer": referer}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


# 1) 从已知视频反查 owner mid
view = get("https://api.bilibili.com/x/web-interface/view?bvid=BV1PmDWBKECC")
d = view.get("data", {})
mid = d.get("owner", {}).get("mid")
out.append(f"owner mid={mid} name={d.get('owner',{}).get('name')}")

if mid:
    # 2) 拉该 UP 的空间视频（按发布时间倒序）
    for pn in (1, 2, 3):
        try:
            arc = get(f"https://api.bilibili.com/x/space/wbi/arc/search?mid={mid}&ps=30&pn={pn}")
            vlist = arc.get("data", {}).get("list", {}).get("vlist", [])
            if not vlist:
                break
            for v in vlist:
                out.append(f"  BV={v.get('bvid')} pv={v.get('play')} dur={v.get('length')} title={v.get('title')}")
        except Exception as exc:
            out.append(f"[fail pn{pn}] {type(exc).__name__} {exc}")
            break

with open("_bili_user.txt", "w", encoding="utf-8") as fh:
    fh.write("\n".join(out))
print("\n".join(out))
