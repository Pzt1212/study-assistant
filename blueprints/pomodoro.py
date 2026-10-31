# -*- coding: utf-8 -*-
"""番茄钟蓝图。

页面负责计时展示（前端 JS 驱动倒计时），后端提供：
- 完成记录持久化（每次完成一个番茄钟写一条记录）
- 今日完成数 / 最近 7 天统计
"""
from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from models import (
    add_pomodoro_record,
    get_recent_daily_focus,
    get_today_focus_count,
)

pomodoro = Blueprint("pomodoro", __name__, template_folder="../templates")


@login_required
@pomodoro.route("/pomodoro")
def index():
    """番茄钟页面。渲染初始统计并返回模板。"""
    uid = current_user.id
    return render_template(
        "pomodoro.html",
        today_focus=get_today_focus_count(uid),
        daily_focus=get_recent_daily_focus(uid, days=7),
        # 默认时长（分钟），前端可自定义并保存在 localStorage
        focus_min=25,
        short_min=5,
        long_min=15,
    )


@pomodoro.route("/pomodoro/record", methods=["POST"])
@login_required
def record():
    """记录一个完成的番茄钟（前端 JS 在倒计时结束时调用）。

    请求体 JSON：{"mode": "focus|short_break|long_break", "duration_seconds": 1500}
    响应 JSON：{"ok": true, "today_focus": N}
    """
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "focus")
    if mode not in ("focus", "short_break", "long_break"):
        return jsonify(ok=False, error="非法模式"), 400

    try:
        duration = int(data.get("duration_seconds", 0))
    except (TypeError, ValueError):
        duration = 0
    if duration <= 0:
        return jsonify(ok=False, error="时长非法"), 400

    add_pomodoro_record(current_user.id, mode, duration)
    return jsonify(
        ok=True,
        today_focus=get_today_focus_count(current_user.id),
    )


@pomodoro.route("/pomodoro/api/stats")
@login_required
def api_stats():
    """返回今日完成数 + 最近 7 天统计（JSON）。"""
    uid = current_user.id
    return jsonify(
        today_focus=get_today_focus_count(uid),
        daily_focus=get_recent_daily_focus(uid, days=7),
    )