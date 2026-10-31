# -*- coding: utf-8 -*-
"""Celery 接入（Linux 生产环境可选，Windows 无 Redis 时请忽略本文件）。

启用方式：
1. pip install celery redis            （见 requirements-media.txt 注释行）
2. 环境变量：
       MEDIA_ASYNC_ENGINE=celery
       CELERY_BROKER_URL=redis://127.0.0.1:6379/0
3. 启动 worker（与 Web 进程同目录）：
       celery -A services.tasks_celery:celery_app worker -l info -P solo
   （单机并发不高时用 -P solo 可省去 Windows/Linux 上 prefork 的内存开销）

任务函数体与线程引擎共用 services/tasks.py 中的同一实现，
这里只负责用 @celery_app.task 把它们注册成可投递消息的任务。
"""
import os

try:
    from celery import Celery
except Exception:  # pragma: no cover - 未安装 celery 时不影响其它功能
    Celery = None


def _build():
    if Celery is None:
        raise ImportError("未安装 celery，请先 pip install celery")
    app = Celery(
        "study_assistant",
        broker=os.environ.get("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0"),
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="Asia/Shanghai",
        enable_utc=True,
        task_ignore_result=True,
        broker_connection_retry_on_startup=True,
    )
    return app


# 模块级实例：celery -A services.tasks_celery:celery_app worker 使用
celery_app = _build()

import services.tasks as _tasks  # noqa: E402  注册线程引擎里的任务函数

for _name in ("media.verify", "media.backup", "media.promote", "media.delete_remote"):
    _fn = _tasks._REGISTRY.get(_name)
    if _fn is not None:
        globals()[_name.replace(".", "_")] = celery_app.task(name=_name)(_fn)
