# -*- coding: utf-8 -*-
"""OCR 文字识别服务。

模式（mode）：
- printed   印刷体（默认）：本地 pytesseract + Tesseract；也可切 ocrspace / baidu / online
- handwrite 手写体：优先使用本地插件 rapidocr-onnxruntime（离线、无需 Key）；
            插件缺失时若本地 Tesseract 可用则自动降级（提高识别参数的 psm 6），
            两者都不可用时抛出 OCRUnavailableError 给出友好安装提示。

Tesseract 可执行文件解析优先级（模块七「OCR 本地打包」）：
    1. config.TESSERACT_CMD（显式配置，环境变量可覆盖）
    2. 项目内置版本 bin/tesseract/tesseract.exe（自动发现）
    3. 系统 PATH 中的 tesseract

友好降级：无论缺依赖还是缺引擎，都抛出 OCRUnavailableError，
由路由层转为 flash 提示，绝不导致 500。
"""
import os
import shutil

from config import Config

# 常见图片扩展名（印刷/手写 OCR 均支持）
SUPPORTED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "bmp", "webp", "tif", "tiff"}


class OCRUnavailableError(Exception):
    """OCR 功能不可用（缺少依赖 / 未配置 / 识别失败）。"""


# ============================================================
# 配置读取（兼容 Config 类与 Flask config dict）
# ============================================================
def _cfg(cfg, name, default=""):
    """兼容「Config 类属性」与「Flask config 字典」两种取值方式。"""
    if cfg is None:
        return getattr(Config, name, default)
    if isinstance(cfg, dict):
        return cfg.get(name, default)
    return getattr(cfg, name, default)


def bundled_tesseract_path():
    """返回项目内置 Tesseract 的候选路径（不存在时为空字符串）。"""
    return getattr(Config, "BUNDLED_TESSERACT", "") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "bin", "tesseract", "tesseract.exe",
    )


def resolve_tesseract_cmd(app_config=None):
    """按优先级解析可用的 tesseract 可执行文件路径；找不到返回空字符串。"""
    cfg = app_config
    # 1) 显式配置
    explicit = (_cfg(cfg, "TESSERACT_CMD", "") or "").strip()
    candidates = [explicit]
    # 2) 内置打包版本
    candidates.append(bundled_tesseract_path())
    for cand in candidates:
        if cand and os.path.isfile(cand):
            return cand
    # 3) 系统 PATH
    found = shutil.which("tesseract")
    return found or ""


# ============================================================
# 入口
# ============================================================
def extract_text_from_image(image_path, app_config=None, mode="printed"):
    """对一张图片执行 OCR，返回识别出的文本。

    :param image_path: 图片文件的绝对路径
    :param app_config: 应用配置（Config 类或 Flask 的 config）
    :param mode: "printed" 印刷体（默认） / "handwrite" 手写体
    :return: 识别出的文本字符串
    :raises OCRUnavailableError: 引擎不可用或识别失败
    """
    mode = (mode or "printed").strip().lower()
    if mode in ("handwrite", "handwritten", "手写", "手写体"):
        return _handwrite_ocr(image_path, app_config)
    return _printed_ocr(image_path, app_config)


# ============================================================
# 印刷体：provider 链（local / ocrspace / baidu / online）
# ============================================================
def _printed_ocr(image_path, app_config=None):
    cfg = app_config
    provider = (_cfg(cfg, "OCR_PROVIDER", "") or "").strip().lower()
    if not provider:
        engine = (_cfg(cfg, "OCR_ENGINE", "local") or "local").strip().lower()
        provider = "online" if engine == "online" else "local"

    if provider == "ocrspace":
        return _ocrspace_ocr(image_path, cfg)
    if provider == "baidu":
        return _baidu_ocr(image_path, cfg)
    if provider == "online":
        return _online_ocr(image_path, cfg)
    return _local_ocr(image_path, cfg)


