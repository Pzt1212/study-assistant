# -*- coding: utf-8 -*-
"""在线题库蓝图（路由前缀 /question-bank）。

功能：
- 页面展示「接入你自己的题库 API」表单：填写接口地址、令牌与题目；
- 每行一题，逐题查询答案后写入当前用户的题库；
- 接口地址/令牌可预先通过环境变量配置（QUESTION_BANK_API_URL /
  QUESTION_BANK_TOKEN），页面留空时自动取用；
- WKAPI_ENABLED=False 时整页查询功能关闭。

项目不内置任何题目与令牌，导入结果取决于你所接入的接口。
"""
from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from models import create_question
from services.question_bank import (
    QuestionBankError,
    WKAPI_MAX_QUESTIONS,
    fetch_questions,
)

question_bank = Blueprint(
    "question_bank", __name__, url_prefix="/question-bank",
    template_folder="../templates",
)


@question_bank.route("")
@login_required
def index():
    """在线题库首页：展示用户自备 API 的接入表单。"""
    cfg = current_app.config
    return render_template(
        "question_bank/index.html",
        max_questions=WKAPI_MAX_QUESTIONS,
        enabled=cfg.get("WKAPI_ENABLED", True),
        api_url=cfg.get("QUESTION_BANK_API_URL", ""),
        token_configured=bool(cfg.get("QUESTION_BANK_TOKEN")),
    )


@question_bank.route("/import", methods=["POST"])
@login_required
def import_questions():
    """按题目逐题查询答案，并写入当前用户题库。"""
    cfg = current_app.config
    if not cfg.get("WKAPI_ENABLED", True):
        flash("在线题库功能已被管理员关闭。", "error")
        return redirect(url_for("question_bank.index"))

    api_url = request.form.get("api_url", "").strip() or cfg.get("QUESTION_BANK_API_URL", "")
    token = request.form.get("token", "").strip() or cfg.get("QUESTION_BANK_TOKEN", "")

    if not api_url:
        flash("请填写你的题库 API 地址（或设置环境变量 QUESTION_BANK_API_URL）。", "error")
        return redirect(url_for("question_bank.index"))

    question_list = [
        line.strip() for line in request.form.get("questions", "").splitlines()
        if line.strip()
    ][:WKAPI_MAX_QUESTIONS]
    if not question_list:
        flash("请输入至少一道题目（每行一题）。", "error")
        return redirect(url_for("question_bank.index"))

    try:
        items = fetch_questions(api_url, question_list, token=token)
    except QuestionBankError as exc:
        flash(f"在线题库导入失败：{exc}", "error")
        return redirect(url_for("question_bank.index"))

    uid = current_user.id
    for q in items:
        create_question(uid, q["subject"], q["content"], q["option_a"],
                        q["option_b"], q["option_c"], q["option_d"],
                        q["answer"], q["analysis"])
    flash(f"已通过在线题库导入 {len(items)} 道题目。", "success")
    return redirect(url_for("questions.index"))
