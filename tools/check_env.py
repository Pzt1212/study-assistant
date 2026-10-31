# -*- coding: utf-8 -*-
"""环境自检工具（模块一）：一键核对运行环境是否齐备。

用法：python tools/check_env.py
输出：Python 库 / 系统依赖（Tesseract）/ 内置目录 / 插件 / 数据库 状态清单
"""
import os
import shutil
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

OUT = []


def line(mark, text):
    OUT.append(f"[{mark}] {text}")


def main():
    line("===", "学习助手 · 环境清单自检")
    line("---", f"Python: {sys.version.split()[0]} ({sys.executable})")

    # 1) Python 运行时依赖
    line("---", "Python 库：")
    required = ["flask", "flask_login", "click", "werkzeug", "bcrypt",
                "PIL", "pytesseract", "requests"]
    for mod in required:
        try:
            __import__(mod)
            line("OK", f"import {mod}")
        except Exception as exc:
            line("FAIL", f"import {mod}: {exc}")
    optional = {
        "rapidocr_onnxruntime": "手写体 OCR 本地插件（可选，未装时手写模式走 Tesseract 降级）",
    }
    line("---", "插件（可选）：")
    for mod, desc in optional.items():
        try:
            __import__(mod)
            line("OK", f"{mod}（{desc}）")
        except Exception:
            line("--", f"{mod} 未安装（{desc}）")

    # 2) 系统/内置依赖：Tesseract
    line("---", "系统依赖：Tesseract-OCR")
    from services.ocr_service import bundled_tesseract_path, resolve_tesseract_cmd
    bundled = bundled_tesseract_path()
    line("OK" if os.path.isfile(bundled) else "--",
         f"内置打包目录 {bundled}")
    resolved = resolve_tesseract_cmd()
    if resolved:
        line("OK", f"可用 Tesseract: {resolved}")
    else:
        line("FAIL", "未找到 tesseract（可联网执行: python tools/setup_tesseract.py 自动内置）")
    path_tess = shutil.which("tesseract")
    line("OK" if path_tess else "--", f"系统 PATH 中的 tesseract: {path_tess or '（无）'}")

    # 3) 数据库
    line("---", "数据库：")
    db_path = os.path.join(ROOT, "data", "study_assistant.db")
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        q = cur.execute("SELECT user_id, subject, COUNT(*) FROM questions "
                        "GROUP BY user_id, subject ORDER BY user_id, subject").fetchall()
        users = cur.execute("SELECT id, username, is_admin FROM users").fetchall()
        line("OK", f"数据库存在：{db_path}")
        line("OK", f"用户: {', '.join(f'{u[1]}(id={u[0]}, admin={u[2]})' for u in users)}")
        for uid, subject, cnt in q:
            line("OK", f"用户 {uid} · {subject}: {cnt} 题")
        conn.close()
    else:
        line("WARN", f"数据库不存在（首次启动会自动创建）：{db_path}")

    # 4) 目录与曲目源
    line("---", "运行目录：")
    for d in ("logs", "uploads", "static/music"):
        p = os.path.join(ROOT, d)
        line("OK" if os.path.isdir(p) else "--", f"{d}/ {'存在' if os.path.isdir(p) else '不存在'}")
    from services.music_source import list_all_tracks
    tracks = list_all_tracks()
    line("OK", f"音乐曲目源：共 {len(tracks)} 首（在线 + 脑波）")

    # 5) 汇总
    fails = sum(1 for x in OUT if x.startswith("[FAIL]"))
    line("===", f"自检完成：{len(OUT)} 行，核心失败 {fails} 项")
    print("\n".join(OUT))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
