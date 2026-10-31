# -*- coding: utf-8 -*-
"""题库蓝图。

功能：
- 题目增删改查（新增 / 编辑 / 删除）
- 按学科、主题、题型、难度筛选 + 关键字过滤
- 刷题模式：按题型随机抽题、即时判分、显示解析
  - 选择题：单选作答，自动判分
  - 填空题：文本输入，去首尾空白后与标准答案比对
  - 解答题：展示参考答案 + 评分标准，用户自评得分
- 答题统计（正确 / 错误 / 正确率）
"""
import json
import os
import re

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from models import (
    create_question,
    delete_question,
    get_question,
    get_quiz_stats,
    get_random_question,
    list_questions,
    list_subjects,
    record_answer,
    set_question_image,
    update_question,
    get_questions_by_filter,
    get_distinct_subjects,
    get_distinct_topics,
    get_distinct_types,
    get_distinct_difficulties,
)
from services.question_image import generate_math_image

questions = Blueprint("questions", __name__, template_folder="../templates")

# 合法答案选项
VALID_ANSWERS = ("A", "B", "C", "D")

# 题型定义（与题库生成器、列表页筛选取值一致）
QUESTION_TYPE_CHOICE = "选择题"
QUESTION_TYPE_FILL = "填空题"
QUESTION_TYPE_ANSWER = "解答题"
QUESTION_TYPES = (QUESTION_TYPE_CHOICE, QUESTION_TYPE_FILL, QUESTION_TYPE_ANSWER)

# 分值兜底：题目的 score 为空时按题型套用默认分值
DEFAULT_SCORE_CHOICE = 3     # 选择题默认 3 分
DEFAULT_SCORE_FILL = 3       # 填空题默认 3 分
DEFAULT_SCORE_ANSWER = 10    # 解答题默认 10 分


# ============================================================
# 页面路由
# ============================================================
@questions.route("/questions")
@login_required
def index():
    """题目列表页：支持按学科、主题、题型、难度筛选 + 关键字过滤。"""
    uid = current_user.id
    subject = request.args.get("subject", "").strip()
    topic = request.args.get("topic", "").strip()
    qtype = request.args.get("type", "").strip()
    difficulty = request.args.get("difficulty", "").strip()
    keyword = request.args.get("q", "").strip()

    # 搜索关键字与 学科/主题/题型/难度 筛选可同时生效（修复旧版“有搜索就丢筛选”）
    items = get_questions_by_filter(
        uid,
        subject=subject or None,
        topic=topic or None,
        question_type=qtype or None,
        difficulty=difficulty or None,
        keyword=keyword or None,
    )

    return render_template(
        "questions/list.html",
        questions=items,
        subjects=get_distinct_subjects(uid),
        topics=get_distinct_topics(uid, subject or None),
        types=get_distinct_types(uid),
        difficulties=get_distinct_difficulties(uid),
        current_subject=subject,
        current_topic=topic,
        current_type=qtype,
        current_difficulty=difficulty,
        keyword=keyword,
        stats=get_quiz_stats(uid),
    )


def _auto_image(question_id, subject, content):
    """数学题：题目无配图时自动生成示意图（SVG 存 static/img/q/，路径写库）。"""
    if (subject or "").strip() != "数学":
        return
    if not content:
        return
    svg = generate_math_image(content)
    if not svg:
        return
    img_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "static", "img", "q")
    os.makedirs(img_dir, exist_ok=True)
    rel = "/static/img/q/q%d.svg" % question_id
    try:
        with open(os.path.join(img_dir, "q%d.svg" % question_id), "w", encoding="utf-8") as fh:
            fh.write(svg)
        set_question_image(question_id, rel)
    except OSError:
        pass


@questions.route("/questions/new", methods=["GET", "POST"])
@login_required
def new():
    """新增题目。"""
    if request.method == "POST":
        data = _read_form()
        error = _validate_form(data)
        if error:
            flash(error, "error")
            return render_template("questions/form.html", q=data, subjects=_user_subjects())

        qid = create_question(current_user.id, **data)
        _auto_image(qid, data["subject"], data["content"])
        flash("题目已添加。", "success")
        return redirect(url_for("questions.index"))

    # GET：初始化一个空表单，预填最近使用过的科目，方便连续录入
    data = {
        "subject": request.args.get("subject", ""),
        "topic": "", "grade": "",
        "question_type": QUESTION_TYPE_CHOICE,
        "difficulty": "中等", "score": DEFAULT_SCORE_CHOICE,
        "content": "",
        "option_a": "", "option_b": "", "option_c": "", "option_d": "",
        "answer": "A", "analysis": "",
    }
    return render_template("questions/form.html", q=data, subjects=_user_subjects())


