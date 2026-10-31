# -*- coding: utf-8 -*-
"""背景音乐曲目源服务（在线音频源 + 脑波音频）。

设计（模块六升级后）：
- 播放器不再扫描 static/music/ 本地目录；
- 改为「内置曲目源目录」提供两类曲目：
    * online    在线轻音乐（远程 mp3 直链，浏览器流式播放，不占本地空间）
    * brainwave 脑波音频（双耳节拍，前端 Web Audio 实时合成，离线可播）
- 在线曲目源可用环境变量 MUSIC_STREAM_URLS 覆盖（接入自有在线音频 API 时用）。

说明：内置在线曲目来自公共演示音频站（SoundHelix，CC 式免费示例），
仅用于功能演示与联调；正式使用时建议通过 MUSIC_STREAM_URLS 换为
自己接入的在线音乐 API（如网易云/咪咕开放接口等返回的直链地址）。
"""
import json
import os

from config import Config

# ------------------------------------------------------------
# 分类
# ------------------------------------------------------------
CATEGORY_STREAM = "online"
CATEGORY_BRAINWAVE = "brainwave"

CATEGORIES = [
    {"id": CATEGORY_STREAM, "name": "在线轻音乐", "icon": "",
     "desc": "流式播放的在线曲目（需网络）"},
    {"id": CATEGORY_BRAINWAVE, "name": "脑波音频", "icon": "",
     "desc": "双耳节拍，建议佩戴耳机（本地合成，离线可用）"},
]

# ------------------------------------------------------------
# 内置在线曲目（默认源：SoundHelix 公共演示音频）
# 可通过环境变量 MUSIC_STREAM_URLS 覆盖为自有曲目源列表
# ------------------------------------------------------------
_SOUNDHELIX_TEMPLATE = "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-{n}.mp3"

_DEFAULT_STREAM_TRACKS = [
    {"name": "在线 · 轻音乐 1（SoundHelix）", "artist": "SoundHelix", "url": _SOUNDHELIX_TEMPLATE.format(n=1)},
    {"name": "在线 · 轻音乐 2（SoundHelix）", "artist": "SoundHelix", "url": _SOUNDHELIX_TEMPLATE.format(n=2)},
    {"name": "在线 · 轻音乐 3（SoundHelix）", "artist": "SoundHelix", "url": _SOUNDHELIX_TEMPLATE.format(n=3)},
    {"name": "在线 · 轻音乐 4（SoundHelix）", "artist": "SoundHelix", "url": _SOUNDHELIX_TEMPLATE.format(n=4)},
    {"name": "在线 · 轻音乐 5（SoundHelix）", "artist": "SoundHelix", "url": _SOUNDHELIX_TEMPLATE.format(n=5)},
    {"name": "在线 · 轻音乐 6（SoundHelix）", "artist": "SoundHelix", "url": _SOUNDHELIX_TEMPLATE.format(n=6)},
    {"name": "在线 · 轻音乐 7（SoundHelix）", "artist": "SoundHelix", "url": _SOUNDHELIX_TEMPLATE.format(n=7)},
    {"name": "在线 · 轻音乐 8（SoundHelix）", "artist": "SoundHelix", "url": _SOUNDHELIX_TEMPLATE.format(n=8)},
]

