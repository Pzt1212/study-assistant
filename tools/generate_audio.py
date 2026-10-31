# -*- coding: utf-8 -*-
"""手动生成/重新生成占位音乐脚本。

用法（在项目根目录执行）：
    python tools/generate_audio.py

生成 3 段 WAV 占位曲目到 static/music/ 目录。
应用启动时也会自动生成（幂等），此脚本用于手动重新生成。
"""
import os
import sys

# 确保可以导入 services 包（从项目根目录运行）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.audio_placeholder import ensure_sample_music  # noqa: E402

if __name__ == "__main__":
    music_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static",
        "music",
    )
    created = ensure_sample_music(music_dir)
    print(f"占位音乐目录：{music_dir}")
    print("已生成：" + (", ".join(created) if created else "（全部已存在，未改动）"))