@questions.route("/questions/<int:question_id>/edit", methods=["GET", "POST"])
@login_required
def edit(question_id):
    """编辑题目。"""
    question = get_question(question_id, current_user.id)
    if not question:
        abort(404)

    if request.method == "POST":
        data = _read_form()
        error = _validate_form(data)
        if error:
            flash(error, "error")
            return render_template("questions/form.html", q=data, subjects=_user_subjects())

        update_question(question_id, current_user.id, **data)
        # 原题若无配图，更新后尝试自动生成（仅数学）
        if not (question["image"] or ""):
            _auto_image(question_id, data["subject"], data["content"])
        flash("题目已更新。", "success")
        return redirect(url_for("questions.index"))

    # GET：用数据库现有值填充表单
    data = {
        "subject": question["subject"],
        "topic": question["topic"] or "",
        "grade": question["grade"] or "",
        "question_type": _question_type_of(question),
        "difficulty": question["difficulty"] or "中等",
        "score": question["score"] or _default_score(question),
        "content": question["content"],
        "option_a": question["option_a"],
        "option_b": question["option_b"],
        "option_c": question["option_c"],
        "option_d": question["option_d"],
        "answer": question["answer"],
        "analysis": question["analysis"],
        "image": question["image"] or "",
    }
    return render_template("questions/form.html", q=data, subjects=_user_subjects())


@questions.route("/questions/<int:question_id>/delete", methods=["POST"])
@login_required
def delete(question_id):
    """删除题目（POST 方法，防止误删）。"""
    if not get_question(question_id, current_user.id):
        abort(404)
    delete_question(question_id, current_user.id)
    flash("题目已删除。", "info")
    return redirect(url_for("questions.index"))


@questions.route("/questions/quiz")
@login_required
def quiz():
    """刷题模式页面：提供学科/难度/题型三个筛选下拉框的数据源。"""
    uid = current_user.id
    # 数据来源与题库列表页一致：学科取当前用户实际存在的科目
    subjects = get_distinct_subjects(uid)
    difficulties = get_distinct_difficulties(uid) or ["简单", "中等", "较难"]
    return render_template(
        "questions/quiz.html",
        stats=get_quiz_stats(uid),
        types=QUESTION_TYPES,
        subjects=subjects,
        difficulties=difficulties,
    )


# ============================================================
# API 路由（刷题模式用）
# ============================================================
@questions.route("/questions/api/random")
@login_required
def api_random():
    """随机抽一道题，返回题干与选项（不返回答案，由服务端判分）。

    支持 GET 参数组合过滤（三者可同时使用，均为可选项）：
    - subject=    学科过滤（如 数学 / 物理）
    - difficulty= 难度过滤（简单 / 中等 / 较难）
    - type=       题型过滤：
        - 缺省 / type=全部：选择题、填空题、解答题混合抽取
        - type=选择题 / 填空题 / 解答题：只抽对应题型
    """
    qtype = request.args.get("type", "").strip()
    subject = request.args.get("subject", "").strip()
    difficulty = request.args.get("difficulty", "").strip()

    question = get_random_question(
        current_user.id,
        question_type=qtype or None,
        subject=subject or None,
        difficulty=difficulty or None,
    )
    if not question:
        # 区分“没题目”与“没符合筛选条件的题目”，给出可操作的提示
        active = []
        if qtype:
            active.append(f"题型「{qtype}」")
        if subject:
            active.append(f"学科「{subject}」")
        if difficulty:
            active.append(f"难度「{difficulty}」")
        if active:
            cond = "、".join(active)
            return jsonify(
                ok=False,
                error=f"没有符合「{cond}」条件的题目，试试放宽筛选条件，或去题库添加题目。",
            ), 404
        return jsonify(ok=False, error="题库为空，请先添加题目。"), 404

    # 手工新增的题目未设置题型，按选择题展示与作答
    question_type = _question_type_of(question)

    payload = {
        "id": question["id"],
        "subject": question["subject"],
        "topic": question["topic"] or "未分类",
        "question_type": question_type,
        "difficulty": question["difficulty"] or "中等",
        "score": _default_score(question),
        "content": question["content"],
        "image": question["image"] or "",
        "options": [],
    }
    # 只有选择题返回 A/B/C/D 四个选项，其余题型由前端渲染输入框
    if question_type == QUESTION_TYPE_CHOICE:
        payload["options"] = [
            {"key": "A", "text": question["option_a"]},
            {"key": "B", "text": question["option_b"]},
            {"key": "C", "text": question["option_c"]},
            {"key": "D", "text": question["option_d"]},
        ]

    return jsonify(ok=True, question=payload)


