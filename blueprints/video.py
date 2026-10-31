# -*- coding: utf-8 -*-
"""视频播放蓝图（/video）。

- /video            播放页：B站链接解析播放 + 本地已下载视频库
- /video/api/resolve  解析 B站链接 → 播放信息（iframe 官方播放器，免登录稳定）
- /video/api/local    列出 video/downloads/ 下的本地视频
"""
import os

from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import login_required

from services.video_source import (
    VideoResolveError,
    ensure_thumbnail,
    list_local_videos,
    resolve_bili,
)

video = Blueprint("video", __name__, template_folder="../templates")

# 本地视频目录（相对 static 服务，需能直接播放）
DOWNLOAD_DIR_NAME = "downloads"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@video.route("/video")
@login_required
def index():
    """视频播放页。"""
    local = list_local_videos()
    return render_template("video/index.html", local=local)


@video.route("/video/api/resolve")
@login_required
def api_resolve():
    """解析 B站视频链接。GET ?url=..."""
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify(ok=False, error="请输入 B 站视频链接或 BV 号。"), 400
    try:
        info = resolve_bili(url)
    except VideoResolveError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    return jsonify(ok=True, video=info)


@video.route("/video/api/local")
@login_required
def api_local():
    """列出本地已下载视频。"""
    return jsonify(ok=True, local=list_local_videos())


@video.route("/video/thumb")
@login_required
def api_thumb():
    """本地视频封面帧（ffmpeg 抽第 1 秒画面，磁盘缓存）。?file=相对路径"""
    from flask import abort, send_file

    rel = (request.args.get("file") or "").strip()
    if not rel:
        abort(400)
    dl_dir = os.path.join(BASE_DIR, "video", DOWNLOAD_DIR_NAME)
    full = os.path.normpath(os.path.join(dl_dir, rel))
    if not (full == dl_dir or full.startswith(dl_dir + os.sep)):
        abort(404)
    thumb = ensure_thumbnail(rel)
    if not thumb:
        abort(404)
    resp = send_file(thumb, mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "public, max-age=604800"
    return resp


@video.route("/video/files/<path:filename>")
@login_required
def serve_local(filename):
    """播放本地已下载视频（安全路径，仅 video/downloads/ 下）。"""
    from flask import send_from_directory

    dl_dir = os.path.join(BASE_DIR, "video", DOWNLOAD_DIR_NAME)
    return send_from_directory(dl_dir, filename)
