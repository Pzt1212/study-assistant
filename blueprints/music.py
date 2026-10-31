# -*- coding: utf-8 -*-
"""背景音乐播放器蓝图（模块六升级版）。

升级内容：
- 不再读取 static/music/ 本地目录；
- 改为调用内置在线曲目源（SoundHelix 公共音频/可环境变量覆盖为自有在线 API）；
- 新增「脑波音频」分类：双耳节拍由前端 Web Audio 实时合成（离线可用）；
- 提供曲目列表 / 搜索 API，播放控制完全由前端 JS 完成。
"""
from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import login_required

from services import music_source

music = Blueprint("music", __name__, template_folder="../templates")


def _cfg():
    return current_app.config


@music.route("/music")
@login_required
def index():
    """音乐播放器页面：注入曲目与分类。"""
    return render_template(
        "music.html",
        tracks=music_source.list_all_tracks(_cfg()),
        categories=music_source.category_stats(_cfg()),
    )


@music.route("/music/api/tracks")
@login_required
def api_tracks():
    """曲目列表 API（JSON），供前端刷新播放列表与分类筛选。"""
    return jsonify(
        ok=True,
        tracks=music_source.list_all_tracks(_cfg()),
        categories=music_source.category_stats(_cfg()),
    )


@music.route("/music/api/search")
@login_required
def api_search():
    """按名称 / 描述搜索在线曲目与脑波音频。"""
    q = request.args.get("q", "").strip()
    return jsonify(ok=True, tracks=music_source.search_tracks(q, _cfg()))
