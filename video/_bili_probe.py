# -*- coding: utf-8 -*-
"""探测 B 站 API 可达性：搜索 UP 主 + 视频信息解析。"""
import json
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
out = []


def get(url, referer=None):
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


# 1) 搜索 UP 主 TheGreatStill（web 得到 BV1PmDWBKECC）
try:
    r = get("https://api.bilibili.com/x/web-interface/search/type?search_type=bili_user&keyword=TheGreatStill", referer="https://www.bilibili.com/")
    users = r.get("data", {}).get("result", [])[:3]
    for u in users:
        out.append(f"USER mid={u.get('mid')} name={u.get('uname')} sign={str(u.get('usign'))[:60]} vids={u.get('videos')} fans={u.get('fans')}")
except Exception as exc:
    out.append(f"[FAIL search user] {type(exc).__name__} {exc}")

# 2) 视频 BV 解析：取 BV1PmDWBKECC 的详情（cid/pages）
try:
    r = get("https://api.bilibili.com/x/web-interface/view?bvid=BV1PmDWBKECC", referer="https://www.bilibili.com/")
    d = r.get("data", {})
    out.append(f"VIDEO title={d.get('title')} owner={d.get('owner',{}).get('name')} cid={d.get('cid')} duration={d.get('duration')} pages={len(d.get('pages',[]))}")
except Exception as exc:
    out.append(f"[FAIL view] {type(exc).__name__} {exc}")

with open("_bili_probe.txt", "w", encoding="utf-8") as fh:
    fh.write("\n".join(out))
print("\n".join(out))
