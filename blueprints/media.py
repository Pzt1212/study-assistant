# -*- coding: utf-8 -*-
"""媒体库蓝图：视频/音频 直连分块上传、Range 播放、R2 异步备份。

架构（无公网 IP 环境，"绕过 Tunnel"的落地方式）：
- 网页、API、签发请求 → 走 Cloudflare Tunnel 域名（本站，轻量）；
- 视频字节流 → 浏览器把文件切成小块，直接 PUT 到 Cloudflare R2 的
  预签名分块 URL（R2 全球边缘就近收流，不再穿隧道绕路海外）；
- 播放 → 私有桶预签名 GET（Range 支持 + 有效期防盗链 + 用户目录隔离）；
- 云端备份 → 上传完成后入队异步任务：SHA-256 审计 → 主桶拷贝到备份桶。

两条上传通道（由 MEDIA_UPLOAD_CHANNEL 配置）：
- r2    （默认）：浏览器 S3 multipart 直传，本站只签发 URL 与记录元数据；
- proxy：resumable.js 分块 POST 到本站（适合日后公网 IP / 国内 frp 直连），
  本站加密落盘 → 组装 → 异步整体转存 R2（"先传本地再转云"原始方案）。

安全分层：
1. 全部本站 API 走既有登录会话 + 全站 CSRF（X-CSRFToken 头）；
2. 对象键按用户目录隔离（media/u<uid>/…），只给属主签发 URL；
3. 私有桶 + 预签名（有效期 MEDIA_URL_TTL）实现防盗链与时效；
4. proxy 通道分块 Fernet 加密落盘；传输全程 HTTPS；
5. 整文件 SHA-256 审计 + 分块数/总字节校验保证完整性。
"""
import math
import os

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required

import services.media_files as mf
import services.r2 as r2
import services.tasks as tasks
from models import (
    clear_media_chunks,
    count_media_bytes,
    create_media_item,
    delete_media_item,
    get_media_item,
    get_media_item_owned,
    list_media_chunks,
    list_media_items,
    set_media_chunk,
    set_media_status,
    sum_media_chunks,
    update_media_item,
)

media = Blueprint("media", __name__, url_prefix="/media",
                  template_folder="../templates")

# 状态机文案（前端展示用）
STATUS_LABELS = {
    "init": "初始化",
    "uploading": "上传中",
    "promoting": "转存云端中",
    "ready": "就绪",
    "verifying": "校验中",
    "backed_up": "已备份",
    "failed": "失败",
}
# 允许播放的状态
PLAYABLE_STATUS = {"ready", "verifying", "backed_up"}
# 一次最多批量签发的分块 URL 数（避免请求过大）
MAX_PART_URLS_PER_CALL = 24


class MediaBadRequest(Exception):
    """业务校验失败，统一转成 {"ok": false, "error": msg} 400。"""


# ================================================================
# 小工具
# ================================================================
def _ok(**data):
    return jsonify(ok=True, **data)


def _err(msg, code=400):
    return jsonify(ok=False, error=msg), code


@media.errorhandler(MediaBadRequest)
def _bad_request(exc):
    return _err(str(exc), 400)


@media.errorhandler(404)
def _not_found(_exc):
    return _err("媒体不存在或已删除", 404)


@media.errorhandler(403)
def _forbidden(_exc):
    return _err("无权访问该媒体", 403)


@media.errorhandler(401)
def _unauthorized(_exc):
    """API 未登录时返回 JSON（页面仍走 Flask-Login 的登录跳转）。"""
    return _err("请先登录", 401)


