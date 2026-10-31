# -*- coding: utf-8 -*-
"""手写体本地 OCR 插件封装（可选依赖 rapidocr-onnxruntime）。

设计说明：
- rapidocr-onnxruntime 内置 PP-OCRv4 模型，可离线识别印刷体与手写体中英文，
  是 /ocr 页面「手写体」模式的首选本地引擎（无需联网、无需 API Key）。
- 该包体积较大（含 ONNX 推理引擎与模型），因此未写入 requirements.txt 主清单，
  需要时执行：pip install -r requirements-handwriting.txt
- 插件不可用时 handwriting_plugin_available() 返回 False，调用方给出友好提示，
  并可按策略降级到本地 Tesseract（见 services/ocr_service.py 的 _handwrite_ocr）。
"""
import os

PLUGIN_NAME = "rapidocr-onnxruntime"

# 模型/引擎进程级缓存（重复识别不重复加载模型）
_ENGINE = None


def handwriting_plugin_available() -> bool:
    """检测手写识别插件是否可导入（不真正加载模型，速度快）。"""
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except Exception:
        return False


def _get_engine():
    """懒加载并缓存 RapidOCR 引擎。"""
    global _ENGINE
    if _ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR

        _ENGINE = RapidOCR()
    return _ENGINE


def recognize_handwriting(image_path: str) -> str:
    """对图片执行手写体识别，返回拼接后的文本（按行）。

    :param image_path: 图片文件绝对路径
    :return: 识别文本；无文字时返回空字符串
    :raises OCRUnavailableError: 插件缺失或识别失败（携带友好提示）
    """
    if not os.path.exists(image_path):
        from services.ocr_service import OCRUnavailableError

        raise OCRUnavailableError("图片文件不存在，请重新上传。")

    try:
        engine = _get_engine()
    except Exception:
        from services.ocr_service import OCRUnavailableError

        raise OCRUnavailableError(
            "手写识别插件不可用。请执行 `pip install -r requirements-handwriting.txt` "
            "安装 rapidocr-onnxruntime 后重试；或在页面选择「印刷体」模式。"
        )

    try:
        # result: [box, text, score] 的嵌套列表；第二项为识别文本
        result, _elapse = engine(image_path)
    except Exception as exc:  # noqa: BLE001 - 所有底层错误都转为友好提示
        from services.ocr_service import OCRUnavailableError

        raise OCRUnavailableError(f"手写识别执行失败：{exc}")

    if not result:
        return ""
    lines = [str(item[1]).strip() for item in result if len(item) >= 2 and str(item[1]).strip()]
    return "\n".join(lines)
