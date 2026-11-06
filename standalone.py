# -*- coding: utf-8 -*-
"""学习助手 - 单机单人版启动入口（PyInstaller 打包目标）。

与普通 Web 版的区别：
- 数据（SQLite 数据库、上传文件、媒体存储、日志）落在 exe 所在目录旁，
  复制整个文件夹到任何位置都可运行，卸载即删文件夹；
- 首次启动自动创建唯一账号（用户名默认 user，密码随机 6 位并已设为管理员），
  账号信息写入 data/账号信息.txt 备查；可用环境变量
  STANDALONE_USERNAME / STANDALONE_PASSWORD 覆盖；
- 单人免登录：访问任意页面自动以该账号登录，无需输入密码；
- 注册入口在单人版中被禁用（保持单用户）；
- 启动后自动打开系统默认浏览器访问本机地址。

用法（开发态调试）：
    python standalone.py
打包后：
    双击 学习助手.exe
"""
import os
import socket
import sys
import threading
import webbrowser

# ---------------------------------------------------------------------------
# 1. 解析程序所在目录（exe 旁目录 = 用户数据根目录）
#    - PyInstaller onedir 打包后：sys.executable 指向 exe，模块代码在 _internal；
#    - 开发态运行：与项目根一致。
# ---------------------------------------------------------------------------
if getattr(sys, "frozen", False):  # PyInstaller 打包环境
    APP_ROOT = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_ROOT = os.path.dirname(os.path.abspath(__file__))

# 模块导入根（打包后为 _internal，保证 config/blueprints 等可导入）
if getattr(sys, "frozen", False):
    MODULE_ROOT = getattr(sys, "_MEIPASS", os.path.join(APP_ROOT, "_internal"))
else:
    MODULE_ROOT = APP_ROOT
if MODULE_ROOT not in sys.path:
    sys.path.insert(0, MODULE_ROOT)

# ---------------------------------------------------------------------------
# 2. 在导入 config 之前，把所有可写路径重定向到 exe 旁目录
#    （config.py 会读取这些环境变量；BASE_DIR 在打包态指向 _internal，
#     只读资源没问题，但数据库/上传不能放那里）
# ---------------------------------------------------------------------------
DATA_DIR = os.path.join(APP_ROOT, "data")
UPLOAD_DIR = os.path.join(APP_ROOT, "uploads")
LOG_DIR = os.path.join(APP_ROOT, "logs")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

os.environ.setdefault("DATABASE", os.path.join(DATA_DIR, "study_assistant.db"))
os.environ.setdefault("UPLOAD_FOLDER", UPLOAD_DIR)
os.environ.setdefault("MEDIA_ITEM_ROOT", os.path.join(DATA_DIR, "media_store"))
os.environ.setdefault("APP_LOG_FILE", os.path.join(LOG_DIR, "server.log"))
os.environ.setdefault("APP_PID_FILE", os.path.join(LOG_DIR, "server.pid"))
os.environ.setdefault("APP_HOST", "127.0.0.1")
os.environ.setdefault("APP_PORT", "5000")
os.environ["FLASK_DEBUG"] = "0"

# 单人版内置账号（用户名可用环境变量 STANDALONE_USERNAME 覆盖；
# 密码默认在首次启动时随机生成并写入 data/账号信息.txt，
# 也可用环境变量 STANDALONE_PASSWORD 指定）
SU_USERNAME = os.environ.get("STANDALONE_USERNAME", "user")


def _generate_password() -> str:
    """首次启动时生成随机密码（6 位数字，好记够用；自动登录下很少手动输入）。"""
    import secrets

    return str(secrets.randbelow(1000000)).zfill(6)


