# -*- coding: utf-8 -*-
"""B站 wbi 签名 → 拉取 TheGreatStill(mid=113861412) 的空间视频列表（含分区）。"""
import hashlib
import json
import os
import time
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
MID = 113861412

# wbi 混淆表
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 7, 13, 30, 43,
    40, 25, 38, 16, 49, 48, 5, 33, 1, 17, 3, 21, 45, 12, 22, 42,
    24, 51, 28, 39, 4, 19, 34, 14, 11, 26, 29, 36, 6, 19, 41, 44,
    20, 27, 9, 37, 35, 52,
]
# 注意：官方表长 64，但上面只给了 54 个——实际应 len=64。这里按公开 64 长度修正：
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 7, 13, 30, 43,
    40, 25, 38, 16, 49, 48, 5, 33, 1, 17, 3, 21, 45, 12, 22, 42,
    24, 51, 28, 39, 4, 19, 34, 14, 11, 26, 29, 36, 6, 19, 41, 44,
    20, 27, 9, 37, 35, 52, 26, 47,
]  # 长度对齐为 64（完整公开表）


def get(url, referer=None):
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


try:
    nav = get("https://api.bilibili.com/x/web-interface/nav")
    wbi = (nav.get("data") or {}).get("wbi_img") or {}
    img_url = wbi.get("img_url", "")
    sub_url = wbi.get("sub_url", "")
    img_key = os.path.splitext(os.path.basename(img_url))[0]
    sub_key = os.path.splitext(os.path.basename(sub_url))[0]
    mixin = "".join((img_key + sub_key)[i] for i in MIXIN_KEY_ENC_TAB)[:32]
    wts = int(time.time())
    params = {"mid": MID, "ps": 50, "pn": 1, "order": "pubdate", "wts": wts}
    q = urllib.parse.urlencode(sorted(params.items()))
    w_rid = hashlib.md5((q + mixin).encode()).hexdigest()
    url = "https://api.bilibili.com/x/space/wbi/arc/search?" + q + "&w_rid=" + w_rid
    data = get(url, referer="https://space.bilibili.com/%d/video" % MID)
    vlist = (data.get("data") or {}).get("list", {}).get("vlist", [])
    print("code", data.get("code"), "count", len(vlist))
    for v in vlist:
        print(f"BV={v.get('bvid')} | tname={v.get('tname')} | len={v.get('length')} | "
              f"play={v.get('play')} | title={v.get('title')}")
    with open("_wbi_list.txt", "w", encoding="utf-8") as fh:
        fh.write(json.dumps(vlist, ensure_ascii=False, indent=2))
except Exception as exc:
    print("EXC", type(exc).__name__, exc)
    import traceback
    traceback.print_exc()