# ------------------------------------------------------------
# 内置脑波音频（双耳节拍预设：base = 载波频率，beat = 左右耳频率差）
# 格式说明：kind="binaural"，前端用 Web Audio 双振荡器左右声道合成
# ------------------------------------------------------------
_BRAINWAVE_TRACKS = [
    {"name": "深度专注 · Alpha（10 Hz）", "artist": "脑波音频",
     "category": CATEGORY_BRAINWAVE, "kind": "binaural",
     "binaural": {"base": 200, "beat": 10}, "wave": "sine",
     "desc": "10 Hz α 波，适合阅读/做题的轻度专注"},
    {"name": "高效学习 · Beta（14 Hz）", "artist": "脑波音频",
     "category": CATEGORY_BRAINWAVE, "kind": "binaural",
     "binaural": {"base": 220, "beat": 14}, "wave": "sine",
     "desc": "14 Hz β 波，提升警觉与信息处理"},
    {"name": "放松冥想 · Theta（6 Hz）", "artist": "脑波音频",
     "category": CATEGORY_BRAINWAVE, "kind": "binaural",
     "binaural": {"base": 180, "beat": 6}, "wave": "sine",
     "desc": "6 Hz θ 波，放松、记忆巩固"},
    {"name": "助眠舒压 · Delta（2.5 Hz）", "artist": "脑波音频",
     "category": CATEGORY_BRAINWAVE, "kind": "binaural",
     "binaural": {"base": 150, "beat": 2.5}, "wave": "sine",
     "desc": "2.5 Hz δ 波，深度放松/助眠"},
]


def _load_stream_tracks(app_config=None):
    """读取在线曲目：优先环境变量 MUSIC_STREAM_URLS（JSON），否则用内置目录。"""
    raw = ""
    if app_config is not None:
        raw = (app_config.get("MUSIC_STREAM_URLS")
               if isinstance(app_config, dict)
               else getattr(app_config, "MUSIC_STREAM_URLS", "")) or ""
    else:
        raw = os.environ.get("MUSIC_STREAM_URLS", "") or Config.MUSIC_STREAM_URLS or ""
    raw = raw or Config.MUSIC_STREAM_URLS or ""
    tracks = []
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict) and item.get("name") and item.get("url"):
                        tracks.append({
                            "name": item["name"],
                            "artist": item.get("artist", "") or "在线音频",
                            "url": item["url"],
                        })
        except (ValueError, TypeError):
            pass
    if not tracks:
        tracks = [dict(t) for t in _DEFAULT_STREAM_TRACKS]
    return tracks


def _track(t, category, kind, index, **extra):
    """把原始条目归一化为播放器数据结构。"""
    base = {
        "id": f"{category}-{index + 1}",
        "name": t["name"],
        "artist": t.get("artist", "") or ("在线音频" if category == CATEGORY_STREAM else "脑波音频"),
        "category": category,
        "kind": kind,
    }
    base.update(extra)
    base.update({k: v for k, v in t.items() if k not in ("name", "artist")})
    return base


def list_all_tracks(app_config=None):
    """返回全部曲目（在线流媒体 + 脑波音频）。"""
    tracks = []
    for i, t in enumerate(_load_stream_tracks(app_config)):
        item = dict(t)
        item.pop("category", None)
        item.pop("kind", None)
        tracks.append(_track(item, CATEGORY_STREAM, "stream", i))
    for i, t in enumerate(_BRAINWAVE_TRACKS):
        tracks.append(_track(t, CATEGORY_BRAINWAVE, "binaural", i))
    return tracks


def list_tracks(category=None, app_config=None):
    """按分类过滤曲目；category 为空返回全部。"""
    tracks = list_all_tracks(app_config)
    if category:
        tracks = [t for t in tracks if t["category"] == category]
    return tracks


def search_tracks(keyword, app_config=None):
    """按名称/描述模糊搜索曲目（大小写不敏感）。"""
    keyword = (keyword or "").strip().lower()
    if not keyword:
        return []
    tracks = list_all_tracks(app_config)
    return [
        t for t in tracks
        if keyword in t["name"].lower()
        or keyword in (t.get("desc") or "").lower()
        or keyword in t["artist"].lower()
    ]


def category_stats(app_config=None):
    """每个分类的曲目数量统计（前端分类筛选用）。"""
    tracks = list_all_tracks(app_config)
    stats = {c["id"]: 0 for c in CATEGORIES}
    for t in tracks:
        if t["category"] in stats:
            stats[t["category"]] += 1
    return [
        {**c, "count": stats.get(c["id"], 0)}
        for c in CATEGORIES
    ]
