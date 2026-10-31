# -*- coding: utf-8 -*-
"""笔记模块蓝图。

功能：
- 列表展示 / 关键字过滤
- 新建笔记（手写标题 + 正文）
- 在线编辑 / 删除
- 文件上传：txt/md 直接读取，图片走 OCR 提取文字
  存储时使用 uuid 重命名，避免文件名冲突
- 查看笔记详情
"""
import os
import re
import uuid

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required

from models import (
    create_note,
    delete_note,
    get_note,
    get_note_by_stored_filename,
    list_notes,
    update_note,
)
from services.ocr_service import OCRUnavailableError
from services.text_extract import UnsupportedFileTypeError, extract_text
from services.file_guard import is_safe_stored_filename, remove_uploaded_file

notes = Blueprint("notes", __name__, template_folder="../templates")


def allowed_file(filename: str) -> bool:
    """判断上传文件名扩展名是否在允许列表中。"""
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    return ext in current_app.config["ALLOWED_UPLOAD_EXTENSIONS"]


@notes.route("/notes")
@login_required
def index():
    """笔记列表页，支持 ?q= 关键字过滤。"""
    keyword = request.args.get("q", "").strip()
    items = list_notes(current_user.id, keyword=keyword or None)
    return render_template("notes/list.html", notes=items, keyword=keyword)


def _editor_type(form, current_file_type=""):
    """根据编辑器模式返回落库 file_type：手写 → svg；纯文本模式显式切换则 → text。

    后端以此为依据决定内容按「文本」还是「手写 SVG」渲染，杜绝把任意
    用户文本当 SVG 输出（XSS 防护）。
    """
    mode = (form.get("editor_mode", "") or "text").strip().lower()
    if mode in ("handwrite", "svg", "手写"):
        return "svg"
    if mode == "text" and current_file_type == "svg":
        return "text"
    return None  # 其它情况保持原类型不变


# 手写 SVG 白名单（与 static/js/notes_form.js 的序列化产物一一对应）：
#   svg(width/height/viewBox) · rect(x/y/width/height/fill) · path(d/fill/stroke/...)
_ALLOWED_SVG_TAGS = {"svg", "rect", "path", "line", "circle", "polyline", "polygon", "g", "title", "desc"}
_ALLOWED_SVG_ATTRS = {
    "xmlns", "width", "height", "viewbox", "x", "y", "d", "fill", "stroke",
    "stroke-width", "stroke-linecap", "stroke-linejoin", "cx", "cy", "r", "points",
    "opacity", "transform",
}
_TAG_RE = re.compile(r"<\s*([A-Za-z][A-Za-z0-9]*)([^>]*)>", re.S)


def _sanitize_svg_content(content):
    """手写笔记 SVG 的白名单净化（防御存储型 XSS）。

    只保留安全标签与属性，其余一律剥除；任何带引号/协议的属性值会被清掉，
    `javascript:` / `data:` / on* 等全部不通过属性白名单。可保留注释与原始文本节点。
    """
    if not content:
        return content

    def _clean_attrs(attrs_raw):
        out = []
        for m in re.finditer(r"""([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)""", attrs_raw):
            name = m.group(1).lower()
            value = m.group(2).strip()
            if value[:1] in ('"', "'"):
                value = value[1:-1]
            if name not in _ALLOWED_SVG_ATTRS:
                continue
            if not value:
                continue
            low = value.lower()
            if "javascript" in low or "&#" in low or "&colon" in low:
                continue
            out.append('%s="%s"' % (m.group(1), value))
        return " ".join(out)

    def _repl(mm):
        tag = mm.group(1)
        attrs_raw = mm.group(2) or ""
        if tag.lower() not in _ALLOWED_SVG_TAGS:
            return ""
        if ">" in attrs_raw:  # 异常输入，丢弃整段
            return ""
        cleaned = _clean_attrs(attrs_raw)
        if cleaned:
            return "<%s %s>" % (tag, cleaned)
        return "<%s>" % tag

    # 逐标签清理（> 后内容/文本/注释原样保留）
    cleaned = _TAG_RE.sub(_repl, content)
    # 清理危险标签的残留闭合片段与首尾孤儿文本
    cleaned = re.sub(r"(?is)</\s*(script|iframe|object|embed|foreignobject|image|style)\s*>", "", cleaned)
    return cleaned


@notes.route("/notes/new", methods=["GET", "POST"])
@login_required
def new():
    """新建笔记（手动输入 / 手写绘图）。"""
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "")
        if not title:
            flash("笔记标题不能为空。", "error")
            return render_template("notes/form.html", note=None, title=title, content=content)

        note_id = create_note(
            current_user.id, title,
            _sanitize_svg_content(content) if _editor_type(request.form) == "svg" else content,
            file_type=_editor_type(request.form) or "text",
        )
        flash("笔记已创建。", "success")
        return redirect(url_for("notes.edit", note_id=note_id))

    return render_template("notes/form.html", note=None, title="", content="")


