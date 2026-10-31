# -*- coding: utf-8 -*-
"""停止后台服务（配合 stop_server.bat 使用）。

读取 logs/server.pid 中的 PID 并终止对应进程；随后删除 PID 文件。
"""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# PID 文件路径可用环境变量 APP_PID_FILE 覆盖（manage.py / start.bat 使用 logs/app.pid）
def _pid_file():
    raw = (os.environ.get("APP_PID_FILE", "") or "").strip()
    if raw:
        return raw if os.path.isabs(raw) else os.path.join(ROOT, raw)
    return os.path.join(ROOT, "logs", "server.pid")

PID_FILE = _pid_file()


def _process_alive(pid):
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _terminate(pid):
    """终止进程：先温和 SIGTERM，稍等仍存活则强制结束。"""
    if os.name == "nt":
        os.kill(pid, 9)          # Windows 上 os.kill 直接 TerminateProcess
    else:
        try:
            os.kill(pid, 15)
        except OSError:
            pass
        time.sleep(1)
        if _process_alive(pid):
            os.kill(pid, 9)


def _port_default():
    """读取监听端口（环境变量 APP_PORT 或默认 5000）。"""
    try:
        return int(os.environ.get("APP_PORT", "5000"))
    except ValueError:
        return 5000


def _is_python_process(pid):
    """Windows 下判断 PID 对应的进程是否 python / pythonw（避免误杀其它占用进程）。"""
    if os.name != "nt":
        return True
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, timeout=10,
        ).stdout or ""
        return "python" in out.lower()
    except Exception:
        # tasklist 不可用时退而信任端口占用者
        return True


def stop_by_port(port=None):
    """通过端口找到占用 PID 并停止（stop.bat / manage.py 的兜底手段）。"""
    port = port or _port_default()
    try:
        out = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=15
        ).stdout or ""
    except Exception as exc:
        print(f"无法读取端口占用：{exc}")
        return 1

    target = f":{port}"
    pids = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].upper() == "TCP" and "LISTENING" in line.upper():
            # 形如 TCP 127.0.0.1:5000 0.0.0.0:0 LISTENING 12345
            addr = parts[1]
            if addr.endswith(target):
                try:
                    pids.add(int(parts[4]))
                except (IndexError, ValueError):
                    pass

    killed = 0
    for pid in pids:
        if _is_python_process(pid):
            print(f"按端口 {port} 找到进程 PID={pid}，正在停止…")
            _terminate(pid)
            killed += 1
    if not killed and not pids:
        print(f"端口 {port} 没有正在监听的进程。")
        return 0 if not pids else 1
    if not killed and pids:
        print(f"端口 {port} 被非 Python 进程占用（PID={sorted(pids)}），未自动停止。")
        return 1
    # 清理可能残留的 PID 文件
    for f in (PID_FILE, os.path.join(ROOT, "logs", "server.pid"),
              os.path.join(ROOT, "logs", "app.pid")):
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass
    print(f"已停止监听端口 {port} 的服务进程。")
    return 0


def main():
    # 一律按端口清理：可能残留多个监听实例（历史 restart 未杀干净会累积），
    # 只杀 PID 文件里那一个会漏掉其余实例，导致新旧代码实例同时抢 5000 端口。
    return stop_by_port()


if __name__ == "__main__":
    sys.exit(main())
