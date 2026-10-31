# -*- coding: utf-8 -*-
"""占位背景音乐生成服务。

项目要求「内置至少 3 首示例曲目，文件可占位」。
本服务使用 Python 标准库 wave 生成 3 段轻缓的纯音旋律（WAV 格式），
保证播放器开箱即用（无需依赖任何音频资源）。

重要：这些只是占位音，用于验证播放器功能。用户可随时用自己的音乐文件
替换 static/music/ 目录下的文件（支持 mp3/ogg/wav 等浏览器可播放格式），
文件名保持不变即可，无需改动任何代码。

示例曲目：
- sample-1.wav  晨光（舒缓单音渐变）
- sample-2.wav  林间（三音上行循环）
- sample-3.wav  星夜（柔和双音交替）
"""
import math
import os
import struct
import wave

# 采样率 / 声道 / 位深（16bit 单声道，兼容性最好）
SAMPLE_RATE = 22050
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16 位 = 2 字节

# 音符频率（Hz）：A4/B4/C#5/E5/A5 等，构成简单动听的小调五声音阶
NOTES = {
    "A4": 440.0, "B4": 493.88, "C5": 523.25, "D5": 587.33,
    "E5": 659.25, "F5": 698.46, "G5": 783.99, "A5": 880.0,
    "C6": 1046.5,
}


def _write_frame(frames, freq, duration, volume=0.25, attack=0.05, release=0.15):
    """向 frames 列表追加一个音符（带淡入淡出包络，避免爆音）。

    :param frames:   输出帧列表（每个元素是 16bit 采样值）
    :param freq:     音符频率
    :param duration: 音符时长（秒）
    :param volume:   音量（0~1）
    :param attack:   淡入时长（秒）
    :param release:  淡出时长（秒）
    """
    n = int(duration * SAMPLE_RATE)
    for i in range(n):
        t = i / SAMPLE_RATE
        # 包络：先线性淡入，再线性淡出
        env = min(1.0, t / attack, (duration - t) / release)
        # 基频 + 少量二次谐波，音色更饱满
        value = volume * env * (
            math.sin(2 * math.pi * freq * t)
            + 0.35 * math.sin(2 * math.pi * freq * 2 * t)
        )
        frames.append(int(value * 32767))


def _generate_track(melody):
    """根据旋律（(音符, 秒数) 列表）生成 16bit 单声道采样帧列表。"""
    frames = []
    for note, dur in melody:
        freq = NOTES[note]
        _write_frame(frames, freq, dur)
    return frames


def _save_wav(path, frames):
    """将采样帧列表写入 WAV 文件。"""
    with wave.open(path, "w") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(b"".join(struct.pack("<h", f) for f in frames))


# 三段示例旋律
_MELODIES = {
    "sample-1.wav": [
        ("A4", 1.2), ("C5", 1.2), ("E5", 1.6), ("A5", 2.0),
        ("E5", 1.2), ("C5", 1.2), ("A4", 1.6),
    ],
    "sample-2.wav": [
        ("C5", 0.6), ("D5", 0.6), ("E5", 0.9), ("G5", 1.2),
        ("E5", 0.6), ("G5", 0.6), ("A5", 0.9), ("G5", 1.2),
    ],
    "sample-3.wav": [
        ("A4", 1.5), ("E5", 1.5), ("C6", 1.5), ("E5", 1.5),
        ("B4", 1.5), ("G5", 1.5), ("E5", 1.5), ("A5", 2.0),
    ],
}


def ensure_sample_music(music_dir):
    """确保 static/music 目录下存在示例曲目。

    若目录为空或缺少示例文件，则自动生成。返回生成的文件名列表。
    这是幂等操作，可安全地在应用启动时调用。
    """
    os.makedirs(music_dir, exist_ok=True)
    created = []
    for filename, melody in _MELODIES.items():
        path = os.path.join(music_dir, filename)
        if not os.path.exists(path):
            frames = _generate_track(melody)
            _save_wav(path, frames)
            created.append(filename)
    return created


if __name__ == "__main__":
    # 命令行直接运行：python -m services.audio_placeholder
    # 用于手动（重新）生成占位音乐
    import sys

    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static", "music",
    )
    created = ensure_sample_music(out_dir)
    print(f"占位音乐目录：{out_dir}")
    print("已生成/确认：" + (", ".join(created) if created else "已全部存在"))
