# -*- coding: utf-8 -*-
"""OCR 文字识别蓝图。

流程：上传图片 → 识别文字 → 预览/编辑 → 保存为笔记
- 识别失败（缺依赖/未配置引擎）给出友好提示并回退表单
- 结果可在文本域中人工修正后再保存
"""
import os
import uuid

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

from models import create_note
from services.file_guard import is_safe_stored_filename
from services.handwriting_ocr import handwriting_plugin_available
from services.ocr_service import OCRUnavailableError, extract_text_from_image

ocr = Blueprint("ocr", __name__, template_folder="../templates")

# OCR 可处理的图片扩展名
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "bmp", "webp"}


def _normalize_mode(raw):
    """把表单的识别模式归一化：printed / handwrite。"""
    mode = (raw or "").strip().lower()
    return "handwrite" if mode in ("handwrite", "handwritten", "手写", "手写体") else "printed"


def _render(index_mode="printed", preview=None, recognized_text="", ocr_mode="printed"):
    """统一渲染 OCR 页面（携带模式回显与手写插件状态）。"""
    return render_template(
        "ocr/index.html",
        preview=preview,
        recognized_text=recognized_text,
        index_mode=index_mode,
        ocr_mode=ocr_mode,
        handwriting_ok=handwriting_plugin_available(),
    )


@ocr.route("/ocr", methods=["GET", "POST"])
@login_required
def index():
    """OCR 页面。

    GET  — 显示上传表单
    POST — 接收图片 → 识别 → 展示结果（可编辑）
    """
    if request.method == "POST":
        image = request.files.get("image")
        mode = _normalize_mode(request.form.get("mode", "printed"))
        if not image or not image.filename:
            flash("请选择要识别的图片。", "error")
            return _render(index_mode=mode)

        original_name = os.path.basename(image.filename)
        ext = os.path.splitext(original_name)[1].lower().lstrip(".")
        if ext not in IMAGE_EXTENSIONS:
            flash("请上传图片文件（png / jpg / jpeg / gif / bmp / webp）。", "error")
            return _render(index_mode=mode)

        # 用 uuid 保存临时图片，避免重名覆盖
        stored = f"ocr_{uuid.uuid4().hex}.{ext}"
        upload_dir = current_app.config["UPLOAD_FOLDER"]
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, stored)
        image.save(file_path)

        # 执行 OCR 识别（mode: printed 印刷体 / handwrite 手写体）
        try:
            text = extract_text_from_image(file_path, current_app.config, mode=mode)
        except OCRUnavailableError as exc:
            flash(f"OCR 识别不可用：{exc}", "error")
            # 删除临时文件，避免垃圾文件堆积
            if os.path.exists(file_path):
                os.remove(file_path)
            return _render(index_mode=mode)

        if not text:
            text = "（未识别到文字，请检查图片清晰度）"

        return _render(
            index_mode=mode,
            preview=stored,
            recognized_text=text,
            ocr_mode=mode,
        )

    return _render(index_mode="printed")


@ocr.route("/ocr/save", methods=["POST"])
@login_required
def save():
    """将识别（或人工修正后）的文本保存为笔记。"""
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    # 传回图片临时文件名，便于保存时保留原图。
    # 安全：只接受服务端生成的合法 uuid 文件名（防 stored=../../x 穿越删除）。
    stored = request.form.get("stored", "")
    if stored and not is_safe_stored_filename(stored):
        stored = ""  # 非法文件名：丢弃关联文件，仅保存文本

    if not title:
        title = "OCR 识别笔记"
    if not content:
        flash("识别结果为空，无法保存为笔记。", "error")
        return redirect(url_for("ocr.index"))

    note_id = create_note(
        current_user.id,
        title,
        content,
        source_filename=stored,
        stored_filename=stored,
        file_type="image",
    )
    flash("已保存为笔记。", "success")
    return redirect(url_for("notes.detail", note_id=note_id))