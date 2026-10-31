# -*- coding: utf-8 -*-
"""Cloudflare R2（S3 兼容）客户端封装。

职责（全部基于官方 boto3，不手写签名协议）：
- 创建分块上传会话、批量签发"上传分块"预签名 PUT URL、查询已传分块、
  完成/中止分块上传（R2 原生 multipart，浏览器据此直传，字节不经过本站）；
- 签发下载/播放用的预签名 GET URL（防盗链：私有桶 + 有效期 + 用户目录隔离）；
- HEAD / 删除 / 主桶 → 备份桶服务端拷贝（备份不占用本站带宽）；
- 一键设置 R2 桶 CORS（浏览器跨域直传的前提）。

约定：
- 桶默认私有。媒体对象键一律放入 "media/u<user_id>/..."，天然按用户隔离；
- 所有失败抛出 R2Error，由调用方转成对客户端的可读错误。
"""
import json
import os
import re
import uuid

from flask import current_app

try:
    import boto3
    from botocore.client import Config as BotoConfig
    from botocore.exceptions import BotoCoreError, ClientError
    _BOTO_OK = True
except Exception:  # 未安装 boto3 时，除本模块外其余功能照常可用
    boto3 = None
    BotoConfig = None
    BotoCoreError = ClientError = Exception
    _BOTO_OK = False


class R2Error(RuntimeError):
    """R2 操作失败（携带对用户友好的中文原因）。"""


def available():
    """boto3 是否可用（未安装时媒体上传相关接口返回明确提示）。"""
    return _BOTO_OK


