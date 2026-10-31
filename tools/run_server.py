# -*- coding: utf-8 -*-
"""后台运行入口（配合 start_server.bat 使用）。

特点：
- 以文件日志方式运行（pythonw 启动时没有控制台，输出全部落到 logs/server.log）；
- 启动前检查 logs/server.pid，避免重复启动；
- 启动后把进程 PID 与访问地址写入 logs/server.pid，供 stop_server 使用；
- 监听地址/端口读自 config（环境变量 APP_HOST / APP_PORT 可覆盖）。

用法：
    python tools/run_server.py          # 前台运行（日志同时输出到控制台与文件）
    start_server.bat                    # 双击：pythonw 后台运行，无黑窗口
"""
import json
import logging
import logging.handlers
import os
import sys
import time

# 保证无论从哪个目录调用都能导入项目模块
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import Config  # noqa: E402
from app import create_app  # noqa: E402

LOG_DIR = os.path.join(ROOT, "logs")
# 日志 / PID 文件路径可用环境变量覆盖（manage.py / start.bat 用 logs/app.log + logs/app.pid）
def _resolve_env_path(name, default):
    raw = (os.environ.get(name, "") or "").strip()
    if not raw:
        return os.path.join(LOG_DIR, default)
    return raw if os.path.isabs(raw) else os.path.join(ROOT, raw)

LOG_FILE = _resolve_env_path("APP_LOG_FILE", "server.log")
PID_FILE = _resolve_env_path("APP_PID_FILE", "server.pid")


def _setup_logging():
    """把应用与 Werkzeug 日志写入 logs/server.log（兼作控制台输出）。"""
    os.makedirs(LOG_DIR, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    # pythonw 下无控制台（sys.stderr 为 None），仅在有终端时附加控制台输出
    if sys.stderr is not None and getattr(sys.stderr, "write", None):
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(formatter)
        root.addHandler(console)

    # Flask/Werkzeug 的请求日志走 root handler（它们会向上传播）
    for name in ("werkzeug", "flask.app"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.INFO)
        lg.propagate = True


def _process_alive(pid):
    """判断 pid 对应的进程是否存活（Windows/Linux 通用）。"""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _write_pid(pid, host, port, url):
    with open(PID_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "pid": pid,
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "host": host,
            "port": port,
            "url": url,
        }, f, ensure_ascii=False, indent=2)


def _remove_pid_if_mine(pid):
    """退出时清理 PID 文件（只清理自己写入的那个）。"""
    try:
        with open(PID_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if int(data.get("pid", -1)) == pid:
            os.remove(PID_FILE)
    except Exception:
        pass


def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    _setup_logging()
    log = logging.getLogger("run_server")

    # 防止重复启动
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r", encoding="utf-8") as f:
                old = int(json.load(f).get("pid", -1))
        except Exception:
            old = -1
        if _process_alive(old):
            log.warning("检测到服务已在运行（PID=%s），如需重启请先执行 stop_server.bat", old)
            return 1
        else:
            os.remove(PID_FILE)

    app = create_app(Config)
    host = app.config["APP_HOST"]
    port = app.config["APP_PORT"]
    url = f"http://{host}:{port}"
    log.info("应用初始化完成，即将监听 %s:%s", host, port)
    log.info("访问地址：%s  健康检查：%s/api/health", url, url)
    _write_pid(os.getpid(), host, port, url)

    try:
        # debug 关闭 + threaded 开启：后台运行不允许自动重载，多人访问互不阻塞
        app.run(host=host, port=port, debug=False, threaded=True,
                use_reloader=False)
    finally:
        _remove_pid_if_mine(os.getpid())
    return 0


if __name__ == "__main__":
    sys.exit(main())
