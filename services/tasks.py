# -*- coding: utf-8 -*-
"""媒体异步任务：内置线程队列（Windows 无 Redis 默认可用）+ Celery 兼容。

任务清单（名称即路由，线程/Celery 共用同一函数体）：
- media.verify        上传完成后从 R2 流式拉回整文件做 SHA-256 审计
- media.backup        主桶 → 备份桶 服务端拷贝（异步"云端备份"）
- media.promote       proxy 通道：把本地组装好的成品整体上传 R2（断点/分块由 boto3 处理）
- media.delete_remote 删除 R2 对象（主桶 + 备份桶），与数据库行删除解耦

引擎选择：
- MEDIA_ASYNC_ENGINE=thread（默认）：进程内 daemon 线程消费队列，无外部依赖；
- MEDIA_ASYNC_ENGINE=celery：调用 services/tasks_celery.py 注册的 Celery 任务，
  需另行启动 celery worker（Linux 生产环境）。
"""
import logging
import queue as _queue
import threading

from models import (
    get_media_item,
    set_media_status,
    update_media_item,
)

log = logging.getLogger("media.tasks")

_REGISTRY = {}
_q = _queue.Queue()
_workers = []
_lock = threading.Lock()
_app = None
_STARTED = False


def _item(item_id):
    """取媒体记录为 dict（sqlite3.Row 无 .get，任务里统一用 dict）。"""
    row = get_media_item(item_id)
    return dict(row) if row is not None else None


def task(name):
    """注册任务函数（线程引擎与 Celery 共用同一函数体）。"""
    def decorator(fn):
        _REGISTRY[name] = fn
        return fn
    return decorator


def init(app):
    """在应用工厂内调用：按配置启动线程 worker（celery 引擎则无需启动）。"""
    global _app, _STARTED
    _app = app
    if app.config.get("TESTING"):
        return
    if app.config.get("MEDIA_ASYNC_ENGINE", "thread") != "thread":
        return
    with _lock:
        if _STARTED:
            return
        count = max(1, int(app.config.get("MEDIA_ASYNC_WORKERS", 2)))
        for i in range(count):
            t = threading.Thread(
                target=_worker_loop, name=f"media-worker-{i}", daemon=True)
            t.start()
            _workers.append(t)
        _STARTED = True
        log.info("媒体异步任务线程队列已启动（%d 个 worker）", count)


def enqueue(name, **payload):
    """把任务投递到线程队列；engine=celery 时改发 Celery 消息。"""
    if _app is None:
        return False
    engine = _app.config.get("MEDIA_ASYNC_ENGINE", "thread")
    if engine == "celery":
        try:
            from services.tasks_celery import celery_app
        except Exception as exc:  # celery 未安装等：降级线程队列
            log.warning("Celery 不可用，降级线程队列：%s", exc)
        else:
            celery_app.send_task(name, kwargs=payload)
            return True
    _q.put((name, payload))
    return True


def _worker_loop():
    while True:
        try:
            name, payload = _q.get(timeout=2.0)
        except _queue.Empty:
            continue
        fn = _REGISTRY.get(name)
        if fn is None:
            log.error("未知任务：%s", name)
            _q.task_done()
            continue
        try:
            with _app.app_context():
                fn(**payload)
        except Exception:
            log.exception("任务 %s(%s) 执行失败", name, payload)
        finally:
            _q.task_done()


# ================================================================
# media.verify —— R2 整文件 SHA-256 审计
# ================================================================
@task("media.verify")
def media_verify(item_id):
    item = _item(item_id)
    if not item or not item.get("r2_key"):
        return
    cfg = _app.config
    if not cfg.get("MEDIA_VERIFY_ON_COMPLETE"):
        return
    size = int(item.get("size_bytes") or 0)
    if size > int(cfg.get("MEDIA_AUDIT_MAX_BYTES", 2 * 1024 ** 3)):
        log.info("item %s 超过审计阈值，跳过整文件校验", item_id)
        _maybe_backup(item_id, item)
        return

    import hashlib

    import services.r2 as r2

    key = item["r2_key"]
    bucket = item.get("r2_bucket") or r2.main_bucket()
    set_media_status(item_id, "verifying")
    try:
        client = r2.get_client()
        resp = client.get_object(Bucket=bucket, Key=key)
        body, digest, got = resp["Body"], hashlib.sha256(), 0
        while True:
            block = body.read(1024 * 1024)
            if not block:
                break
            got += len(block)
            digest.update(block)
        body.close()
        sha = digest.hexdigest()
    except Exception as exc:
        set_media_status(item_id, "failed", error=f"审计失败：{exc}")
        return

    if got != size:
        set_media_status(item_id, "failed",
                         error=f"审计失败：R2 对象大小 {got} ≠ 声明 {size}，请重新上传")
        return
    old = item.get("sha256") or ""
    if old and old.lower() != sha:
        set_media_status(item_id, "failed",
                         error="审计失败：SHA-256 与客户端声明不一致，请重新上传")
        return
    update_media_item(item_id, sha256=sha)
    set_media_status(item_id, "ready")
    _maybe_backup(item_id, item)