def _port_in_use(host: str, port: int) -> bool:
    """检测 host:port 是否已被占用。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _find_free_port(host: str, start: int) -> int:
    """从 start 起找一个可用端口（最多尝试 20 个）。"""
    for p in range(start, start + 20):
        if not _port_in_use(host, p):
            return p
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def _open_browser_later(url: str, delay: float = 1.5):
    """延迟打开浏览器，等服务真正监听后再访问。"""
    def _worker():
        # 轮询等待端口就绪（最多 ~15 秒）
        for _ in range(30):
            if _port_in_use("127.0.0.1", _url_port(url)):
                webbrowser.open(url)
                return
            threading.Event().wait(0.5)

    threading.Thread(target=_worker, daemon=True).start()


def _url_port(url: str) -> int:
    try:
        return int(url.rsplit(":", 1)[1])
    except Exception:
        return 5000


def _ensure_single_user(app):
    """首次启动时创建默认账号并写入 data/账号信息.txt。"""
    from models import count_users, create_user, get_user_by_username, set_user_admin
    from blueprints.auth import hash_password

    created_password = None
    with app.app_context():
        _create = count_users() == 0
        if _create:
            # 密码优先级：环境变量 STANDALONE_PASSWORD > 随机生成（记录在账号信息.txt）
            created_password = os.environ.get("STANDALONE_PASSWORD") or _generate_password()
            create_user(SU_USERNAME, f"{SU_USERNAME}@local", hash_password(created_password))
            user = get_user_by_username(SU_USERNAME)
            if user:
                set_user_admin(user.id, True)

    if _create:
        info_path = os.path.join(DATA_DIR, "账号信息.txt")
        with open(info_path, "w", encoding="utf-8") as f:
            f.write(
                "学习助手·单机版 自动创建的账号：\n"
                f"    用户名：{SU_USERNAME}\n"
                f"    密码：{created_password}\n"
                "\n"
                "单人模式下访问页面会自动登录，通常无需手动输入。\n"
                "（重新安装时删除 data 目录即可重置账号；也可用环境变量 "
                "STANDALONE_USERNAME / STANDALONE_PASSWORD 指定账号）\n"
            )
        print(f"[单机版] 已自动创建账号：{SU_USERNAME} / {created_password}（详情见 data/账号信息.txt）")


def _install_single_user_mode(app):
    """注入单人模式行为：自动登录 + 禁用注册。"""
    from flask import request
    from flask_login import current_user, login_user

    _ensure_single_user(app)

    @app.before_request
    def _auto_login_or_block_register():
        # 屏蔽注册入口：单人版保持单用户
        endpoint = request.endpoint or ""
        if endpoint.startswith("auth.register"):
            from flask import jsonify
            msg = "单机单人版已禁用注册功能。"
            if request.path.startswith("/api/"):
                return jsonify({"error": msg}), 403
            return (
                "<h3>403 - 单机单人版</h3>"
                "<p>本版本为单机单人版，已禁用注册功能。</p>"
                "<p><a href='/'>返回首页</a></p>",
                403,
            )
        # 静态资源与已登录用户无需处理
        if endpoint == "static" or current_user.is_authenticated:
            return None
        # 自动登录默认账号
        try:
            from models import get_user_by_username
            user = get_user_by_username(SU_USERNAME)
            if user is not None:
                login_user(user, remember=True)
        except Exception:
            pass
        return None


def main() -> int:
    # ------- 先处理端口：被占用时判断是否为已运行的实例 -------
    host = os.environ["APP_HOST"]
    port = int(os.environ["APP_PORT"])
    already_running = _port_in_use(host, port)

    if already_running:
        # 端口已开：大概率是本程序已在运行（健康检查确认）
        import requests
        try:
            r = requests.get(f"http://{host}:{port}/api/health", timeout=2)
            healthy = r.status_code == 200
        except Exception:
            healthy = False
        if healthy:
            url = f"http://{host}:{port}"
            print(f"[单机版] 检测到学习助手已在运行，直接打开浏览器：{url}")
            _open_browser_later(url, delay=0.2)
            threading.Event().wait(3)  # 给浏览器线程一点时间
            return 0
        # 端口被其他程序占用 → 换一个端口启动
        port = _find_free_port(host, port + 1)
        print(f"[单机版] 端口 {os.environ['APP_PORT']} 被其他程序占用，改用 {port}。")

    # ------- 创建应用（建库 + 注册蓝图） -------
    from app import create_app
    from config import Config
    from db import init_db

    app = create_app(Config)
    init_db(app)  # ensure tables（create_app 内部 initialize_db=True 已建，这里幂等兜底）
    _install_single_user_mode(app)

    url = f"http://{host}:{port}"
    print("=" * 56)
    print("  学习助手 · 单机单人版")
    print(f"  访问地址：{url}  （启动后会自动打开浏览器）")
    print(f"  数据目录：{DATA_DIR}")
    print(f"  账    号：{SU_USERNAME}（自动登录，无需输入密码；详见 data/账号信息.txt）")
    print("  关闭本窗口或按 Ctrl+C 即可退出。")
    print("=" * 56)

    _open_browser_later(url)

    try:
        app.run(host=host, port=port, debug=False, threaded=True, use_reloader=False)
    except KeyboardInterrupt:
        print("\n[单机版] 已退出。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