# ============================================================
# 手写体：本地插件优先，Tesseract(psm 6) 降级兜底
# ============================================================
def _handwrite_ocr(image_path, app_config=None):
    cfg = app_config

    # 1) 本地手写插件（首选）
    try:
        from services.handwriting_ocr import handwriting_plugin_available, recognize_handwriting
        if handwriting_plugin_available():
            text = recognize_handwriting(image_path)
            return (text or "").strip()
    except OCRUnavailableError:
        # 插件存在但执行失败 → 抛出，避免静默错误
        raise
    except Exception:  # noqa: BLE001 - 插件导入/初始化异常 → 继续尝试降级
        pass

    # 2) 降级：本地 Tesseract 用更利于手写的参数（psm 6 按块识别）
    tesseract_cmd = resolve_tesseract_cmd(cfg)
    if tesseract_cmd:
        text = _local_ocr(image_path, cfg, extra_config="--psm 6")
        if text:
            return text

    # 3) 两者都不可用 → 友好提示
    raise OCRUnavailableError(
        "手写体识别暂不可用：本地手写插件未安装。请执行 "
        "`pip install -r requirements-handwriting.txt` 安装 rapidocr-onnxruntime "
        "（离线可用，无需 API Key）；或返回选择「印刷体」模式。"
    )


# ============================================================
# 本地 Tesseract
# ============================================================
def _local_ocr(image_path, cfg, extra_config=""):
    """本地 Tesseract OCR（自动解析内置/系统引擎路径）。"""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        raise OCRUnavailableError(
            "缺少 OCR 依赖，请执行 `pip install pytesseract Pillow` 后重试。"
        )

    tesseract_cmd = resolve_tesseract_cmd(cfg)
    if not tesseract_cmd:
        raise OCRUnavailableError(
            "未检测到 Tesseract 引擎。解决方案（任选其一）：\n"
            "1) 联网执行 `python tools/setup_tesseract.py` 自动下载内置版本到 "
            "bin/tesseract/（推荐，开箱即用）；\n"
            "2) 从 https://github.com/UB-Mannheim/tesseract/wiki 下载安装 "
            "Tesseract-OCR（安装时勾选中文语言包 chi_sim）；\n"
            "3) 在 config.py 的 TESSERACT_CMD 中填写安装路径。"
        )
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    try:
        image = Image.open(image_path)
    except Exception:
        raise OCRUnavailableError("图片无法打开，请更换图片后重试。")

    # 指定内置版本时把其目录加入 PATH，确保依赖 DLL（如 leptonica）可被加载
    if os.name == "nt" and os.path.isdir(os.path.dirname(tesseract_cmd)):
        os.environ["PATH"] = os.path.dirname(tesseract_cmd) + os.pathsep + os.environ.get("PATH", "")

    lang = _cfg(cfg, "OCR_LANG", "chi_sim+eng") or "eng"

    def _run(lang_code, cfg_text):
        kwargs = {"config": cfg_text} if cfg_text else {}
        try:
            return pytesseract.image_to_string(image, lang=lang_code, **kwargs).strip()
        except pytesseract.TesseractNotFoundError:
            raise OCRUnavailableError(
                "Tesseract 引擎无法启动，请确认文件完整（可重新运行 "
                "tools/setup_tesseract.py 或检查 TESSERACT_CMD 配置）。"
            )
        except Exception:  # noqa: BLE001 - 语言包缺失等
            return None

    text = _run(lang, extra_config)
    if text is None:
        # 指定语言包未安装 → 退而尝试纯英文
        text = _run("eng", extra_config)
    if text is None:
        raise OCRUnavailableError(
            "OCR 识别失败。请确认 Tesseract 已安装且包含所需语言包（chi_sim）。"
        )
    return text


# ============================================================
# 在线 OCR 各 provider（保持原有能力）
# ============================================================
def _online_ocr(image_path, cfg):
    """在线 OCR（预留的 API 配置位）。"""
    api_url = _cfg(cfg, "OCR_API_URL", "") or ""
    api_key = _cfg(cfg, "OCR_API_KEY", "") or ""

    if not api_url or not api_key:
        raise OCRUnavailableError(
            "在线 OCR 未配置。请在 config.py 中设置 OCR_API_URL 与 OCR_API_KEY，"
            "或将 OCR_ENGINE 改为 'local' 使用本地识别。"
        )

    try:
        import requests
    except ImportError:
        raise OCRUnavailableError("缺少依赖 requests，请执行 `pip install requests` 后重试。")

    try:
        with open(image_path, "rb") as f:
            resp = requests.post(
                api_url,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"image": f},
                timeout=30,
            )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        raise OCRUnavailableError(f"在线 OCR 请求失败：{exc}")

    if isinstance(data, dict):
        for key in ("text", "result", "data", "words_result"):
            if key in data and data[key]:
                if isinstance(data[key], str):
                    return data[key].strip()
                if isinstance(data[key], dict) and "text" in data[key]:
                    return data[key]["text"].strip()
        return str(data).strip()
    return str(data).strip()