def _json_item(row):
    """把 DB 行序列化为前端友好的 JSON。"""
    item = dict(row)
    item["id"] = int(item["id"])
    item["sizeBytes"] = int(item.get("size_bytes") or 0)
    item["uploadedBytes"] = int(item.get("uploaded_bytes") or 0)
    item["partSize"] = int(item.get("part_size") or 0)
    item["uploadId"] = item.get("r2_upload_id") or None
    status = item.get("status") or "init"
    item["status"] = status
    item["statusLabel"] = STATUS_LABELS.get(status, status)
    item["createdAt"] = item.pop("created_at", "")
    item["updatedAt"] = item.pop("updated_at", "")
    # 可播放性：r2 就绪 或 本地成品存在
    local_ok = bool(item.get("local_file"))
    item["playable"] = (
        (item["channel"] == "r2" and status in PLAYABLE_STATUS and bool(item.get("r2_key")))
        or (item["channel"] == "proxy" and (local_ok or status in PLAYABLE_STATUS))
    )
    return item


def _get_owned(item_id):
    """取媒体记录并做属主/管理员权限判断，失败直接 abort。

    统一返回 dict（sqlite3.Row 不支持 .get，dict 更不易出错）。
    """
    row = get_media_item_owned(
        item_id, current_user.id, is_admin=(current_user.role >= 2)
    )
    if row is None:
        if get_media_item(item_id):
            abort(403)
        abort(404)
    return dict(row)


def _ext_of(filename):
    return os.path.splitext(str(filename or ""))[1].lstrip(".").lower()


def _validate_new_upload(filename, size):
    """校验文件名/扩展名/大小/配额，返回 (ext, title)；非法抛 MediaBadRequest。"""
    ext = _ext_of(filename)
    cfg = current_app.config
    if not ext or ext not in cfg["MEDIA_ALLOWED_EXTENSIONS"]:
        raise MediaBadRequest("不支持的文件类型（允许：" +
                              " ".join(sorted(cfg["MEDIA_ALLOWED_EXTENSIONS"])) + "）")
    try:
        size = int(size)
    except (TypeError, ValueError):
        raise MediaBadRequest("文件大小参数非法")
    if size <= 0:
        raise MediaBadRequest("文件大小必须大于 0")
    if size > int(cfg["MEDIA_MAX_SIZE"]):
        raise MediaBadRequest(
            f"文件超过大小上限 {int(cfg['MEDIA_MAX_SIZE']) // (1024**3)}GB")
    quota = int(cfg["MEDIA_PER_USER_QUOTA_BYTES"] or 0)
    if quota > 0 and count_media_bytes(current_user.id) + size > quota:
        raise MediaBadRequest("超出个人容量配额，请先删除旧媒体")
    title = (request.json or {}).get("title") or ""
    title = title.strip() or os.path.splitext(os.path.basename(filename))[0]
    return ext, title[:120]


def _make_r2_session(filename, size, mime):
    """创建 r2 直传分块会话：R2 CreateMultipartUpload + DB 行。"""
    ext, title = _validate_new_upload(filename, size)
    cfg = current_app.config
    key = r2.make_key(current_user.id, filename)
    content_type = mime or "application/octet-stream"
    upload_id = r2.create_multipart_upload(key, content_type=content_type)
    part_size = int(cfg["MEDIA_PART_SIZE"])
    item_id = create_media_item(
        user_id=current_user.id, title=title, filename=filename, ext=ext,
        size_bytes=int(size), channel="r2", r2_key=key,
        part_size=part_size, mime=content_type, r2_upload_id=upload_id,
    )
    return get_media_item(item_id), part_size


def _make_proxy_session(filename, size, mime):
    """创建 proxy 中转会话：仅 DB 行 + 本地目录，转存 R2 由异步任务做。"""
    ext, title = _validate_new_upload(filename, size)
    cfg = current_app.config
    key = r2.make_key(current_user.id, filename)
    part_size = int(cfg["MEDIA_PART_SIZE"])
    item_id = create_media_item(
        user_id=current_user.id, title=title, filename=filename, ext=ext,
        size_bytes=int(size), channel="proxy", r2_key=key,
        part_size=part_size, mime=mime or "application/octet-stream",
    )
    mf.item_dir(item_id)  # 预创建工作目录
    return get_media_item(item_id), part_size


