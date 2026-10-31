# -*- coding: utf-8 -*-
"""顺序 BBDown 下载 _queue.json；每项后计量总大小，>=20GB 熔断。
   若 BBDown 下载成功但混流失败（留下 .P1.mp4/.m4a 分片），自动用绝对路径 ffmpeg 混流兜底并清理分片。"""
import json
import os
import re
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIDEO = os.path.join(ROOT, "video")
BBDOWN = os.path.join(VIDEO, "bbdown", "BBDown.exe")
FFMPEG = os.path.join(VIDEO, "bin", "ffmpeg-master-latest-win64-gpl", "bin", "ffmpeg.exe")
DL_ROOT = os.path.join(VIDEO, "downloads")
LOG_DIR = os.path.join(VIDEO, "_dllogs")
STATUS = os.path.join(VIDEO, "_dl_status.json")
QUEUE = os.path.join(VIDEO, "_queue.json")
LOCAL_TMP = os.path.join(VIDEO, "_tmp")

CAP_BYTES = 20 * 1024 ** 3  # 20GB
PART_RE = re.compile(r"\.P\d+\.\d+\.(mp4|m4a)$")
ILLEGAL = re.compile(r'[\\/:*?"<>|\r\n\t]')
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(LOCAL_TMP, exist_ok=True)


def total_bytes():
    s = 0
    for dirpath, _dirs, files in os.walk(DL_ROOT):
        for f in files:
            try:
                s += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return s


def safe_title(title, maxlen=120):
    t = ILLEGAL.sub("_", title).strip().strip(". ")
    if len(t) > maxlen:
        t = t[:maxlen].rstrip()
    return t or "video"


def run_bbdown(item, workdir, logpath):
    cmd = [
        BBDOWN,
        "--ffmpeg-path", FFMPEG,
        "-e", "avc,hevc,av1",
        "--work-dir", workdir,
        "https://www.bilibili.com/video/" + item["bvid"],
    ]
    env = dict(os.environ)
    env["TEMP"] = LOCAL_TMP
    env["TMP"] = LOCAL_TMP
    with open(logpath, "w", encoding="utf-8", errors="replace") as lf:
        return subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT,
                              stdin=subprocess.DEVNULL, env=env).returncode


def list_media(root):
    """返回 {relpath: abs} 递归下全部 mp4/m4a/flv。"""
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.lower().endswith((".mp4", ".m4a", ".flv")):
                p = os.path.join(dirpath, f)
                out[os.path.relpath(p, root)] = p
    return out


def mux_pair(mp4, m4a, out_path):
    cmd = [FFMPEG, "-y", "-i", mp4, "-i", m4a, "-c", "copy", "-movflags", "+faststart", out_path]
    with open(os.path.join(VIDEO, "_mux_fallback.log"), "w", encoding="utf-8", errors="replace") as lf:
        return subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT).returncode


def finish_item(item, workdir):
    """尝试从 BBDown 产物中确定最终文件；必要时兜底混流。返回 (ok, final_abspath or None)。"""
    before = list_media(workdir)
    rc = run_bbdown(item, workdir, os.path.join(LOG_DIR, "%s.log" % item["bvid"]))
    after = list_media(workdir)
    newp = {r: p for r, p in after.items() if r not in before}
    # 1) 直接找新的“最终 mp4”（非分片名，且够大——含音频）
    finals = [p for r, p in newp.items()
              if p.lower().endswith(".mp4") and not PART_RE.search(p)
              and os.path.getsize(p) > 10 * 1048576]
    if finals:
        finals.sort(key=lambda p: -os.path.getsize(p))
        return True, finals[0], rc
    # 2) 兜底：找新出现的分片对（m4a 是可靠信号：≥40min 音频必然 >20MB）
    for r, m4a in newp.items():
        if not m4a.lower().endswith(".m4a") or os.path.getsize(m4a) < 20 * 1048576:
            continue
        stem = r.rsplit(".", 1)[0]
        mp4 = after.get(stem + ".mp4")
        if mp4 and os.path.getsize(mp4) > 1024 * 1024:
            out = os.path.join(workdir, safe_title(item["title"]) + ".mp4")
            if mux_pair(mp4, m4a, out) == 0 and os.path.getsize(out) > 10 * 1048576:
                for x in (mp4, m4a):
                    try:
                        os.remove(x)
                    except OSError:
                        pass
                return True, out, rc
    return False, None, rc


def main():
    queue = json.load(open(QUEUE, encoding="utf-8"))
    report = {"cap_bytes": CAP_BYTES, "items": []}
    for i, item in enumerate(queue):
        before_tot = total_bytes()
        if before_tot >= CAP_BYTES:
            print("CAP reached %.1fGB before item %d, stop." % (before_tot / 1024 ** 3, i + 1), flush=True)
            break
        workdir = os.path.join(DL_ROOT, item["dir"])
        os.makedirs(workdir, exist_ok=True)
        ok = False
        final = None
        last_rc = None
        for attempt in range(3):
            print("[%d/%d] %s %.1fh %s | attempt %d/3"
                  % (i + 1, len(queue), item["bvid"], item["duration"] / 3600.0,
                     item["dir"], attempt + 1), flush=True)
            ok, final, last_rc = finish_item(item, workdir)
            print("  rc=%d ok=%s total=%.2fGB" % (last_rc, ok, total_bytes() / 1024 ** 3), flush=True)
            if ok:
                break
            time.sleep(8)
        report["items"].append({
            "idx": i + 1, "bvid": item["bvid"], "title": item["title"],
            "duration": item["duration"], "dir": item["dir"],
            "ok": ok, "rc": last_rc,
            "final": os.path.relpath(final, DL_ROOT) if final else None,
            "final_mb": round(os.path.getsize(final) / 1048576.0, 1) if final else None,
            "total_gb": round(total_bytes() / 1024 ** 3, 3),
        })
        with open(STATUS, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
    print("DONE items=%d final_total=%.2fGB" % (len(report["items"]), total_bytes() / 1024 ** 3), flush=True)


if __name__ == "__main__":
    main()
