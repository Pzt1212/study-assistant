# -*- coding: utf-8 -*-
"""用 wbi 签名 + 搜索接口按标题反查 BV 号（验证 B 站搜索是否可用）。"""
import hashlib
import json
import os
import time
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 7, 13, 30, 43,
    40, 25, 38, 16, 49, 48, 5, 33, 1, 17, 3, 21, 45, 12, 22, 42,
    24, 51, 28, 39, 4, 19, 34, 14, 11, 26, 29, 36, 6, 19, 41, 44,
    27, 9, 37, 35, 52, 26, 47, 46,
]


def get(url, referer=None):
    headers = {"User-Agent": UA, "Accept": "application/json", "Referer": referer or "https://search.bilibili.com/"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


try:
    nav = get("https://api.bilibili.com/x/web-interface/nav")
    wbi = (nav.get("data") or {}).get("wbi_img") or {}
    img_key = os.path.splitext(os.path.basename(wbi.get("img_url", "")))[0]
    sub_key = os.path.splitext(os.path.basename(wbi.get("sub_url", "")))[0]
    mixin = "".join((img_key + sub_key)[i] for i in MIXIN_KEY_ENC_TAB)[:32]
    kw = "ADHD 强制重启 专注力"
    params = {"search_type": "video", "keyword": kw, "page": 1, "wts": int(time.time())}
    q = urllib.parse.urlencode(sorted(params.items()))
    w_rid = hashlib.md5((q + mixin).encode()).hexdigest()
    url = "https://api.bilibili.com/x/web-interface/search/type?" + q + "&w_rid=" + w_rid
    r = get(url, referer="https://search.bilibili.com/all?keyword=" + urllib.parse.quote(kw))
    print("code", r.get("code"), "msg", r.get("message"))
    res = r.get("data", {}).get("result") or []
    for v in res[:8]:
        print(f"  BV={v.get('bvid')} title={v.get('title')}")
except Exception as exc:
    print("EXC", type(exc).__name__, exc)
    import traceback; traceback.print_exc()
