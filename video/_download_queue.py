# -*- coding: utf-8 -*-
"""按 _queue.json 顺序批量下载（BBDown 480P），按分类子目录，≤20GB 自动停。"""
import json
import os
import subprocess
import sys
import time

# 控制台 UTF-8，避免 GBK 下写中文/符号崩
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIDEO = os.path.join(ROOT, "video")
BBDOWN = os.path.join(VIDEO, "bbdown", "BBDown.exe")
FFMPEG = os.path.join(VIDEO, "bin", "ffmpeg-master-latest-win64-gpl", "bin", "ffmpeg.exe")
DL_ROOT = os.path.join(VIDEO, "downloads")
os.makedirs(DL_ROOT, exist_ok=True)
BUDGET_MB = 20.0 * 1024
LOG = os.path.join(VIDEO, "_download.log")

with open(os.path.join(ROOT, "_queue.json"), "r", encoding="utf-8") as fh:
    queue = json.load(fh)


def log(msg):
    line = time.strftime("%H:%M:%S") + " " + msg
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def dir_size_mb(path):
    total = 0
    for base, _d, files in os.walk(path):
        for f in files:
            fp = os.path.join(base, f)
            if os.path.isfile(fp):
                total += os.path.getsize(fp)
    return total / 1048576


def main():
    used = dir_size_mb(DL_ROOT)
    log(f"start: 已有 {used/1024:.2f} GB, 预算 20GB")
    ok = 0
    for item in queue:
        if used >= BUDGET_MB:
            log("reached 20GB budget, stop.")
            break
        bv = item["bvid"]
        cat = item.get("category", "其它")
        # 分类子目录（去掉敏感字符）
        safe_cat = cat.replace("/", "_").replace("\\", "_")
        outdir = os.path.join(DL_ROOT, safe_cat)
        os.makedirs(outdir, exist_ok=True)

        # 跳过已存在的（以含 bv/BV 或视频文件为准）
        existing = [f for f in os.listdir(outdir) if f.lower().endswith((".mp4", ".flv"))]
        if existing:
            log(f"skip {bv} (exists {len(existing)})")
            continue

        log(f"-> downloading {bv} [{cat}] → {safe_cat}/")
        cmd = [
            BBDOWN, "--ffmpeg-path", FFMPEG,
            "-e", "avc,hevc,av1",
            "--work-dir", outdir,
            "https://www.bilibili.com/video/" + bv,
        ]
        try:
            with open(LOG, "a", encoding="utf-8") as lf:
                p = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, timeout=1800)
            if p.returncode != 0:
                log(f"  ! {bv} BBDown exit {p.returncode}")
                time.sleep(2)
                continue
        except subprocess.TimeoutExpired:
            log(f"  ! {bv} timeout")
            continue
        except Exception as exc:
            log(f"  ! {bv} EXC {exc}")
            continue

        used = dir_size_mb(DL_ROOT)
        ok += 1
        log(f"  [OK] {bv} done. 累计 {used/1024:.2f} GB")
        time.sleep(1.5)

    log(f"finished: {ok} downloaded, 累计 {dir_size_mb(DL_ROOT)/1024:.2f} GB")


if __name__ == "__main__":
    main()
