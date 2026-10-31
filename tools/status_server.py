# -*- coding: utf-8 -*-
"""查看后台服务状态（配合 status_server.bat 使用）。

读取 logs/server.pid，判断进程是否存活，并请求健康检查接口确认可用。
"""
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


def main():
    if not os.path.exists(PID_FILE):
        print("状态：未在运行（没有 PID 文件）。")
        print("启动方式：双击 start_server.bat，或执行 python app.py。")
        return 0

    try:
        with open(PID_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        pid = int(data.get("pid", -1))
        url = data.get("url", "http://127.0.0.1:5000")
    except Exception:
        print("状态：PID 文件损坏（进程可能仍在运行，请手动检查）。")
        return 1

    if not _process_alive(pid):
        print(f"状态：进程 {pid} 已不在运行（PID 文件残留）。")
        return 1

    # 请求健康检查，确认真的能对外提供服务
    try:
        with urllib.request.urlopen(url + "/api/health", timeout=5) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        print(f"状态：运行中（PID={pid}）")
        print(f"地址：{url}")
        print(f"健康检查：HTTP {resp.status} {body[:120]}")
        return 0
    except Exception as e:
        print(f"状态：进程 {pid} 存在但健康检查失败：{e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