# ================================================================
# 页面
# ================================================================
@media.route("")
@login_required
def index():
    return render_template("media/index.html")


# ================================================================
# API：配置 / 列表 / 详情
# ================================================================
@media.route("/api/config")
@login_required
def api_config():
    cfg = current_app.config
    return _ok(config={
        "channel": cfg["MEDIA_UPLOAD_CHANNEL"],
        "partSize": int(cfg["MEDIA_PART_SIZE"]),
        "maxSize": int(cfg["MEDIA_MAX_SIZE"]),
        "urlTtl": int(cfg["MEDIA_URL_TTL"]),
        "verify": bool(cfg.get("MEDIA_VERIFY_ON_COMPLETE", True)),
        "perUserQuotaBytes": int(cfg.get("MEDIA_PER_USER_QUOTA_BYTES", 0)),
        "r2Ready": r2.ready() if r2.available() else False,
        "engine": cfg.get("MEDIA_ASYNC_ENGINE", "thread"),
        "allowedExtensions": sorted(cfg["MEDIA_ALLOWED_EXTENSIONS"]),
    })


@media.route("/api/items", methods=["GET"])
@login_required
def api_list_items():
    rows = list_media_items(current_user.id, limit=300)
    quota = int(current_app.config.get("MEDIA_PER_USER_QUOTA_BYTES", 0))
    return _ok(
        items=[_json_item(r) for r in rows],
        quota={
            "usedBytes": count_media_bytes(current_user.id),
            "limitBytes": quota,
        },
    )


@media.route("/api/items/<int:item_id>", methods=["GET"])
@login_required
def api_item(item_id):
    return _ok(item=_json_item(_get_owned(item_id)))


# ================================================================
# API：创建上传会话（r2 直传 / proxy 中转 由配置自动选择）
# ================================================================
@media.route("/api/items", methods=["POST"])
@login_required
def api_create_session():
    if not r2.available():
        return _err("缺少依赖 boto3，请执行 pip install -r requirements-media.txt", 503)
    data = request.get_json(silent=True) or {}
    filename = str(data.get("filename") or "").strip()
    size = data.get("size")
    mime = str(data.get("mime") or "").strip() or None
    channel = current_app.config["MEDIA_UPLOAD_CHANNEL"]

    try:
        if channel == "proxy":
            item_row, part_size = _make_proxy_session(filename, size, mime)
        else:
            item_row, part_size = _make_r2_session(filename, size, mime)
    except r2.R2Error as exc:
        return _err(str(exc), 502)
    except Exception as exc:
        current_app.logger.exception("创建上传会话失败")
        return _err(f"创建上传会话失败：{exc}", 500)

    item = _json_item(item_row)
    return _ok(item=item, upload={
        "channel": item["channel"],
        "partSize": part_size,
        "partCount": max(1, math.ceil(item["sizeBytes"] / part_size)),
        "urlTtl": int(current_app.config["MEDIA_URL_TTL"]),
        "chunkEndpoint": url_for("media.api_proxy_chunk", item_id=item["id"]),
    })


# ================================================================
# API：r2 直传 —— 续传查询 / 签发分块 URL / 完成 / 中止
# ================================================================
@media.route("/api/items/<int:item_id>/parts", methods=["GET"])
@login_required
def api_r2_parts(item_id):
    row = _get_owned(item_id)
    if row["channel"] != "r2" or not row.get("r2_upload_id"):
        return _err("当前会话不支持续传查询")
    try:
        parts = r2.list_parts(row["r2_key"], row["r2_upload_id"])
    except r2.R2Error as exc:
        return _err(str(exc), 502)
    done_bytes = sum(p["Size"] for p in parts)
    update_media_item(item_id, uploaded_bytes=done_bytes)
    return _ok(
        uploaded=[p["PartNumber"] for p in parts],
        uploadedBytes=done_bytes,
        expectedBytes=int(row["size_bytes"]),
        partCount=max(1, math.ceil(int(row["size_bytes"]) / int(row["part_size"]))),
    )


