# -*- coding: utf-8 -*-
"""学习助手 - 服务统一管理入口（start / stop / status / restart / log）

用法（项目根目录）：
    python manage.py start       # 后台启动（pythonw，无窗口），日志 logs/app.log
    python manage.py stop        # 停止服务（PID 优先，缺失时按端口查杀）
    python manage.py status      # 查看运行状态 + 健康检查
    python manage.py restart     # 重启服务
    python manage.py log [行数]  # 查看最近日志（默认 40 行）

脚本族关系：
    start.bat / start.vbs / start_silent.vbs  →  调起 tools/run_server.py（后台）
    stop.bat / manage.py stop                  →  tools/stop_server.py
    日志文件：logs/app.log（APP_LOG_FILE 可覆盖）
    PID 文件：logs/app.pid（APP_PID_FILE 可覆盖）
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(ROOT, "logs")


def _pyw_exe():
    """定位 pythonw（无控制台窗口的解释器）。"""
    explicit = os.environ.get("PYTHONW", "").strip()
    if explicit:
        return explicit
    # 与 python.exe 同目录的 pythonw.exe（uv 托管 Python 布局即如此）
    if sys.executable and os.path.basename(sys.executable).lower().startswith("python"):
        sibling = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if os.path.exists(sibling):
            return sibling
    fallback = os.path.join(
        os.path.expanduser("~"), "AppData", "Local", "Python", "bin", "pythonw.exe")
    if os.path.exists(fallback):
        return fallback
    return "pythonw"


def _app_log_file():
    raw = os.environ.get("APP_LOG_FILE", "").strip()
    if raw:
        return raw if os.path.isabs(raw) else os.path.join(ROOT, raw)
    return os.path.join(LOG_DIR, "app.log")


def _app_pid_file():
    raw = os.environ.get("APP_PID_FILE", "").strip()
    if raw:
        return raw if os.path.isabs(raw) else os.path.join(ROOT, raw)
    return os.path.join(LOG_DIR, "app.pid")


def _host_port():
    host = os.environ.get("APP_HOST", "127.0.0.1").strip() or "127.0.0.1"
    try:
        port = int(os.environ.get("APP_PORT", "5000"))
    except ValueError:
        port = 5000
    return host, port


def _health_url():
    host, port = _host_port()
    return f"http://{host}:{port}/api/health"


def _process_alive(pid):
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_pid_file(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def cmd_start():
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = _app_log_file()
    pid_file = _app_pid_file()

    # 已通过 PID 文件注册并存活 → 提示，不重复启动
    data = _read_pid_file(pid_file)
    if data and _process_alive(int(data.get("pid", -1))):
        print(f"服务已在运行（PID={data.get('pid')}）→ {data.get('url')}")
        return 0

    child_env = os.environ.copy()
    child_env["APP_LOG_FILE"] = log_file
    child_env["APP_PID_FILE"] = pid_file
    child_env["FLASK_DEBUG"] = "0"

    script = os.path.join(ROOT, "tools", "run_server.py")
    kwargs = {}
    if os.name == "nt":
        # 独立进程组 + 脱离控制台：保证 pythonw 服务不被启动它的
        # 命令行窗口（cmd / .bat / 其它 shell）关闭时连带终止
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
    proc = subprocess.Popen(
        [_pyw_exe(), script],
        cwd=ROOT,
        env=child_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        **kwargs,
    )
    url = _health_url()
    print(f"正在后台启动服务（pythonw PID={proc.pid}）…")
    print(f"日志文件：{log_file}")

    # 等待健康检查通过（最多 ~15 秒）
    for _ in range(30):
        time.sleep(0.5)
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    print(f"启动成功，浏览器访问：{url.replace('/api/health', '')}")
                    print(f"查看状态：python manage.py status   停止：python manage.py stop")
                    return 0
        except Exception:
            continue
    print("健康检查超时。可执行 `python manage.py log` 查看日志排查。")
    return 1


def cmd_stop():
    env = os.environ.copy()
    env["APP_PID_FILE"] = _app_pid_file()
    return subprocess.call(
        [sys.executable, os.path.join(ROOT, "tools", "stop_server.py")],
        cwd=ROOT, env=env,
    )


def cmd_status():
    data = _read_pid_file(_app_pid_file())
    if not data:
        print("状态：未在运行（没有 PID 文件）。")
        print("启动方式：python manage.py start / start.bat / start.vbs")
        return 1
    pid = int(data.get("pid", -1))
    url = data.get("url", _health_url())
    if not _process_alive(pid):
        print(f"状态：进程 {pid} 已不在运行（PID 文件残留，可执行 manage.py stop 清理）。")
        return 1
    try:
        with urllib.request.urlopen(url + "/api/health", timeout=5) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        print(f"状态：运行中（PID={pid}）")
        print(f"地址：{url}")
        print(f"健康检查：HTTP {resp.status} {body[:120]}")
        return 0
    except Exception as exc:
        print(f"状态：进程 {pid} 存在但健康检查失败：{exc}")
        return 1


def cmd_log(lines=40):
    log_file = _app_log_file()
    if not os.path.exists(log_file):
        print(f"日志文件不存在：{log_file}")
        return 1
    try:
        lines = int(lines)
    except (TypeError, ValueError):
        lines = 40
    with open(log_file, "r", encoding="utf-8", errors="replace") as fh:
        all_lines = fh.readlines()
    tail = all_lines[-max(1, min(lines, 200)):]
    print(f"--- {log_file} 最近 {len(tail)} 行 ---")
    sys.stdout.write("".join(tail))
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    action = sys.argv[1].lower()
    if action == "start":
        return cmd_start()
    if action == "stop":
        return cmd_stop()
    if action == "status":
        return cmd_status()
    if action == "log":
        return cmd_log(sys.argv[2] if len(sys.argv) > 2 else 40)
    if action == "restart":
        code = cmd_stop()
        print("—" * 40)
        return cmd_start() if code == 0 else code
    print(f"未知命令：{action}\n")
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
