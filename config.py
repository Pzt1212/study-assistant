# -*- coding: utf-8 -*-
"""应用配置中心。

所有可调参数集中放在这里，方便二次开发与部署时通过环境变量覆盖。
"""
import os

# 项目根目录（config.py 所在目录）
BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _load_local_secrets():
    """读取 data/r2_secrets.env（被 .gitignore 忽略，用于存放 R2 密钥）。

    文件格式（每行一个，支持 # 注释与引号）：
        R2_ACCOUNT_ID=...
        R2_ACCESS_KEY_ID=...
        R2_SECRET_ACCESS_KEY=...
    优先级：环境变量 > 本文件 > 内置默认值。
    """
    path = os.path.join(BASE_DIR, "data", "r2_secrets.env")
    secrets = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                secrets[key.strip()] = value.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return secrets


_LOCAL_SECRETS = _load_local_secrets()


class Config:
    """应用默认配置。

    说明：
    - 环境变量优先级最高，其次才是这里的默认值，便于生产部署。
    - 默认值为开发友好配置，生产环境请务必修改 SECRET_KEY。
    """

    # ----- Flask 核心 -----
    # 运行环境：development / production。production 下未显式设置 SECRET_KEY 会拒绝启动。
    APP_ENV = os.environ.get("APP_ENV", "development")
    # 会话签名密钥（开发用默认值；生产必须设置环境变量 SECRET_KEY）
    SECRET_KEY = os.environ.get("SECRET_KEY", "study-assistant-dev-secret-change-me")
    # 会话 Cookie：仅允许同站发送（防跨站请求伪造利用 cookie），并禁止 JS 读取
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_HTTPONLY = True
    # HTTPS 部署（设置了 https 的 PUBLIC_BASE_URL 或显式环境变量）时启用 Secure
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1" or \
        os.environ.get("PUBLIC_BASE_URL", "").startswith("https://")

    # ----- SQLite 数据库 -----
    # 数据库文件路径（默认放在 data/ 目录下，该目录已被 .gitignore 忽略）
    DATABASE = os.environ.get(
        "DATABASE", os.path.join(BASE_DIR, "data", "study_assistant.db")
    )

    # ----- 上传文件 -----
    # 用户上传文件保存目录（默认 uploads/，已被 .gitignore 忽略）
    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER", os.path.join(BASE_DIR, "uploads")
    )
    # 上传文件大小上限：16MB
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    # 允许上传的文件扩展名（txt/md 直接读文本；图片走 OCR）
    ALLOWED_UPLOAD_EXTENSIONS = {"txt", "md", "markdown", "png", "jpg", "jpeg", "gif", "bmp", "webp"}

    # ----- OCR 文字识别 -----
    # OCR 引擎选择："local" 使用本地 pytesseract；"online" 使用在线 API（需自行配置）
    OCR_ENGINE = os.environ.get("OCR_ENGINE", "local")
    # 内置（打包随项目分发）的 Tesseract 可执行文件路径（见模块七 / tools/setup_tesseract.py）。
    # 把 tesseract.exe 及其 tessdata 放入 bin/tesseract/ 即可开箱即用，无需系统安装。
    BUNDLED_TESSERACT = os.path.join(BASE_DIR, "bin", "tesseract", "tesseract.exe")
    # 本地 Tesseract 可执行文件路径。解析优先级：
    #   1) 显式设置 TESSERACT_CMD（环境变量）；
    #   2) 自动发现项目内置版本 bin/tesseract/tesseract.exe；
    #   3) 系统 PATH 中的 tesseract。
    TESSERACT_CMD = os.environ.get(
        "TESSERACT_CMD",
        BUNDLED_TESSERACT if os.path.exists(BUNDLED_TESSERACT) else "",
    )
    # 本地 OCR 识别的语言包（"chi_sim" 为简体中文，需在 Tesseract 中额外安装）
    OCR_LANG = os.environ.get("OCR_LANG", "chi_sim+eng")
    # ---- 在线 OCR API 配置位（预留，OCR_ENGINE="online" 时启用）----
    OCR_API_URL = os.environ.get("OCR_API_URL", "")      # 例如：https://your-ocr-provider.example/api
    OCR_API_KEY = os.environ.get("OCR_API_KEY", "")      # 在线 OCR 服务的 API 密钥

    # ----- 免费在线 OCR 引擎（通过 OCR_PROVIDER 切换，默认 local）-----
    # 可选值：local（本地 pytesseract，默认）/ ocrspace（OCR.space）/ baidu（百度 OCR）
    # 注意：OCR_PROVIDER 优先于上方的 OCR_ENGINE；若未设置 OCR_PROVIDER，
    #        则回退使用 OCR_ENGINE 的值以兼容旧配置。
    OCR_PROVIDER = os.environ.get("OCR_PROVIDER", "local")
    # OCR.space 免费 API Key（https://ocr.space 注册即可获得，语言指定 chs 中文）
    OCRSPACE_API_KEY = os.environ.get("OCRSPACE_API_KEY", "")
    # 百度智能云 OCR：API Key 与 Secret Key（用于换取 access_token，通用文字识别 general_basic）
    BAIDU_OCR_API_KEY = os.environ.get("BAIDU_OCR_API_KEY", "")
    BAIDU_OCR_SECRET_KEY = os.environ.get("BAIDU_OCR_SECRET_KEY", "")

    # ----- 在线题库（由使用者自行接入 API；项目不内置题目与令牌）-----
    # 是否启用「在线题库」页面（置 0 关闭）。早期变量 OPENTDB_ENABLED 仍兼容识别。
    WKAPI_ENABLED = os.environ.get(
        "WKAPI_ENABLED", os.environ.get("OPENTDB_ENABLED", "1")
    ) == "1"
    # 你的题库接口地址与访问令牌。留空表示由用户在页面上临时填写。
    # 接口约定：GET <地址>?q=<题目>&token=<令牌>，响应 JSON 含 answer 字段。
    QUESTION_BANK_API_URL = os.environ.get("QUESTION_BANK_API_URL", "").strip()
    QUESTION_BANK_TOKEN = os.environ.get("QUESTION_BANK_TOKEN", "").strip()

    # ----- 对外发布 / 内网穿透预留（后续部署时按需覆盖环境变量即可）-----
    # 服务监听地址与端口：
    # - 本地使用：保持 127.0.0.1:5000；
    # - 内网穿透（ngrok/cpolar/frp 等）：隧道指向本机时地址可保持 127.0.0.1，
    #   隧道服务方负责对外转发；
    # - 若需直接对外监听网卡，改为 APP_HOST=0.0.0.0（请自行配置防火墙/反代）。
    APP_HOST = os.environ.get("APP_HOST", "127.0.0.1")
    APP_PORT = int(os.environ.get("APP_PORT", "5000"))
    # 对外访问地址（最终用户访问的完整地址，形如 https://study.example.com）。
    # 留空表示暂未对外发布；后续做公告/分享链接等功能时据此生成绝对地址。
    PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    # 是否位于反向代理 / 内网穿透之后：置 1 时信任 X-Forwarded-* 头，
    # 保证 https 协议、真实客户端 IP 能正确传给 Flask（务必要由受信反代设置这些头）。
    TRUST_PROXY_HEADERS = os.environ.get("TRUST_PROXY_HEADERS", "0") == "1"

    # ----- 背景音乐（在线曲目源 + 脑波音频，见 blueprints/music.py）-----
    # MUSIC_PROVIDER = "builtin"：使用内置曲目源目录（无需任何 API Key）。
    # 在线曲目默认来自公共演示音频站 SoundHelix（仅供功能演示/学习，可替换）。
    # 如需接入自己的在线音频 API，可用环境变量 MUSIC_STREAM_URLS 覆盖，
    # 值为 JSON 数组：[{"name": "曲名", "url": "https://.../a.mp3", "artist": "来源"}]
    MUSIC_PROVIDER = os.environ.get("MUSIC_PROVIDER", "builtin")
    MUSIC_STREAM_URLS = os.environ.get("MUSIC_STREAM_URLS", "")

    # ==================================================================
    # 视频媒体库：绕过 Tunnel 的直连分块传输（见 blueprints/media.py）
    # ==================================================================
    # 背景：本机无公网 IP，网页/API 走 Cloudflare Tunnel。若让视频字节也走
    # Tunnel，国内访问会绕路海外导致极慢。无公网 IP 时的"直连"正确落地方式：
    #   - 浏览器把文件切成小块，直接 PUT 到 Cloudflare R2 的预签名 URL，
    #     字节流不经过本站/Tunnel（R2 在全球边缘就近收流，国内明显快于穿隧道）；
    #   - 本站（走 Tunnel）只处理轻量请求：登录、建会话、按需签发 URL、
    #     记录元数据、异步校验与备份。
    # 若日后拿到公网 IP / 国内 frp 直连端口，可把 MEDIA_UPLOAD_CHANNEL 切为
    # "proxy"：浏览器用 resumable.js 分块 POST 到本站直连地址，本站落盘后
    # 异步转存 R2（即原始"先传本地再转云"的方案，后端已一并实现）。
    # ----- 上传/播放通道 -----
    # 上传通道：r2（默认，浏览器直传 R2 预签名分块）/ proxy（本站中转+异步转 R2）
    MEDIA_UPLOAD_CHANNEL = os.environ.get("MEDIA_UPLOAD_CHANNEL", "r2").strip().lower()
    # 播放源：r2（默认，直连 R2 预签名 URL，防盗链+快）/ self（经本站 Range 流，
    # 仅 proxy 通道本地文件存在时可用，兜底用）
    MEDIA_PLAYBACK_SOURCE = os.environ.get("MEDIA_PLAYBACK_SOURCE", "r2").strip().lower()
    # proxy 通道的本地媒体根目录（分块暂存 + 组装后的原文件）
    MEDIA_ITEM_ROOT = os.environ.get(
        "MEDIA_ITEM_ROOT", os.path.join(BASE_DIR, "data", "media_store")
    )
    # 允许上传的扩展名（白名单；浏览器可直接播放 mp4/webm/mov/音频，
    # mkv/avi/flv 等仅归档备份，播放需转码或本地播放器）
    MEDIA_ALLOWED_EXTENSIONS = {
        "mp4", "webm", "mov", "m4v", "m4a", "mp3", "ogg", "oga", "wav",
        "aac", "flac", "opus", "mkv", "avi", "flv", "ts",
    }
    # 单文件大小上限（默认 4GB）
    MEDIA_MAX_SIZE = int(os.environ.get("MEDIA_MAX_SIZE", str(4 * 1024 ** 3)))
    # 每个分块的目标大小（16MiB；R2 分块下限为 5MiB，勿低于 5MiB）
    MEDIA_PART_SIZE = int(os.environ.get("MEDIA_PART_SIZE", str(16 * 1024 * 1024)))
    # 单用户总容量配额（字节），0 表示不限
    MEDIA_PER_USER_QUOTA_BYTES = int(
        os.environ.get("MEDIA_PER_USER_QUOTA_BYTES", "0")
    )
    # 预签名播放链接有效期（秒）。播放到一半过期由前端自动续签并从当前位置续播。
    MEDIA_URL_TTL = int(os.environ.get("MEDIA_URL_TTL", "3600"))
    # 上传完成后是否异步做整文件 SHA-256 审计（流式从 R2 拉回比对，防分块丢失/篡改）
    MEDIA_VERIFY_ON_COMPLETE = os.environ.get("MEDIA_VERIFY_ON_COMPLETE", "1") == "1"
    # 超过该字节数的大文件跳过整文件审计（拉回太耗时），只做尺寸/分块数校验
    MEDIA_AUDIT_MAX_BYTES = int(os.environ.get("MEDIA_AUDIT_MAX_BYTES", str(2 * 1024 ** 3)))
    # proxy 通道分块落盘是否用 Fernet 加密（密钥 MEDIA_FERNET_KEY，留空则自动
    # 生成并持久化到 data/media_fernet.key；生产建议显式设置环境变量）
    MEDIA_SPOOL_ENCRYPT = os.environ.get("MEDIA_SPOOL_ENCRYPT", "1") == "1"
    MEDIA_FERNET_KEY = os.environ.get("MEDIA_FERNET_KEY", "").strip()
    # proxy 通道转存 R2 成功后是否保留本地原文件（1=保留，构成"本地+云端"
    # 双重地址，可随时走本站兜底源；0=删本地、只留云端）
    MEDIA_KEEP_LOCAL = os.environ.get("MEDIA_KEEP_LOCAL", "1") == "1"

    # ----- Cloudflare R2（S3 兼容）-----
    # 在 Cloudflare 控制台 → R2 → 管理 API 令牌 创建，权限至少：
    #   “对象读与写”，范围限定到下面两个桶；端点与账号 ID 见 R2 概览页。
    # 三个凭据可放环境变量，也可写入 data/r2_secrets.env（自动读取，见文件头说明）。
    R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID") or _LOCAL_SECRETS.get("R2_ACCOUNT_ID", "")
    R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID") or _LOCAL_SECRETS.get("R2_ACCESS_KEY_ID", "")
    R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY") or _LOCAL_SECRETS.get("R2_SECRET_ACCESS_KEY", "")
    R2_BUCKET = os.environ.get("R2_BUCKET", "study-media")        # 主桶（媒体本体）
    R2_BACKUP_BUCKET = os.environ.get("R2_BACKUP_BUCKET", "")      # 备份桶（同账号，留空=仅校验不另存）
    # 一般无需设置；留空时自动拼 https://<ACCOUNT_ID>.r2.cloudflarestorage.com
    R2_ENDPOINT_URL = os.environ.get("R2_ENDPOINT_URL", "").strip()

    # ----- 异步任务（校验 / 备份 / 转存）-----
    # engine：thread（默认，内置线程队列，Windows 无 Redis 开箱即用）/
    #         celery（Linux 生产环境标准 Celery+Redis，见 services/tasks_celery.py）
    MEDIA_ASYNC_ENGINE = os.environ.get("MEDIA_ASYNC_ENGINE", "thread").strip().lower()
    MEDIA_ASYNC_WORKERS = int(os.environ.get("MEDIA_ASYNC_WORKERS", "2"))