def _maybe_backup(item_id, item=None):
    """若配置了备份桶则投递备份任务。"""
    item = item or _item(item_id)
    if not item:
        return
    import services.r2 as r2

    try:
        if r2.backup_bucket():
            enqueue("media.backup", item_id=item_id)
    except Exception as exc:
        log.warning("item %s 投递备份失败：%s", item_id, exc)


# ================================================================
# media.backup —— 主桶 → 备份桶（同账号服务端拷贝）
# ================================================================
@task("media.backup")
def media_backup(item_id):
    item = _item(item_id)
    if not item or not item.get("r2_key"):
        return
    import services.r2 as r2

    if not r2.backup_bucket():
        return
    try:
        target = r2.copy_to_backup(item["r2_key"])
    except Exception as exc:
        update_media_item(item_id, error=f"云备份失败：{exc}")
        log.warning("item %s 云备份失败：%s", item_id, exc)
        return
    set_media_status(item_id, "backed_up")
    log.info("item %s 已备份到桶 %s", item_id, target)


# ================================================================
# media.promote —— proxy 通道：本地成品整体上传 R2
# ================================================================
@task("media.promote")
def media_promote(item_id):
    import os

    import services.media_files as mf
    import services.r2 as r2

    item = _item(item_id)
    if not item or item.get("channel") != "proxy":
        return
    if not r2.available():
        set_media_status(item_id, "ready",
                         error="R2 依赖未安装，当前仅保存在本地")
        return
    try:
        r2._cfg()  # 校验 R2 凭据是否齐全
    except Exception as exc:
        set_media_status(item_id, "ready", error=f"R2 未配置，仅保存在本地：{exc}")
        return

    local = mf.item_local_path(item)
    if not local or not os.path.exists(local):
        set_media_status(item_id, "failed", error="本地文件缺失，无法转存 R2")
        return

    from boto3.s3.transfer import TransferConfig

    key = item["r2_key"]
    bucket = item.get("r2_bucket") or r2.main_bucket()
    cfg = _app.config
    set_media_status(item_id, "promoting")
    try:
        client = r2.get_client()
        size = os.path.getsize(local)
        part = max(5 * 1024 * 1024, int(cfg.get("MEDIA_PART_SIZE", 16 * 1024 * 1024)))
        client.upload_fileobj(
            Fileobj=open(local, "rb"),
            Bucket=bucket,
            Key=key,
            Config=TransferConfig(
                multipart_threshold=part,
                multipart_chunksize=part,
                max_concurrency=4,
            ),
        )
    except Exception as exc:
        set_media_status(item_id, "failed", error=f"转存 R2 失败：{exc}")
        return

    if cfg.get("MEDIA_KEEP_LOCAL", True):
        # 保留本地副本：local_file 不动，即"双重地址"（本地 + 云端）
        set_media_status(item_id, "ready")
    else:
        update_media_item(item_id, local_file=None)
        mf.cleanup_item(item_id)
        set_media_status(item_id, "ready")
    log.info("item %s 已转存 R2（%s 字节）", item_id, size)
    _maybe_backup(item_id)


# ================================================================
# media.delete_remote —— 删除 R2 对象（行删除后调用，含备份桶）
# ================================================================
@task("media.delete_remote")
def media_delete_remote(r2_key, r2_bucket="", backup_bucket=""):
    if not r2_key:
        return
    import services.r2 as r2

    try:
        r2.delete_object(r2_key, bucket=r2_bucket or None)
    except Exception as exc:
        log.warning("删除 R2 主桶对象 %s 失败：%s", r2_key, exc)
    if backup_bucket:
        try:
            r2.delete_object(r2_key, bucket=backup_bucket)
        except Exception as exc:
            log.warning("删除 R2 备份桶对象 %s 失败：%s", r2_key, exc)
