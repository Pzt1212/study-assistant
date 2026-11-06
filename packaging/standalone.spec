# -*- mode: python ; coding: utf-8 -*-
# 学习助手 · 单机单人版打包配置
# 构建：pyinstaller --noconfirm packaging/standalone.spec
# 产物：dist/exe-dist/学习助手/学习助手.exe（整个文件夹即发布包）
#
# 说明：
# - onedir 模式：启动快、防杀软误报率低，整个文件夹复制到任意位置即可运行；
# - templates/static/bin(tesseract OCR 引擎) 打进 _internal；
# - 数据库/上传/日志运行时落在 exe 旁（见 standalone.py），不在包内。

import os

ROOT = os.path.dirname(SPECPATH)  # 项目根目录

a = Analysis(
    [os.path.join(ROOT, 'standalone.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, 'templates'), 'templates'),
        (os.path.join(ROOT, 'static'), 'static'),
        (os.path.join(ROOT, 'bin', 'tesseract'), 'bin/tesseract'),
    ],
    hiddenimports=[
        # 以下均由静态分析自动发现，这里显式列出兜底
        'click',
        'bcrypt',
        'PIL',
        'pytesseract',
        'requests',
        'services',
        'services.audio_placeholder',
        'services.csrf',
        'services.tasks',
        'blueprints',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='学习助手',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=os.path.join(ROOT, 'static', 'img', 'app_icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='学习助手',
)
