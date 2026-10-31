# -*- coding: utf-8 -*-
"""Tesseract-OCR 本地打包工具（模块七：OCR 开箱即用）。

目标：把 Tesseract 引擎放入项目目录 bin/tesseract/，使 OCR 无需系统安装即可用。
- Windows：下载 UB-Mannheim 的官方安装包并静默安装到 bin/tesseract/，
           随后自动补充简体中文语言包 chi_sim.traineddata；
- macOS：brew install tesseract tesseract-lang（需联网 + 管理员/brew 权限）；
- Linux：apt-get / yum 安装 tesseract-ocr 与中文语言包。

使用：python tools/setup_tesseract.py
引擎解析顺序（services/ocr_service.py）：显式 TESSERACT_CMD → 内置 bin/tesseract/ → 系统 PATH。
"""
import os
import shutil
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN_DIR = os.path.join(ROOT, "bin", "tesseract")

# UB-Mannheim 官方 Windows 安装包（主链 GitHub Release + 多个国内镜像回退，均可直连）
_SETUP_GH = ("https://github.com/UB-Mannheim/tesseract/releases/download/"
             "v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe")
_SETUP_FALLBACK = ("https://digi.bib.uni-mannheim.de/tesseract/"
                   "tesseract-ocr-w64-setup-5.3.3.20231005.exe")
# 已实测可用的 GitHub 加速镜像（按顺序回退）
_MIRRORS = ["https://ghfast.top/", "https://gh-proxy.com/",
            "https://ghproxy.net/", "https://gh.ddlc.top/"]
TESSERACT_WIN_URLS = [_SETUP_GH] + [m + _SETUP_GH for m in _MIRRORS] + [_SETUP_FALLBACK]
# 简体中文 traineddata（tessdata_fast 仓库；jsdelivr CDN + GitHub 镜像）
_CHI_GH = ("https://github.com/tesseract-ocr/tessdata_fast/raw/main/chi_sim.traineddata")
CHI_SIM_URLS = (["https://cdn.jsdelivr.net/gh/tesseract-ocr/tessdata_fast@main/chi_sim.traineddata"]
                + [m + _CHI_GH for m in _MIRRORS])


def log(msg):
    print(msg)


def _download(url, dest):
    log(f"  下载 {url}")
    log(f"  保存至 {dest}")
    req = urllib.request.Request(url, headers={"User-Agent": "study-assistant-setup"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as fh:
        shutil.copyfileobj(resp, fh)
    log(f"  完成（{os.path.getsize(dest)} 字节）")


def _run(cmd):
    log("  执行: " + " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.stdout.strip():
        log("    " + result.stdout.strip().replace("\n", "\n    "))
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"命令失败，退出码 {result.returncode}")


def setup_windows():
    os.makedirs(BIN_DIR, exist_ok=True)
    installer = os.path.join(BIN_DIR, "_setup_tesseract.exe")
    last_err = None
    for url in TESSERACT_WIN_URLS:
        try:
            _download(url, installer)
            break
        except Exception as exc:
            last_err = exc
            log(f"  通道不可用 {url.split('/')[2]}：{exc}")
            if os.path.exists(installer):
                try:
                    os.remove(installer)
                except OSError:
                    pass
    else:
        log(f"全部通道下载失败：{last_err}")
        return 1
    try:
        log("[1/2] 静默安装 Tesseract 到 bin/tesseract/（Inno Setup 静默参数）…")
        _run([installer, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
              f'/DIR="{BIN_DIR}"'])
    finally:
        if os.path.exists(installer):
            try:
                os.remove(installer)
            except OSError:
                pass

    tessdata = os.path.join(BIN_DIR, "tessdata")
    os.makedirs(tessdata, exist_ok=True)
    chi_sim = os.path.join(tessdata, "chi_sim.traineddata")
    if not os.path.exists(chi_sim):
        log("[2/2] 下载简体中文语言包 chi_sim.traineddata …")
        ok_lang = False
        for url in CHI_SIM_URLS:
            try:
                _download(url, chi_sim)
                ok_lang = True
                break
            except Exception as exc:  # noqa: BLE001
                log(f"  通道不可用 {url.split('/')[2]}：{exc}")
        if not ok_lang:
            log("  中文语言包下载失败（不影响英文识别，可稍后手动放入 tessdata/）")

    exe = os.path.join(BIN_DIR, "tesseract.exe")
    if os.path.exists(exe):
        log(f"\n✅ Tesseract 已内置：{exe}")
        log("验证：python -c \"import pytesseract; print(pytesseract.get_tesseract_version())\"")
        return 0
    log("\n⚠ 安装后未在 bin/tesseract/ 找到 tesseract.exe，请检查安装包路径参数。")
    return 1


def setup_posix():
    if sys.platform == "darwin":
        cmds = [["brew", "install", "tesseract", "tesseract-lang"]]
    else:
        cmds = [
            ["sudo", "apt-get", "install", "-y", "tesseract-ocr", "tesseract-ocr-chi-sim"],
            ["sudo", "yum", "install", "-y", "tesseract", "tesseract-langpack-chi_sim"],
        ]
    for cmd in cmds:
        if shutil.which(cmd[0]):
            try:
                _run(cmd)
                exe = shutil.which("tesseract")
                log(f"\n✅ Tesseract 已安装：{exe}")
                return 0
            except RuntimeError as exc:
                log(f"  安装命令失败：{exc}")
                break
    log("\n⚠ 未能自动安装。请手动执行上方命令，或将 tesseract 放入项目 bin/tesseract/ 目录。")
    return 1


def main():
    log("=" * 60)
    log("Tesseract 本地打包工具（目标目录：bin/tesseract/）")
    log("=" * 60)
    existing = os.path.join(BIN_DIR, "tesseract.exe")
    if os.path.exists(existing):
        log(f"已检测到内置版本：{existing}，无需重复安装。")
        return 0

    if os.name == "nt":
        return setup_windows()
    return setup_posix()


if __name__ == "__main__":
    sys.exit(main())