@media.route("/api/items/<int:item_id>/part-urls", methods=["POST"])
@login_required
def api_r2_part_urls(item_id):
    row = _get_owned(item_id)
    if row["channel"] != "r2":
        return _err("非 r2 直传会话")
    if row["status"] not in ("uploading", "init"):
        return _err("会话不在上传中", 409)
    data = request.get_json(silent=True) or {}
    start = int(data.get("start") or 1)
    count = int(data.get("count") or 1)
    if start < 1 or count < 1 or count > MAX_PART_URLS_PER_CALL:
        return _err(f"start/count 非法（count 1~{MAX_PART_URLS_PER_CALL}）")
    ttl = int(current_app.config["MEDIA_URL_TTL"])
    try:
        urls = r2.presign_part_batch(
            row["r2_key"], row["r2_upload_id"], start, count, expires=ttl)
    except r2.R2Error as exc:
        return _err(str(exc), 502)
    return _ok(urls=urls, expiresIn=ttl)


@media.route("/api/items/<int:item_id>/complete", methods=["POST"])
@login_required
def api_r2_complete(item_id):
    row = _get_owned(item_id)
    if row["channel"] != "r2":
        return _err("非 r2 直传会话")
    if row["status"] not in ("uploading", "init"):
        return _err("会话状态异常，无法完成", 409)
    key = row["r2_key"]
    upload_id = row["r2_upload_id"]
    if not upload_id:
        return _err("缺少上传会话 ID", 409)

    # 以 R2 侧 ListParts 为权威依据（不信任客户端回传的 ETag）
    try:
        parts = r2.list_parts(key, upload_id)
    except r2.R2Error as exc:
        return _err(str(exc), 502)

    total = sum(p["Size"] for p in parts)
    expected = int(row["size_bytes"])
    if total != expected:
        r2.abort_multipart_upload(key, upload_id)
        update_media_item(item_id, uploaded_bytes=total)
        set_media_status(item_id, "failed",
                         error=f"分块总字节 {total} 与声明 {expected} 不符，已中止")
        return _err(f"分块上传不完整或字节不符（已收 {total}/{expected}），"
                    f"请续传后重试", 400)

    try:
        r2.complete_multipart_upload(key, upload_id, parts)
    except r2.R2Error as exc:
        return _err(str(exc), 502)

    # 回填分块进度记录（断点续传/审计留痕）
    clear_media_chunks(item_id)
    for p in parts:
        set_media_chunk(item_id, p["PartNumber"], p["Size"], etag=p["ETag"])
    update_media_item(item_id, r2_upload_id=None,
                      uploaded_bytes=total, size_bytes=expected)
    set_media_status(item_id, "ready")

    # 入队校验（通过后自动再入队备份）
    if current_app.config.get("MEDIA_VERIFY_ON_COMPLETE", True):
        tasks.enqueue("media.verify", item_id=item_id)
    else:
        import services.r2 as _r2

        try:
            if _r2.backup_bucket():
                tasks.enqueue("media.backup", item_id=item_id)
        except Exception:
            pass

    return _ok(item=_json_item(get_media_item(item_id)))


@media.route("/api/items/<int:item_id>/abort", methods=["POST"])
@login_required
def api_r2_abort(item_id):
    row = _get_owned(item_id)
    if row.get("r2_upload_id"):
        try:
            r2.abort_multipart_upload(row["r2_key"], row["r2_upload_id"])
        except r2.R2Error:
            pass
    clear_media_chunks(item_id)
    set_media_status(item_id, "failed", error="用户中止上传")
    update_media_item(item_id, r2_upload_id=None)
    return _ok()


