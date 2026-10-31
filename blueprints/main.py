# -*- coding: utf-8 -*-
"""首页 / 仪表盘蓝图。

展示学习概况：今日番茄数、笔记总数、题目总数、答题正确率，
以及最近 7 天番茄钟统计柱状图数据。

另提供无需登录的健康检查接口 /api/health 与 /healthz，
供本地脚本、内网穿透服务与公网监控探测服务是否存活。
"""
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from models import (
    count_notes,
    count_questions,
    get_quiz_stats,
    get_recent_daily_focus,
    get_today_focus_count,
    update_user_avatar,
)

main = Blueprint("main", __name__, template_folder="../templates")


@main.route("/")
@login_required
def dashboard():
    """仪表盘首页：聚合展示各类学习统计数据。"""
    uid = current_user.id
    context = {
        "today_focus": get_today_focus_count(uid),
        "note_count": count_notes(uid),
        "question_count": count_questions(uid),
        "quiz_stats": get_quiz_stats(uid),
        "daily_focus": get_recent_daily_focus(uid, days=7),
    }
    return render_template("dashboard.html", **context)


@main.route("/api/health")
def health():
    """健康检查（JSON）：内网穿透 / 监控探针用，无需登录，不返回敏感信息。"""
    return jsonify(
        ok=True,
        app="study-assistant",
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@main.route("/api/avatar", methods=["POST"])
@login_required
def api_avatar():
    """更新当前用户头像（自定义头像，前端即时刷新）。

    请求体 JSON：{"kind": "text", "value": "A", "color": "#e8b34b"}   # 字母/文字头像（底色）
             或  {"kind": "image", "value": "data:image/...;base64,..."}  # 已压缩的小图
             或  {}  表示清除头像
    """
    data = request.get_json(silent=True) or {}
    kind = (data.get("kind") or "").strip().lower()
    value = (data.get("value") or "").strip()
    color = (data.get("color") or "").strip()

    if not kind or not value:
        update_user_avatar(current_user.id, None)
        return jsonify(ok=True, avatar=None)

    if kind in ("emoji", "text"):
        # 兼容旧版 emoji 头像；新 UI 使用 text（字母）头像
        if len(value) > 8:
            return jsonify(ok=False, error="内容不合法。"), 400
        payload = {"kind": kind, "value": value, "color": color or "#d9dde3"}
    else:
        # 仅接受 data:image 前缀的小图（前端已压缩 ≤128px），避免撑爆数据库
        if kind != "image" or not value.startswith("data:image/") or len(value) > 400 * 1024:
            return jsonify(ok=False, error="图片格式不合法（请使用压缩后的小图）。"), 400
        payload = {"kind": "image", "value": value}

    update_user_avatar(current_user.id, payload)
    return jsonify(ok=True, avatar=payload)


@main.route("/healthz")
def healthz():
    """极简存活探测：返回纯文本 ok（部分负载均衡/监控器只认 200 文本）。"""
    return "ok\n"