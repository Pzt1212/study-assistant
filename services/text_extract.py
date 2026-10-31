# -*- coding: utf-8 -*-
"""笔记文件文本提取服务。

上传文件后自动提取其中的文本内容，便于后续全文搜索。
支持：
- 纯文本类：txt / md / markdown（直接读取，兼容 UTF-8 / GBK 编码）
- 图片类：png / jpg / jpeg / gif / bmp / webp（调用 OCR 服务识别文字）
暂不支持的类型抛出 UnsupportedFileTypeError，由路由层给出友好提示。
"""
import os

from services import ocr_service


class UnsupportedFileTypeError(Exception):
    """不支持的文件类型。"""


# 纯文本类扩展名集合
TEXT_EXTENSIONS = {"txt", "md", "markdown"}
# 图片类扩展名集合（走 OCR）
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "bmp", "webp"}


def extract_text(file_path, filename, app_config=None):
    """根据文件扩展名提取文本内容。

    :param file_path: 文件绝对路径
    :param filename:  原始文件名（用于判断扩展名）
    :param app_config: 应用配置（透传给 OCR 服务）
    :return: 提取出的文本字符串
    :raises UnsupportedFileTypeError: 不支持的文件类型
    """
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    if ext in TEXT_EXTENSIONS:
        return _read_text_file(file_path)
    if ext in IMAGE_EXTENSIONS:
        # 图片交给 OCR 识别文字
        return ocr_service.extract_text_from_image(file_path, app_config)
    raise UnsupportedFileTypeError(
        f"暂不支持 .{ext} 类型的文件。支持：txt / md / markdown / 常见图片格式。"
    )


def _read_text_file(file_path):
    """读取文本文件，自动尝试多种常见编码，避免中文乱码。"""
    encodings = ["utf-8", "utf-8-sig", "gbk", "gb2312", "big5", "latin-1"]
    for enc in encodings:
        try:
            with open(file_path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    # 兜底：忽略无法解码的字节
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()