# ================================================================
# API：播放地址（防盗链）与 Range 兜底流
# ================================================================
@media.route("/api/items/<int:item_id>/play", methods=["GET"])
@login_required
def api_play(item_id):
    """签发播放地址（单一源）。默认 R2 预签名直连（防盗链 + Range）；
    仅当 MEDIA_PLAYBACK_SOURCE=self 且本地成品仍在时走本站 Range 兜底流。
    """
    row = _get_owned(item_id)
    if not row["playable"]:
        return _err("媒体尚未就绪或已被删除", 409)
    cfg = current_app.config
    source = cfg["MEDIA_PLAYBACK_SOURCE"]
    ttl = int(cfg["MEDIA_URL_TTL"])

    # 本站本地兜底源（proxy 通道本地成品还在时可用）
    local = mf.item_local_path(row) if row.get("local_file") else None
    local_url = url_for("media.api_stream_local", item_id=item_id) \
        if (local and os.path.exists(local)) else None

    r2_url = None
    if row.get("r2_key") and r2.available():
        try:
            r2_url = r2.presign_download_url(row["r2_key"], expires=ttl)
        except r2.R2Error as exc:
            return _err(str(exc), 502)

    if source == "self" and local_url:
        return _ok(url=local_url, source="self", expiresIn=ttl)
    if r2_url:
        return _ok(url=r2_url, source="r2", expiresIn=ttl)
    if local_url:
        return _ok(url=local_url, source="self", expiresIn=ttl)
    return _err("暂无可用的播放源（检查 R2 配置或本地文件）", 503)


@media.route("/api/items/<int:item_id>/stream")
@login_required
def api_stream_local(item_id):
    """本地文件 Range 流（conditional=True 自动支持 206 断点续播）。

    仅 proxy 通道 / R2 不可用时的兜底：正常播放请用 R2 直连 URL。
    """
    row = _get_owned(item_id)
    path = mf.item_local_path(row)
    if not row.get("local_file") or not path or not os.path.exists(path):
        abort(404)
    resp = send_file(
        path,
        mimetype=row.get("mime") or "application/octet-stream",
        as_attachment=False,
        conditional=True,          # 支持 Range / If-Range / 206
        max_age=0,
    )
    resp.headers["Accept-Ranges"] = "bytes"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


# ================================================================
# API：删除 / 重新校验 / 重新备份
# ================================================================
@media.route("/api/items/<int:item_id>", methods=["DELETE"])
@login_required
def api_delete(item_id):
    row = _get_owned(item_id)
    if row["channel"] == "proxy" and row["status"] in ("uploading", "promoting"):
        return _err("文件仍在上传/转存中，请稍后删除", 409)
    key, bucket = row.get("r2_key"), row.get("r2_bucket") or ""
    if row.get("r2_upload_id"):
        try:
            r2.abort_multipart_upload(key, row["r2_upload_id"])
        except r2.R2Error:
            pass
    # 先删 DB 行与本地文件，再异步清 R2 对象（删除动作不阻塞响应）
    backup = ""
    try:
        import services.r2 as _r2

        backup = _r2.backup_bucket()
    except Exception:
        pass
    if row.get("local_file"):
        try:
            mf.cleanup_item(row["id"])
        except Exception:
            pass
    delete_media_item(item_id)
    if key:
        tasks.enqueue("media.delete_remote", r2_key=key,
                      r2_bucket=bucket, backup_bucket=backup)
    return _ok()


@media.route("/api/items/<int:item_id>/verify", methods=["POST"])
@login_required
def api_verify(item_id):
    row = _get_owned(item_id)
    if not row.get("r2_key") or not r2.available():
        return _err("R2 不可用，无法校验", 503)
    tasks.enqueue("media.verify", item_id=item_id)
    return _ok(message="已重新入队校验任务")