def ready():
    """R2 是否可完整使用：依赖已装且三项凭据均已配置。"""
    if not _BOTO_OK:
        return False
    cfg = current_app.config
    return all(cfg.get(n) for n in
               ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"))


# ---------------------------------------------------------------- 基础
def _cfg():
    cfg = current_app.config
    missing = [
        name for name in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")
        if not cfg.get(name)
    ]
    if missing:
        raise R2Error("R2 未配置完整（缺少 " + ", ".join(missing) + "），请见部署文档")
    return cfg


def _endpoint(cfg):
    if cfg.get("R2_ENDPOINT_URL"):
        return cfg["R2_ENDPOINT_URL"].rstrip("/")
    return f"https://{cfg['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"


def get_client():
    """取当前应用的 R2 boto3 客户端（按 endpoint+密钥 缓存，无需重复构造）。"""
    if not _BOTO_OK:
        raise R2Error("缺少依赖 boto3，请执行：pip install -r requirements-media.txt")
    cfg = _cfg()
    cache_key = (_endpoint(cfg), cfg["R2_ACCESS_KEY_ID"])
    ext = current_app.extensions
    cached = ext.get("r2_client")
    if not cached or cached[0] != cache_key:
        client = boto3.client(
            "s3",
            endpoint_url=_endpoint(cfg),
            aws_access_key_id=cfg["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=cfg["R2_SECRET_ACCESS_KEY"],
            region_name="auto",
            config=BotoConfig(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                connect_timeout=10,
                read_timeout=60,
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
        ext["r2_client"] = (cache_key, client)
    return ext["r2_client"][1]


def main_bucket():
    return _cfg()["R2_BUCKET"]


def backup_bucket():
    """备份桶名（未配置返回空串，调用方据此决定是否做桶级备份）。"""
    return (_cfg().get("R2_BACKUP_BUCKET") or "").strip()


# ---------------------------------------------------------------- 对象键
def make_key(user_id, filename):
    """生成用户目录下的唯一对象键：media/u<uid>/<uuid16>-<清洗后文件名>。

    播放/下载 URL 只签发到该键，天然做到"谁上传的谁才能拿链接"的隔离。
    """
    base = os.path.basename(str(filename or "media").replace("\\", "/"))
    safe = re.sub(r"[^0-9A-Za-z_.-]", "_", base)
    safe = safe[:96] or "media"
    return f"media/u{int(user_id)}/{uuid.uuid4().hex[:16]}-{safe}"


# ---------------------------------------------------------------- 分块上传（浏览器直传）
def create_multipart_upload(key, content_type=None):
    """创建分块上传会话，返回 UploadId。"""
    cfg = _cfg()
    params = {"Bucket": main_bucket(), "Key": key}
    if content_type:
        params["ContentType"] = content_type
    try:
        return get_client().create_multipart_upload(**params)["UploadId"]
    except ClientError as exc:
        raise R2Error(_describe(exc, "创建上传会话")) from exc


def presign_part_url(key, upload_id, part_number, expires=3600):
    """签发单个分块的预签名 PUT URL（有效期秒，默认 1 小时）。"""
    try:
        return get_client().generate_presigned_url(
            "upload_part",
            Params={"Bucket": main_bucket(), "Key": key,
                    "UploadId": upload_id, "PartNumber": int(part_number)},
            ExpiresIn=max(60, int(expires)),
            HttpMethod="PUT",
        )
    except (BotoCoreError, ClientError) as exc:
        raise R2Error(f"签发分块 URL 失败：{exc}") from exc


def presign_part_batch(key, upload_id, start, count, expires=3600):
    """批量签发 [start, start+count) 分块 URL，返回 {part_number: url}。"""
    urls = {}
    for num in range(int(start), int(start) + int(count)):
        urls[num] = presign_part_url(key, upload_id, num, expires=expires)
    return urls


def list_parts(key, upload_id):
    """列出 R2 侧已成功上传的分块（断点续传/完成校验的权威依据）。

    返回 [{PartNumber, Size, ETag}]（ETag 已去掉引号）。
    """
    client = get_client()
    bucket = main_bucket()
    parts, marker = [], ""
    try:
        while True:
            params = {"Bucket": bucket, "Key": key, "UploadId": upload_id}
            if marker:
                params["PartNumberMarker"] = marker
            resp = client.list_parts(**params)
            for part in resp.get("Parts", []):
                parts.append({
                    "PartNumber": int(part["PartNumber"]),
                    "Size": int(part.get("Size", 0)),
                    "ETag": str(part.get("ETag", "")).strip('"'),
                })
            if resp.get("IsTruncated"):
                marker = resp.get("NextPartNumberMarker", "")
            else:
                break
    except ClientError as exc:
        raise R2Error(_describe(exc, "查询已传分块")) from exc
    parts.sort(key=lambda p: p["PartNumber"])
    return parts


def complete_multipart_upload(key, upload_id, parts):
    """完成分块上传。parts: [{PartNumber, ETag}]（建议传 R2 list_parts 的权威结果）。"""
    try:
        return get_client().complete_multipart_upload(
            Bucket=main_bucket(), Key=key, UploadId=upload_id,
            MultipartUpload={"Parts": [
                {"PartNumber": p["PartNumber"],
                 "ETag": '"' + str(p["ETag"]).strip('"') + '"'} for p in parts
            ]},
        )
    except ClientError as exc:
        raise R2Error(_describe(exc, "完成上传")) from exc


def abort_multipart_upload(key, upload_id):
    """中止分块上传（清理 R2 侧半成品，无副作用）。"""
    try:
        get_client().abort_multipart_upload(
            Bucket=main_bucket(), Key=key, UploadId=upload_id)
    except ClientError:
        pass  # 会话不存在等情形无需报错


# ---------------------------------------------------------------- 播放 / 下载（防盗链）
def presign_download_url(key, expires=3600):
    """签发播放/下载用的预签名 GET URL（私有桶 + 有效期 = 基础防盗链）。"""
    try:
        return get_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": main_bucket(), "Key": key},
            ExpiresIn=max(60, int(expires)),
            HttpMethod="GET",
        )
    except (BotoCoreError, ClientError) as exc:
        raise R2Error(f"签发播放链接失败：{exc}") from exc


def head_object(key):
    """取对象元信息（大小/ETag/元数据），不存在返回 None。"""
    try:
        resp = get_client().head_object(Bucket=main_bucket(), Key=key)
        return {
            "size": int(resp.get("ContentLength", 0)),
            "etag": str(resp.get("ETag", "")).strip('"'),
            "meta": resp.get("Metadata") or {},
        }
    except ClientError:
        return None


def delete_object(key, bucket=None):
    """删除对象（bucket 缺省为主桶；备份桶传入 R2_BACKUP_BUCKET）。"""
    target = bucket or main_bucket()
    try:
        get_client().delete_object(Bucket=target, Key=key)
    except ClientError as exc:
        raise R2Error(_describe(exc, "删除对象")) from exc


def copy_to_backup(key, backup=None):
    """主桶 → 备份桶的服务端拷贝（同账号桶内复制，不占用本站带宽/流量）。"""
    target = backup or backup_bucket()
    if not target:
        raise R2Error("未配置 R2_BACKUP_BUCKET，无法执行桶级备份")
    try:
        get_client().copy_object(
            Bucket=target, Key=key,
            CopySource={"Bucket": main_bucket(), "Key": key},
            MetadataDirective="COPY",
        )
        return target
    except ClientError as exc:
        raise R2Error(_describe(exc, "备份到备份桶")) from exc


# ---------------------------------------------------------------- 桶配置（一次性）
def ensure_bucket_cors(allowed_origins=None):
    """设置/更新主桶 CORS（浏览器跨域直传 R2 的必需步骤）。

    allowed_origins: 允许的页面来源，例如 ["https://你的域名"]；
    缺省取 config.MEDIA_CORS_ORIGINS（JSON 数组），再缺省为 ["*"]。
    说明：预签名 URL 本身是带时效的 bearer 凭据，允许 "*" 不会泄露桶内其它对象。
    """
    cfg = _cfg()
    if not allowed_origins:
        raw = cfg.get("MEDIA_CORS_ORIGINS") or ""
        try:
            allowed_origins = json.loads(raw) if raw else ["*"]
        except (ValueError, TypeError):
            allowed_origins = ["*"]
    rules = [{
        "AllowedOrigins": [str(o) for o in allowed_origins],
        "AllowedMethods": ["GET", "PUT", "HEAD", "POST", "DELETE"],
        "AllowedHeaders": ["*"],
        "ExposeHeaders": ["ETag", "x-amz-request-id", "x-amz-checksum-crc64nvme"],
        "MaxAgeSeconds": 3600,
    }]
    try:
        get_client().put_bucket_cors(
            Bucket=main_bucket(),
            CORSConfiguration={"CORSRules": rules},
        )
        return rules
    except ClientError as exc:
        raise R2Error(_describe(exc, "设置桶 CORS")) from exc


# ---------------------------------------------------------------- 工具
def _describe(exc, action):
    """把 boto3 ClientError 转成可读中文错误。"""
    code = ""
    try:
        code = exc.response.get("Error", {}).get("Code", "")
    except AttributeError:
        pass
    msg = str(exc).split("\n")[0][:300]
    if code == "NoSuchUpload":
        return f"{action}失败：上传会话已过期或不存在，请重试"
    if code in ("AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch"):
        return f"{action}失败：R2 密钥无权访问或签名错误（检查 R2_* 环境变量与令牌权限）"
    return f"{action}失败（{code or '未知错误'}）：{msg}"
