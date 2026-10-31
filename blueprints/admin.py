# -*- coding: utf-8 -*-
"""后台管理蓝图（管理员专属，路由前缀 /admin）。

功能：
- 概览页：用户 / 题目 / 笔记 / 答题记录 / 番茄记录统计
- 用户管理：列表（含各自内容量）、设为/取消管理员、删除用户
- 全站题目管理：查看 / 搜索 / 删除（可删任意用户的题）
- 全站笔记管理：查看 / 搜索 / 删除（删除时清理上传文件）
- OCR 服务状态页：展示当前各 OCR 引擎与配置情况

保护逻辑：
- admin_required：先校验登录，再校验 is_admin，非管理员返回 403
- 不能删除自己；系统至少保留 1 名管理员
"""
from functools import wraps
import os

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from models import (
    ROLE_ADMIN,
    ROLE_LABELS,
    ROLE_MOD,
    ROLE_SUPER,
    count_admins,
    count_super_admins,
    delete_note_any,
    delete_question_any,
    delete_user_by_id,
    get_note_any,
    get_overview_stats,
    get_recent_users,
    get_site_daily_focus,
    get_user_by_id,
    get_user_notes_for_cleanup,
    list_all_notes,
    list_all_questions,
    list_all_subjects,
    list_users_with_stats,
    set_user_role,
)
from services.file_guard import remove_uploaded_file