@media.route("/api/items/<int:item_id>/backup", methods=["POST"])
@login_required
def api_backup(item_id):
    row = _get_owned(item_id)
    if row["status"] not in ("ready", "verifying", "backed_up", "failed"):
        return _err("当前状态不可备份", 409)
    if not r2.available() or not row.get("r2_key"):
        return _err("R2 不可用", 503)
    try:
        import services.r2 as _r2

        if not _r2.backup_bucket():
            return _err("未配置 R2_BACKUP_BUCKET，无法执行桶级备份", 400)
    except Exception as exc:
        return _err(str(exc), 400)
    tasks.enqueue("media.backup", item_id=item_id)
    return _ok(message="已重新入队云备份任务")


# ================================================================
# API：proxy 通道（resumable.js 分块 → 本站 → 异步转存 R2）
# ================================================================
@media.route("/api/proxy/chunks/<int:item_id>", methods=["GET"])
@login_required
def api_proxy_test_chunk(item_id):
    """resumable.js 断点续传探测：分块已存在返回 200，否则 404。"""
    row = _get_owned(item_id)
    if row["channel"] != "proxy":
        return _err("非 proxy 会话")
    num = _resumable_num()
    if num is None:
        raise MediaBadRequest("缺少分块编号")
    path = mf.chunk_path(item_id, num)
    return ("", 200) if os.path.exists(path) else ("", 404)


@media.route("/api/proxy/chunks/<int:item_id>", methods=["POST"])
@login_required
def api_proxy_chunk(item_id):
    """接收一个分块（兼容 resumable.js 字段；也支持 part= 原始 PUT 模式）。"""
    row = _get_owned(item_id)
    if row["channel"] != "proxy":
        return _err("非 proxy 会话")
    if row["status"] not in ("uploading", "init"):
        return _err("会话状态异常", 409)

    num = _resumable_num()
    if num is None:
        return _err("缺少分块编号（resumableChunkNumber 或 part）")
    # 分块数上限以客户端声明的 chunkSize 推导（resumable 会发送该字段；
    # 缺省按服务端 part_size 计算）。真实分块不会小于该上限对应的单块尺寸，
    # 因此按声明校验即可防越界。
    declared_size = _declared_chunk_size(row)
    if declared_size is None:
        return _err("缺少 resumableChunkSize，无法校验分块边界")
    total_parts = max(1, math.ceil(int(row["size_bytes"]) / declared_size))
    if num < 1 or num > total_parts:
        return _err(f"分块编号越界（1~{total_parts}）")
    f = request.files.get("file")
    if f is None:
        return _err("缺少文件字段 file")
    data = f.read()
    if len(data) > int(row["part_size"]):
        return _err("分块超过单块大小上限")

    try:
        written = mf.save_chunk(item_id, num, data)
    except mf.MediaFileError as exc:
        return _err(str(exc), 500)

    import hashlib as _hl

    md5 = _hl.md5(data).digest().hex()
    set_media_chunk(item_id, num, written, md5=md5)
    current = sum_media_chunks(item_id)
    update_media_item(item_id, uploaded_bytes=min(current, int(row["size_bytes"])))
    return _ok()


@media.route("/api/proxy/chunks/<int:item_id>/missing", methods=["GET"])
@login_required
def api_proxy_missing(item_id):
    """返回尚未收到的分块编号（加快续传）。"""
    row = _get_owned(item_id)
    if row["channel"] != "proxy":
        return _err("非 proxy 会话")
    rows = list_media_chunks(item_id)
    have = {c["part_number"] for c in rows}
    s1 = next((int(c["size_bytes"]) for c in rows if c["part_number"] == 1), 0)
    unit = s1 or int(row["part_size"])
    total = max(1, math.ceil(int(row["size_bytes"]) / unit))
    return _ok(missing=[n for n in range(1, total + 1) if n not in have])


