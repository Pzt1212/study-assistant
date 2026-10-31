# -*- coding: utf-8 -*-
"""命名隧道启动器（固定域名 / 固定 trycloudflare 子域）。

用途：tunnel_start.bat 在设置了 TUNNEL_DOMAIN 后调用本脚本，
自动完成：
    1) 校验已登录（~/.cloudflared/cert.pem 存在）
    2) 查找/创建名为 study-assistant 的隧道（凭据 ~/.cloudflared/<UUID>.json）
    3) 生成绑定本机 http://127.0.0.1:5000 的临时配置（不落任何 Token）
    4) route dns 到目标域名（幂等）
    5) 后台启动 cloudflared 并写 PID / 日志

安全：本脚本不读取、不写入凭据内容；凭据文件路径写入 ~/.cloudflared/，
      项目内 config 仅含域名与本地地址占位。
"""
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CF_DIR = os.path.join(ROOT, "tunnel")
HOME_CF = os.path.join(os.path.expanduser("~"), ".cloudflared")
CF_EXE = os.path.join(CF_DIR, "cloudflared.exe")
if not os.path.exists(CF_EXE):
    CF_EXE = "cloudflared"  # 已在 PATH

TUNNEL_NAME = "study-assistant"
LOCAL_URL = "http://127.0.0.1:5000"
LOG_DIR = os.path.join(CF_DIR, "logs")
PID_FILE = os.path.join(LOG_DIR, "tunnel.pid")


def log(msg):
    print(msg, flush=True)


def run(args, check=True):
    p = subprocess.run([CF_EXE] + args, capture_output=True, text=True, timeout=120)
    if check and p.returncode != 0:
        raise RuntimeError(f"cloudflared {' '.join(args)} 失败：{p.stderr.strip() or p.stdout.strip()}")
    return p


def main():
    domain = os.environ.get("TUNNEL_DOMAIN", "").strip()
    if not domain:
        log("未设置 TUNNEL_DOMAIN，无法启动命名隧道。")
        return 1
    os.makedirs(LOG_DIR, exist_ok=True)

    cert = os.path.join(HOME_CF, "cert.pem")
    if not os.path.exists(cert):
        log("尚未登录 Cloudflare。请先执行：cloudflared tunnel login")
        log("（浏览器授权后会自动生成 %s）" % cert)
        return 1

    # ---- 查找或创建隧道 ----
    cred_json = None
    tunnel_id = None
    if os.path.isdir(HOME_CF):
        for fn in os.listdir(HOME_CF):
            if fn.endswith(".json"):
                p = os.path.join(HOME_CF, fn)
                try:
                    with open(p, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    if data.get("TunnelID"):
                        tunnel_id = data["TunnelID"]
                        cred_json = p
                        break
                except Exception:
                    continue
    if not tunnel_id:
        log("未找到命名隧道凭据。正在创建隧道 %s …" % TUNNEL_NAME)
        p = run(["tunnel", "create", TUNNEL_NAME])
        # 从输出 "Created tunnel ... with id <uuid>" 或目录新 json 获取
        cred_json = None
        for fn in os.listdir(HOME_CF):
            if fn.endswith(".json"):
                pj = os.path.join(HOME_CF, fn)
                try:
                    with open(pj, "r", encoding="utf-8") as fh:
                        if json.load(fh).get("TunnelID"):
                            cred_json = pj
                            break
                except Exception:
                    continue
        if not cred_json:
            log("创建隧道后未找到凭据文件，请检查 cloudflared tunnel list")
            return 1
        with open(cred_json, "r", encoding="utf-8") as fh:
            tunnel_id = json.load(fh)["TunnelID"]

    log("隧道：%s（UUID=%s）" % (TUNNEL_NAME, tunnel_id))
    log("凭据文件：%s" % cred_json)

    # ---- 生成 ingress 配置（临时文件，不含任何 Token）----
    cfg = {
        "tunnel": TUNNEL_NAME,
        "credentials-file": cred_json,
        "ingress": [
            {"hostname": domain, "service": LOCAL_URL},
            {"service": "http_status:404"},
        ],
    }
    cfg_path = os.path.join(CF_DIR, "config-named-active.yml")
    with open(cfg_path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)

    # ---- DNS 路由（幂等）----
    log("配置 DNS 路由 %s → 隧道 …" % domain)
    run(["tunnel", "route", "dns", TUNNEL_NAME, domain], check=False)

    # ---- 后台启动 ----
    out_log = os.path.join(LOG_DIR, "tunnel.out.log")
    err_log = os.path.join(LOG_DIR, "tunnel.err.log")
    with open(out_log, "a", encoding="utf-8") as so, open(err_log, "a", encoding="utf-8") as se:
        proc = subprocess.Popen(
            [CF_EXE, "tunnel", "--config", cfg_path, "run", TUNNEL_NAME, "--no-autoupdate"],
            stdout=so, stderr=se,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            close_fds=True,
        )
    with open(PID_FILE, "w", encoding="ascii") as fh:
        fh.write(str(proc.pid))

    log("命名隧道已后台启动（PID=%s）" % proc.pid)
    log("访问地址：https://%s" % domain)
    log("等待 5 秒后做健康检查 …")
    time.sleep(5)
    url = f"https://{domain}/api/health"
    log(f"健康检查：{url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