@questions.route("/questions/api/answer", methods=["POST"])
@login_required
def api_answer():
    """提交答案。

    请求体：{"question_id": 1, "answer": "..."}
    按题型分别处理：
    - 选择题：answer 为 A/B/C/D，服务端自动判分并记录；
    - 填空题：answer 为输入文本，去除首尾空白后与标准答案比对判分；
    - 解答题：answer 为用户书写的解答过程，本接口不判分，
      返回参考答案 + 解析 + 评分标准，由前端引导用户自评（见 api_grade）。
    响应：{ok, answer_type, correct?, correct_answer?, analysis, stats, ...}
    """
    data = request.get_json(silent=True) or {}
    question_id = data.get("question_id")
    raw_answer = data.get("answer")
    answer = str(raw_answer if raw_answer is not None else "").strip()

    question = get_question(question_id, current_user.id)
    if not question:
        return jsonify(ok=False, error="题目不存在或已被删除。"), 404

    question_type = _question_type_of(question)
    full_score = _default_score(question)

    # ---- 选择题：单选自动判分 ----
    if question_type == QUESTION_TYPE_CHOICE:
        answer = answer.upper()
        if answer not in VALID_ANSWERS:
            return jsonify(ok=False, error="请选择一个答案。"), 400

        is_correct = answer == question["answer"]
        record_answer(current_user.id, question_id, answer, is_correct,
                      score=full_score if is_correct else 0)
        return jsonify(
            ok=True,
            answer_type=question_type,
            correct=is_correct,
            correct_answer=question["answer"],
            analysis=question["analysis"] or "",
            stats=get_quiz_stats(current_user.id),
        )

    # ---- 填空题：文本比对自动判分 ----
    if question_type == QUESTION_TYPE_FILL:
        if not answer:
            return jsonify(ok=False, error="请填写答案。"), 400

        is_correct = _fill_is_correct(answer, question["answer"])
        record_answer(current_user.id, question_id, answer, is_correct,
                      score=full_score if is_correct else 0)
        return jsonify(
            ok=True,
            answer_type=question_type,
            correct=is_correct,
            correct_answer=question["answer"],
            analysis=question["analysis"] or "",
            stats=get_quiz_stats(current_user.id),
        )

    # ---- 解答题：不判分，先展示参考答案与评分标准供用户自评 ----
    return jsonify(
        ok=True,
        answer_type=QUESTION_TYPE_ANSWER,
        reference_answer=question["answer"],
        analysis=question["analysis"] or "",
        step_rules=_parse_step_rules(question["step_rules"]),
        full_score=full_score,
        stats=get_quiz_stats(current_user.id),
    )


@questions.route("/questions/api/grade", methods=["POST"])
@login_required
def api_grade():
    """解答题自评得分接口。

    请求体：{"question_id": 1, "answer": "用户解答过程", "score": 8}
    流程：刷题页先展示参考答案 + 评分标准，用户对照评分标准自评得分后
    提交本接口，服务端把解答过程与自评得分记入答题记录。
    自评得满分时视为正确（参与正确率统计），否则视为错误。
    响应：{ok, correct, score, full_score, stats}
    """
    data = request.get_json(silent=True) or {}
    question_id = data.get("question_id")
    raw_answer = data.get("answer")
    answer = str(raw_answer if raw_answer is not None else "").strip()

    question = get_question(question_id, current_user.id)
    if not question:
        return jsonify(ok=False, error="题目不存在或已被删除。"), 404
    if _question_type_of(question) != QUESTION_TYPE_ANSWER:
        return jsonify(ok=False, error="只有解答题支持自评得分。"), 400

    full_score = _default_score(question)
    try:
        score = int(float(str(data.get("score", 0))))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="自评得分必须是数字。"), 400
    # 得分限制在 0 ~ 满分之间，防止前端传入越界值
    score = max(0, min(score, full_score))

    # 自评得满分视为做对（供正确率统计），否则按错误记录
    is_correct = score >= full_score
    record_answer(current_user.id, question_id, answer, is_correct, score=score)

    return jsonify(
        ok=True,
        answer_type=QUESTION_TYPE_ANSWER,
        correct=is_correct,
        score=score,
        full_score=full_score,
        stats=get_quiz_stats(current_user.id),
    )