@media.route("/api/proxy/complete/<int:item_id>", methods=["POST"])
@login_required
def api_proxy_complete(item_id):
    """分块齐了 → 组装本地成品 → 入队异步转存 R2。"""
    row = _get_owned(item_id)
    if row["channel"] != "proxy":
        return _err("非 proxy 会话")
    if row["status"] not in ("uploading", "init"):
        return _err("会话状态异常", 409)

    chunks = {c["part_number"]: int(c["size_bytes"])
              for c in list_media_chunks(item_id)}
    if not chunks:
        return _err("还没有收到任何分块", 400)
    # 用首个分块尺寸推导期望块数与连续性（首个分块即标准块大小 S，
    # 期望块数 = ceil(size / S)，除末块外每块必须恰好 S）
    s1 = chunks.get(1)
    if not s1:
        return _err("缺少 1 号分块，无法校验", 400)
    total_parts = max(1, math.ceil(int(row["size_bytes"]) / s1))
    missing = [n for n in range(1, total_parts + 1) if n not in chunks]
    if missing:
        return _err(f"还缺分块：{missing[:20]}{'…' if len(missing) > 20 else ''}", 400)
    for num, sz in chunks.items():
        if num == total_parts:
            if sz > s1:
                return _err(f"末块({num})尺寸异常 {sz} > {s1}", 400)
        elif sz != s1:
            return _err(f"分块 {num} 尺寸异常：{sz} ≠ {s1}", 400)
    got = sum(chunks.values())
    if got != int(row["size_bytes"]):
        return _err(f"分块总字节 {got} 与声明 {row['size_bytes']} 不符", 400)

    try:
        final, sha = mf.assemble(item_id, row["filename"])
    except mf.MediaFileError as exc:
        set_media_status(item_id, "failed", error=f"组装失败：{exc}")
        return _err(str(exc), 500)

    rel = os.path.relpath(final, mf.item_root()).replace("\\", "/")
    update_media_item(item_id, local_file=rel, sha256=sha,
                      uploaded_bytes=int(row["size_bytes"]))
    clear_media_chunks(item_id)
    set_media_status(item_id, "promoting")
    tasks.enqueue("media.promote", item_id=item_id)
    return _ok(item=_json_item(get_media_item(item_id)))


@media.route("/api/proxy/session/<int:item_id>", methods=["DELETE"])
@login_required
def api_proxy_cancel(item_id):
    """取消 proxy 上传：清理本地分块并删除记录。"""
    row = _get_owned(item_id)
    if row["channel"] != "proxy":
        return _err("非 proxy 会话")
    if row["status"] not in ("uploading", "init", "failed"):
        return _err("已完成的媒体请用删除接口", 409)
    try:
        mf.cleanup_item(item_id)
    except Exception:
        pass
    delete_media_item(item_id)
    return _ok()


def _resumable_num():
    """从 resumable.js 表单字段或查询参数取分块编号。"""
    if request.method == "POST":
        try:
            return int(request.form.get("resumableChunkNumber") or "")
        except (TypeError, ValueError):
            pass
        try:
            return int(request.args.get("part") or "")
        except (TypeError, ValueError):
            return None
    try:
        return int(request.args.get("resumableChunkNumber") or "")
    except (TypeError, ValueError):
        try:
            return int(request.args.get("part") or "")
        except (TypeError, ValueError):
            return None


def _declared_chunk_size(row):
    """本次请求声明的分块尺寸：resumableChunkSize > 0 时用它，
    否则退回 item.part_size（原生 part= 上传模式）。"""
    if request.method == "POST":
        raw = request.form.get("resumableChunkSize")
    else:
        raw = request.args.get("resumableChunkSize")
    try:
        value = int(raw or 0)
    except (TypeError, ValueError):
        value = 0
    if value > 0:
        return value
    return int(row["part_size"])


# ================================================================
# 请求级调整：proxy 分块体量较大，不受全局 MAX_CONTENT_LENGTH 限制
# ================================================================
@media.before_request
def _media_before():
    if request.path.startswith("/media/api/proxy/chunks/"):
        # werkzeug 惰性解析请求体，这里放开该路径的 body 上限
        # （分块大小已由业务层校验 ≤ MEDIA_PART_SIZE）
        request.max_content_length = None
    return None