admin = Blueprint("admin", __name__, url_prefix="/admin", template_folder="../templates")
# ============================================================
# 权限装饰器：先登录，再校验管理员身份
# ============================================================
def role_required(min_role):
    """按角色层级限制的装饰器工厂。

    用法：@role_required(models.ROLE_ADMIN) —— 角色数字 >= min_role 才能访问，
    否则返回 403；未登录由 Flask-Login 重定向登录页。
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role < min_role:
                abort(403)
            return view_func(*args, **kwargs)
        return wrapped
    return decorator


# 兼容旧名：admin_required == 协管及以上可访问
admin_required = role_required(ROLE_MOD)


# ============================================================
# 概览页
# ============================================================
@admin.route("")
@role_required(ROLE_ADMIN)
def index():
    """后台概览：全站各类数据统计卡片 + 最近专注趋势 + 最新注册。"""
    stats = get_overview_stats()
    site_focus = get_site_daily_focus(7)
    return render_template(
        "admin/index.html",
        stats=stats,
        total_users=stats["users"],
        admins=count_admins(),
        site_focus=site_focus,
        site_focus_max=max((d["count"] for d in site_focus), default=0) or 1,
        recent_users=get_recent_users(6),
    )


# ============================================================
# 用户管理
# ============================================================
@admin.route("/users")
@role_required(ROLE_ADMIN)
def users():
    """用户管理列表，附每个用户的内容量统计，支持关键字过滤。"""
    keyword = request.args.get("q", "").strip()
    items = list_users_with_stats(keyword=keyword or None)
    return render_template("admin/users.html", users=items, keyword=keyword)


@admin.route("/users/<int:user_id>/set-role", methods=["POST"])
@role_required(ROLE_SUPER)
def set_role(user_id):
    """设置用户角色（0 普通 / 1 协管 / 2 管理员 / 3 超级管理员）。

    仅超级管理员可任免；不能修改自己的角色（防自降/自升造成越权）；
    系统至少保留 1 名超级管理员。
    """
    user = get_user_by_id(user_id)
    if not user:
        abort(404)

    role_raw = request.form.get("role", "").strip()
    try:
        new_role = int(role_raw)
    except (TypeError, ValueError):
        flash("无效的角色值。", "error")
        return redirect(url_for("admin.users"))
    if new_role not in ROLE_LABELS:
        flash("无效的角色值。", "error")
        return redirect(url_for("admin.users"))

    if user.id == current_user.id:
        flash("不能修改自己的角色，请由另一位超级管理员操作。", "error")
        return redirect(url_for("admin.users"))

    # 系统至少保留 1 名超管：不能把唯一一位超管降级
    if user.role == ROLE_SUPER and new_role < ROLE_SUPER and count_super_admins() <= 1:
        flash("系统至少需要保留 1 名超级管理员，无法降级该用户。", "error")
        return redirect(url_for("admin.users"))

    set_user_role(user_id, new_role)
    flash(f"已将「{user.username}」的角色设为：{ROLE_LABELS[new_role]}。", "success")
    return redirect(url_for("admin.users"))


@admin.route("/users/<int:user_id>/delete", methods=["POST"])
@role_required(ROLE_ADMIN)
def delete_user(user_id):
    """删除用户（连同其题目 / 笔记 / 答题记录 / 番茄记录）。

    保护：不能删除自己；管理员不能删除超级管理员（超管仅可由超管删除）。
    """
    user = get_user_by_id(user_id)
    if not user:
        abort(404)
    if user.id == current_user.id:
        flash("不能删除当前登录的管理员账号。", "error")
        return redirect(url_for("admin.users"))
    if user.role >= ROLE_SUPER and current_user.role < ROLE_SUPER:
        flash("不能删除超级管理员账号。", "error")
        return redirect(url_for("admin.users"))

    # 先清理该用户上传的文件，再删除数据库记录（笔记等通过外键级联删除）
    # 统一走安全守卫，防 stored 路径穿越
    for note in get_user_notes_for_cleanup(user_id):
        if note["stored_filename"]:
            remove_uploaded_file(current_app.config["UPLOAD_FOLDER"], note["stored_filename"])

    delete_user_by_id(user_id)
    flash(f"已删除用户「{user.username}」及其全部数据。", "info")
    return redirect(url_for("admin.users"))


# ============================================================
# 全站题目管理
# ============================================================
@admin.route("/questions")
@role_required(ROLE_MOD)
def questions():
    """全站题目列表：支持按科目 / 关键字过滤。"""
    subject = request.args.get("subject", "").strip()
    keyword = request.args.get("q", "").strip()
    items = list_all_questions(subject=subject or None, keyword=keyword or None)
    return render_template(
        "admin/questions.html",
        questions=items,
        subjects=list_all_subjects(),
        current_subject=subject,
        keyword=keyword,
    )


@admin.route("/questions/<int:question_id>/delete", methods=["POST"])
@role_required(ROLE_MOD)
def delete_question(question_id):
    """删除任意用户的题目（其答题记录级联删除）。"""
    delete_question_any(question_id)
    flash(f"已删除题目 #{question_id}。", "info")
    return redirect(url_for("admin.questions", subject=request.form.get("subject", "")))


# ============================================================
# 全站笔记管理
# ============================================================
@admin.route("/notes")
@role_required(ROLE_MOD)
def notes():
    """全站笔记列表：支持按标题 / 内容关键字过滤。"""
    keyword = request.args.get("q", "").strip()
    items = list_all_notes(keyword=keyword or None)
    return render_template("admin/notes.html", notes=items, keyword=keyword)


@admin.route("/notes/<int:note_id>/delete", methods=["POST"])
@role_required(ROLE_MOD)
def delete_note(note_id):
    """删除任意用户的笔记，同时清理上传的源文件。"""
    note = get_note_any(note_id)
    if note:
        if note["stored_filename"]:
            remove_uploaded_file(current_app.config["UPLOAD_FOLDER"], note["stored_filename"])
        delete_note_any(note_id)
        flash(f"已删除笔记 #{note_id}。", "info")
    else:
        flash(f"笔记 #{note_id} 不存在。", "error")
    return redirect(url_for("admin.notes"))


# ============================================================
# OCR 服务状态
# ============================================================
@admin.route("/ocr-status")
@role_required(ROLE_ADMIN)
def ocr_status():
    """OCR 服务状态页：展示当前引擎与各引擎配置情况。

    只显示密钥是否已配置（不暴露密钥本身），便于运维排查。
    """
    cfg = current_app.config

    def _mask(key):
        """密钥脱敏：仅保留前 4 位与后 2 位，其余用 * 代替。"""
        if not key:
            return ""
        if len(key) <= 8:
            return key[:2] + "*" * (len(key) - 2)
        return key[:4] + "*" * (len(key) - 6) + key[-2:]

    provider = (cfg.get("OCR_PROVIDER") or "").strip().lower()
    if not provider:
        provider = "online" if cfg.get("OCR_ENGINE") == "online" else "local"

    # 本地引擎依赖检测：pytesseract + Pillow 是否可导入（不保证引擎二进制可用）
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
        tesseract_importable = True
    except ImportError:
        tesseract_importable = False

    # 手写识别插件（rapidocr-onnxruntime）检测
    from services.handwriting_ocr import handwriting_plugin_available
    from services.ocr_service import bundled_tesseract_path, resolve_tesseract_cmd

    resolved_cmd = resolve_tesseract_cmd(cfg)
    status = {
        # 当前生效的引擎
        "provider": provider,
        "provider_label": {
            "local": "本地 Tesseract（默认）",
            "ocrspace": "OCR.space 在线接口",
            "baidu": "百度智能云 OCR",
            "online": "自定义在线 API",
        }.get(provider, provider),
        # 本地引擎
        "tesseract_cmd": cfg.get("TESSERACT_CMD", "") or "（未指定，自动探测）",
        "tesseract_resolved": resolved_cmd or "",
        "tesseract_bundled": bundled_tesseract_path(),
        "tesseract_available": bool(resolved_cmd),
        "ocr_lang": cfg.get("OCR_LANG", "chi_sim+eng"),
        "tesseract_deps_ok": tesseract_importable,
        # 手写体本地插件（rapidocr）
        "handwriting_ok": handwriting_plugin_available(),
        "handwriting_plugin": "rapidocr-onnxruntime",
        # OCR.space
        "ocrspace_configured": bool(cfg.get("OCRSPACE_API_KEY")),
        "ocrspace_masked": _mask(cfg.get("OCRSPACE_API_KEY") or ""),
        # 百度 OCR
        "baidu_configured": bool(cfg.get("BAIDU_OCR_API_KEY") and cfg.get("BAIDU_OCR_SECRET_KEY")),
        "baidu_api_key": _mask(cfg.get("BAIDU_OCR_API_KEY") or ""),
        "baidu_secret_key": _mask(cfg.get("BAIDU_OCR_SECRET_KEY") or ""),
        # 自定义在线 API（兼容旧配置）
        "custom_configured": bool(cfg.get("OCR_API_URL") and cfg.get("OCR_API_KEY")),
        "custom_url": cfg.get("OCR_API_URL", "") or "（未配置）",
        # 在线题库（用户自备 API）
        "wkapi_enabled": bool(cfg.get("WKAPI_ENABLED", True)),
        "question_bank_api_url": cfg.get("QUESTION_BANK_API_URL", "") or "（未配置，由用户页面填写）",
        "question_bank_token_configured": bool(cfg.get("QUESTION_BANK_TOKEN")),
    }
    return render_template("admin/ocr_status.html", status=status)