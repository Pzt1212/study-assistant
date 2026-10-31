# -*- coding: utf-8 -*-
"""视频源服务：B站链接解析 + 本地已下载视频 + 直链。

- 解析 B 站视频链接（BV号 / av号 / 完整URL / 分P），用官方公开接口拿标题与分P；
  播放用 B 站官方 iframe 播放器（无需登录、稳定、支持后台）。
- 本地视频：扫描 video/downloads/ 目录（BBDown 下载产物），供直接播放。
- 直链：任意 http(s) 视频文件直链。
"""
import hashlib
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request

# B站 视频 BV / av / 完整链接 提取
_BVID_RE = re.compile(r"(BV[0-9A-Za-z]{10})")
_AV_RE = re.compile(r"(?:av|aid)[=/]?(\d+)", re.I)
_PAGE_RE = re.compile(r"\?p=(\d+)")
_BILI_EDGE = "https://api.bilibili.com"

# 本机已下载视频目录（相对项目根）
_DL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "video", "downloads")

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


class VideoResolveError(Exception):
    """视频解析失败。"""


def _http_get(url, referer=None, timeout=20):
    headers = {"User-Agent": _UA, "Accept": "application/json"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def parse_bili_link(text):
    """从任意输入提取 (bvid, aid, page)，未匹配返回 None。"""
    text = text or ""
    bvid = _BVID_RE.search(text)
    av = _AV_RE.search(text)
    page = _PAGE_RE.search(text)
    return {
        "bvid": bvid.group(1) if bvid else None,
        "aid": av.group(1) if av else None,
        "page": int(page.group(1)) if page else 1,
    }


def resolve_bili(text):
    """解析 B 站链接 → 播放信息 dict。失败抛 VideoResolveError。"""
    parsed = parse_bili_link(text)
    if not (parsed["bvid"] or parsed["aid"]):
        raise VideoResolveError("无法识别 B 站链接，请粘贴 BV 号 / av 号 / 完整链接。")

    view_url = _BILI_EDGE + "/x/web-interface/view?"
    if parsed["bvid"]:
        view_url += "bvid=" + parsed["bvid"]
    else:
        view_url += "aid=" + parsed["aid"]

    try:
        data = json.loads(_http_get(view_url, referer="https://www.bilibili.com/"))
    except Exception as exc:
        raise VideoResolveError(f"B 站接口请求失败：{exc}")

    if data.get("code") != 0 or not data.get("data"):
        raise VideoResolveError(f"B 站返回错误：{data.get('message', '未知')}")

    d = data["data"]
    bvid = d.get("bvid") or parsed["bvid"]
    pages = d.get("pages") or []
    page_idx = max(0, min(parsed["page"] - 1, len(pages) - 1)) if pages else 0
    page = pages[page_idx] if pages else None

    return {
        "kind": "bili",
        "source": "bilibili",
        "bvid": bvid,
        "cid": page.get("cid") if page else None,
        "page": page_idx + 1,
        "total_pages": len(pages),
        "title": d.get("title"),
        "duration": d.get("duration"),
        "author": d.get("owner", {}).get("name"),
        # B 站官方 iframe 播放器（免登录、稳定支持后台播放）
        "embed_url": (
            "https://player.bilibili.com/player.html?bvid=" + bvid +
            "&page=" + str(page_idx + 1) + "&high_quality=1&danmaku=1&autoplay=0"
        ),
        "proxy_url": None,
    }


def _safe_name(name, ext):
    try:
        s = re.sub(r'[\\/:*?"<>|\n\r\t]', "_", (name or "video").strip())
    except Exception:
        s = "video"
    return (s[:120] or "video") + ext


def list_local_videos():
    """递归扫描 video/downloads/**/*.{mp4,flv,webm,m4a,...}，返回可播放列表。

    兼容顶层文件与分类子目录；跳过下载残留分片（.P1.<cid>.mp4/.m4a 等）。
    """
    import re as _re
    result = []
    if not os.path.isdir(_DL_DIR):
        return result
    part_re = _re.compile(r"\.P\d+\.\d+\.(mp4|m4a)$", _re.I)
    for dirpath, _dirs, files in os.walk(_DL_DIR):
        for fn in sorted(files):
            ext = os.path.splitext(fn)[1].lower()
            if ext not in (".mp4", ".flv", ".webm", ".m4a", ".mov", ".mkv"):
                continue
            if part_re.search(fn):
                continue
            full = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(full) <= 0:
                    continue
            except OSError:
                continue
            rel = os.path.relpath(full, _DL_DIR).replace("\\", "/")
            folder = os.path.basename(dirpath) if dirpath != _DL_DIR else ""
            result.append({
                "kind": "local",
                "source": "local",
                "title": os.path.splitext(fn)[0],
                "file": rel,
                "ext": ext.lstrip("."),
                "size": os.path.getsize(full),
                "folder": folder,
            })
    result.sort(key=lambda v: (v.get("folder", "").lower(), v["file"].lower()))
    return result


# ---------------- 封面帧缩略图 ----------------
_THUMB_DIR = os.path.join(_DL_DIR, ".thumbs")
_FFMPEG_EXE = os.path.join(os.path.dirname(_DL_DIR), "bin",
                           "ffmpeg-master-latest-win64-gpl", "bin", "ffmpeg.exe")
_MEDIA_EXTS = (".mp4", ".flv", ".webm", ".m4a", ".mov", ".mkv")


def _thumb_abs(file_rel):
    return os.path.join(_THUMB_DIR, hashlib.sha1(file_rel.encode("utf-8")).hexdigest() + ".jpg")


def ensure_thumbnail(file_rel):
    """为 video/downloads/ 下本地视频生成/复用封面帧（第 1 秒一帧，缓存于 .thumbs/）。

    返回缓存 jpg 的绝对路径；失败返回 None。
    """
    dl = _DL_DIR
    full = os.path.normpath(os.path.join(dl, file_rel))
    if not (full == dl or full.startswith(dl + os.sep)):
        return None
    if not os.path.isfile(full) or os.path.splitext(full)[1].lower() not in _MEDIA_EXTS:
        return None
    out = _thumb_abs(file_rel)
    if os.path.isfile(out) and os.path.getsize(out) > 0:
        return out
    if not os.path.exists(_FFMPEG_EXE):
        return None
    os.makedirs(_THUMB_DIR, exist_ok=True)
    # 临时名也以 .jpg 结尾，否则 ffmpeg 无法推断输出格式
    tmp = out[:-4] + ".tmp.jpg"
    cmd = [_FFMPEG_EXE, "-y", "-ss", "1", "-i", full, "-frames:v", "1",
           "-vf", "scale=480:-2", "-q:v", "4", tmp]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=90, check=True)
    except Exception:
        return None
    if os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
        os.replace(tmp, out)
        return out
    return None
