# -*- coding: utf-8 -*-
"""全局搜索蓝图。

支持搜索：
- 笔记标题与内容
- 题目题干与解析、科目名
结果分组展示（笔记 / 题目），点击可跳转详情。
"""
from flask import Blueprint, render_template, request
from flask_login import current_user, login_required

from models import search_notes, search_questions

search = Blueprint("search", __name__, template_folder="../templates")


@search.route("/search")
@login_required
def index():
    """全局搜索页。查询参数：?q=关键字"""
    q = request.args.get("q", "").strip()
    notes = questions = []
    if q:
        notes = search_notes(current_user.id, q)
        questions = search_questions(current_user.id, q)
    return render_template(
        "search/results.html", q=q, notes=notes, questions=questions
    )