@notes.route("/notes/<int:note_id>")
@login_required
def detail(note_id):
    """查看笔记详情。"""
    note = get_note(note_id, current_user.id)
    if not note:
        abort(404)
    # 渲染端二次净化（兜底历史存量 svg），确保 |safe 输出的是白名单内容
    if (note["file_type"] or "") == "svg":
        note = dict(note)
        note["content"] = _sanitize_svg_content(note["content"] or "")
    return render_template("notes/detail.html", note=note)


@notes.route("/notes/<int:note_id>/edit", methods=["GET", "POST"])
@login_required
def edit(note_id):
    """编辑笔记。"""
    note = get_note(note_id, current_user.id)
    if not note:
        abort(404)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "")
        if not title:
            flash("笔记标题不能为空。", "error")
            return render_template("notes/form.html", note=note, title=title, content=content)

        new_type = _editor_type(request.form, note["file_type"] or "")
        if new_type == "svg":
            content = _sanitize_svg_content(content)
        update_note(
            note_id, current_user.id, title, content,
            file_type=new_type,
        )
        flash("笔记已保存。", "success")
        return redirect(url_for("notes.detail", note_id=note_id))

    return render_template("notes/form.html", note=note, title=note["title"], content=note["content"])


@notes.route("/notes/<int:note_id>/delete", methods=["POST"])
@login_required
def delete(note_id):
    """删除笔记（POST，防误删）。"""
    note = get_note(note_id, current_user.id)
    if not note:
        abort(404)

    # 同时清理上传的源文件（如果存在；统一走安全守卫，防路径穿越）
    if note["stored_filename"]:
        remove_uploaded_file(current_app.config["UPLOAD_FOLDER"], note["stored_filename"])

    delete_note(note_id, current_user.id)
    flash("笔记已删除。", "info")
    return redirect(url_for("notes.index"))


@notes.route("/notes/upload", methods=["GET", "POST"])
@login_required
def upload():
    """上传文件并自动提取文本生成笔记。

    流程：
    1. 校验文件存在、扩展名合法
    2. 用 uuid 重命名保存到 uploads/ 目录（避免文件名冲突）
    3. 提取文本（txt/md 直接读，图片走 OCR）
    4. 以原文件名作为标题创建笔记
    """
    if request.method == "POST":
        file = request.files.get("file")
        if not file or not file.filename:
            flash("请选择要上传的文件。", "error")
            return redirect(url_for("notes.upload"))

        original_name = os.path.basename(file.filename)
        if not allowed_file(original_name):
            flash("不支持的文件类型。支持：txt / md / markdown / 常见图片格式。", "error")
            return redirect(url_for("notes.upload"))

        # 使用 uuid 生成存储文件名，彻底避免重名冲突
        ext = os.path.splitext(original_name)[1].lower().lstrip(".")
        stored_filename = f"{uuid.uuid4().hex}.{ext}"
        upload_dir = current_app.config["UPLOAD_FOLDER"]
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, stored_filename)
        file.save(file_path)

        # 提取文本：失败时给出友好提示，但保留原文件信息（可再次尝试）
        try:
            content = extract_text(file_path, original_name, current_app.config)
        except (OCRUnavailableError, UnsupportedFileTypeError) as exc:
            flash(f"文本提取失败：{exc}", "error")
            # 仍创建一条笔记，便于用户手动补充内容
            note_id = create_note(
                current_user.id,
                original_name,
                "",
                source_filename=original_name,
                stored_filename=stored_filename,
                file_type=ext,
            )
            return redirect(url_for("notes.edit", note_id=note_id))

        title = os.path.splitext(original_name)[0]  # 去扩展名作标题
        note_id = create_note(
            current_user.id,
            title,
            content,
            source_filename=original_name,
            stored_filename=stored_filename,
            file_type=ext,
        )
        flash(f"上传成功，已自动提取 {len(content)} 个字符。", "success")
        return redirect(url_for("notes.detail", note_id=note_id))

    return render_template("notes/upload.html")


@notes.route("/notes/files/<path:filename>")
@login_required
def serve_upload(filename):
    """提供上传文件的访问。

    归属校验（IDOR 防护）：文件必须对应当前用户自己的一条笔记；
    协管及以上（内容治理）可查看任意上传文件。文件名同时走安全白名单。
    """
    if not is_safe_stored_filename(filename):
        abort(404)
    note = get_note_by_stored_filename(filename)
    if not note:
        abort(404)
    if note["user_id"] != current_user.id and current_user.role < 1:
        abort(403)

    upload_dir = current_app.config["UPLOAD_FOLDER"]
    # send_from_directory 自带路径穿越防护
    return send_from_directory(upload_dir, filename)