def _ocrspace_ocr(image_path, cfg):
    """OCR.space 免费在线识别。"""
    api_key = _cfg(cfg, "OCRSPACE_API_KEY", "") or ""
    if not api_key:
        raise OCRUnavailableError(
            "OCR.space 未配置。请在 config.py 中设置 OCRSPACE_API_KEY"
            "（到 https://ocr.space 免费注册获取），或改用 'local'。"
        )

    try:
        import requests
    except ImportError:
        raise OCRUnavailableError("缺少依赖 requests，请执行 `pip install requests` 后重试。")

    try:
        with open(image_path, "rb") as f:
            resp = requests.post(
                "https://api.ocr.space/parse/image",
                data={"apikey": api_key, "language": "chs", "OCREngine": "2"},
                files={"file": f},
                timeout=30,
            )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise OCRUnavailableError(f"OCR.space 请求失败：{exc}")
    except ValueError:
        raise OCRUnavailableError("OCR.space 返回了非 JSON 数据。")

    if not data.get("IsErroredOnProcessing"):
        parsed = data.get("ParsedResults") or []
        if parsed and parsed[0].get("ParsedText", "").strip():
            return parsed[0]["ParsedText"].strip()

    error_msg = data.get("ErrorMessage") or "未知错误"
    parsed = data.get("ParsedResults") or []
    if parsed and parsed[0].get("ErrorMessage"):
        error_msg = parsed[0]["ErrorMessage"]
    raise OCRUnavailableError(f"OCR.space 识别失败：{error_msg}")


def _baidu_ocr(image_path, cfg):
    """百度智能云 OCR 免费在线识别。"""
    api_key = _cfg(cfg, "BAIDU_OCR_API_KEY", "") or ""
    secret_key = _cfg(cfg, "BAIDU_OCR_SECRET_KEY", "") or ""
    if not api_key or not secret_key:
        raise OCRUnavailableError(
            "百度 OCR 未配置。请在 config.py 中设置 BAIDU_OCR_API_KEY 与"
            " BAIDU_OCR_SECRET_KEY（到 https://cloud.baidu.com/product/ocr 免费申请），"
            "或改用 'local'。"
        )

    try:
        import base64

        import requests
    except ImportError:
        raise OCRUnavailableError("缺少依赖 requests，请执行 `pip install requests` 后重试。")

    try:
        token_resp = requests.post(
            "https://aip.baidubce.com/oauth/2.0/token",
            params={
                "grant_type": "client_credentials",
                "client_id": api_key,
                "client_secret": secret_key,
            },
            timeout=15,
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get("access_token", "")
    except requests.RequestException as exc:
        raise OCRUnavailableError(f"获取百度 access_token 失败：{exc}")
    except ValueError:
        raise OCRUnavailableError("百度接口返回了非 JSON 数据。")
    if not access_token:
        raise OCRUnavailableError("获取百度 access_token 失败，请检查 API Key 与 Secret Key。")

    try:
        with open(image_path, "rb") as f:
            image_base64 = base64.b64encode(f.read()).decode("utf-8")
        resp = requests.post(
            "https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic",
            params={"access_token": access_token},
            data={"image": image_base64},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise OCRUnavailableError(f"百度 OCR 请求失败：{exc}")
    except ValueError:
        raise OCRUnavailableError("百度 OCR 返回了非 JSON 数据。")

    if data.get("error_code"):
        raise OCRUnavailableError(
            f"百度 OCR 错误（{data.get('error_code')}）：{data.get('error_msg', '未知错误')}"
        )

    words = [w.get("words", "") for w in data.get("words_result", [])]
    return "\n".join(words).strip()


def is_image_file(filename):
    """判断文件名扩展名是否为支持的图片格式。"""
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    return ext in SUPPORTED_IMAGE_EXTENSIONS