# ============================================================
# 题型与判分辅助
# ============================================================
def _question_type_of(question):
    """返回题目实际题型。

    手工在表单新增的题目没有设置 question_type（NULL / 空字符串），
    列表页与刷题页都按选择题处理，这里做同样的归一化。
    """
    qtype = (question["question_type"] or "").strip()
    return qtype if qtype in QUESTION_TYPES else QUESTION_TYPE_CHOICE


def _default_score(question):
    """返回题目分值；题目没设置分值（score 为 NULL）时按题型套用默认值。"""
    if question["score"]:
        return int(question["score"])
    qtype = _question_type_of(question)
    if qtype == QUESTION_TYPE_ANSWER:
        return DEFAULT_SCORE_ANSWER
    if qtype == QUESTION_TYPE_FILL:
        return DEFAULT_SCORE_FILL
    return DEFAULT_SCORE_CHOICE


def _fill_is_correct(user_answer, standard_answer):
    """填空题判分：答案文本比对。

    规则：
    1. 去除首尾空白后再比较（大小写不敏感）；
    2. 支持标准答案用「或」连接的多个等价答案（如「1/2 或 0.5」）；
    3. 比较时忽略答案内部空白，容忍「4 / 5」写成「4/5」这类小差异。
    """
    user = (user_answer or "").strip()
    if not user:
        return False
    standard = (standard_answer or "").strip()
    if not standard:
        return False

    user_compact = re.sub(r"\s+", "", user)

    for alternative in standard.split("或"):
        alt = alternative.strip()
        if not alt:
            continue
        # 完全一致（忽略大小写），或忽略内部空白后一致
        if user.casefold() == alt.casefold():
            return True
        if user_compact.casefold() == re.sub(r"\s+", "", alt).casefold():
            return True
    return False


def _parse_step_rules(raw):
    """把 step_rules（JSON 字符串）解析为 dict；空值 / 非法 JSON 返回空 dict。"""
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


# ============================================================
# 表单辅助
# ============================================================
def _read_form():
    """读取并整理表单数据（含分类 / 题型 / 难度等扩展字段）。"""
    qtype = (request.form.get("question_type", "") or "").strip()
    # 兼容旧表单：未显式选择题型时按选择题处理
    if qtype not in QUESTION_TYPES:
        qtype = QUESTION_TYPE_CHOICE
    score_raw = (request.form.get("score", "") or "").strip()
    score = None
    try:
        if score_raw:
            score = max(0, int(float(score_raw)))
    except (TypeError, ValueError):
        score = None

    def _opt(name):
        # 非选择题提交的选项字段忽略
        v = request.form.get(name, "").strip()
        return v if qtype == QUESTION_TYPE_CHOICE else ""

    return {
        "subject": request.form.get("subject", "").strip(),
        "topic": request.form.get("topic", "").strip(),
        "grade": request.form.get("grade", "").strip(),
        "question_type": qtype,
        "difficulty": (request.form.get("difficulty", "") or "").strip() or None,
        "score": score,
        "content": request.form.get("content", "").strip(),
        "option_a": _opt("option_a"),
        "option_b": _opt("option_b"),
        "option_c": _opt("option_c"),
        "option_d": _opt("option_d"),
        # 选择题答案来自 answer_choice（A~D）；填空/解答题答案来自 answer_text；
        # 兼容旧表单/旧测试直接提交的 answer 字段。
        "answer": (
            request.form.get("answer_choice")
            or request.form.get("answer_text")
            or request.form.get("answer")
            or ""
        ).strip().upper(),
        "analysis": request.form.get("analysis", "").strip(),
    }


def _validate_form(data):
    """按题型校验题目表单，返回错误信息字符串；通过则返回 None。"""
    if not data["subject"]:
        return "科目不能为空。"
    if not data["content"]:
        return "题干不能为空。"
    qtype = data.get("question_type") or QUESTION_TYPE_CHOICE
    answer = (data.get("answer") or "").strip()
    if qtype == QUESTION_TYPE_CHOICE:
        if not all([data["option_a"], data["option_b"], data["option_c"], data["option_d"]]):
            return "四个选项（A/B/C/D）都必须填写。"
        if answer not in VALID_ANSWERS:
            return "正确答案必须是 A / B / C / D 之一。"
    else:
        # 填空题 / 解答题：不要求选项，但答案不能为空
        if not answer:
            return "请填写本题答案（填空/解答题答案或参考答案）。"
    return None


def _user_subjects():
    """返回当前用户的科目名列表（供表单下拉建议）。"""
    return [row["subject"] for row in list_subjects(current_user.id)]