# -*- coding: utf-8 -*-
"""proxy 通道的本地媒体文件工具。

背景：无公网 IP 时默认走 r2 直传通道，本模块几乎不会被调用；当部署环境
获得公网 IP / 国内 frp 直连端口并把 MEDIA_UPLOAD_CHANNEL 切为 "proxy" 时，
浏览器分块 POST 到本站，本站用本模块把分块加密落盘、组装成完整文件、
计算 SHA-256，随后由异步任务整体转存 R2。

安全设计：
- 分块默认用 Fernet（cryptography）加密落盘，密钥取 config.MEDIA_FERNET_KEY；
  未设置时自动生成并持久化到 <MEDIA_ITEM_ROOT>/media_fernet.key（重启不失效）；
- 磁盘文件名一律用无意义 ID，原始文件名只用于展示，绝不直接拼进路径。
"""
import hashlib
import os
import re
import secrets

from flask import current_app

try:
    from cryptography.fernet import Fernet
    _FERNET_OK = True
except Exception:
    Fernet = None
    _FERNET_OK = False


class MediaFileError(RuntimeError):
    """本地媒体文件操作失败。"""


# ---------------------------------------------------------------- 路径
def item_root():
    """proxy 通道媒体根目录（自动创建）。"""
    root = current_app.config["MEDIA_ITEM_ROOT"]
    os.makedirs(root, exist_ok=True)
    return root


def item_dir(item_id):
    """单个媒体的工作目录：<root>/<item_id>/（分块 + 成品都在此）。"""
    d = os.path.join(item_root(), str(int(item_id)))
    os.makedirs(d, exist_ok=True)
    return d


def chunk_dir(item_id):
    """分块暂存目录。"""
    d = os.path.join(item_dir(item_id), "chunks")
    os.makedirs(d, exist_ok=True)
    return d


def chunk_path(item_id, part_number):
    """某分块的落盘路径（按 part_number 排序即自然顺序）。"""
    return os.path.join(chunk_dir(item_id), f"{int(part_number):08d}.part")


def final_path(item_id, filename):
    """组装后的成品路径（磁盘名用安全随机名，防路径穿越）。"""
    ext = os.path.splitext(str(filename))[1].lower()
    ext = re.sub(r"[^0-9a-z.]", "", ext)[:12]
    name = secrets.token_hex(16) + ext
    return os.path.join(item_dir(item_id), name)


def item_local_path(item):
    """由 DB 的 local_file 相对路径还原绝对路径（无则 None）。"""
    rel = item["local_file"]
    if not rel:
        return None
    return os.path.join(item_root(), rel)


# ---------------------------------------------------------------- 加密
def _fernet():
    cfg = current_app.config
    if not cfg.get("MEDIA_SPOOL_ENCRYPT"):
        return None
    if not _FERNET_OK:
        raise MediaFileError("MEDIA_SPOOL_ENCRYPT=1 但缺少 cryptography，请安装")
    key = cfg.get("MEDIA_FERNET_KEY") or ""
    if not key:
        key_file = os.path.join(item_root(), "media_fernet.key")
        if os.path.exists(key_file):
            key = open(key_file, encoding="utf-8").read().strip()
        else:
            key = Fernet.generate_key().decode("utf-8")
            try:
                with open(key_file, "w", encoding="utf-8") as fh:
                    fh.write(key)
            except OSError:
                raise MediaFileError("无法生成加密密钥文件，请显式设置 MEDIA_FERNET_KEY")
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise MediaFileError("MEDIA_FERNET_KEY 非法（需为 Fernet 密钥格式）") from exc


def save_chunk(item_id, part_number, data):
    """把一段分块字节写入本地（按配置加密），返回写入字节数。"""
    f = _fernet()
    payload = f.encrypt(data) if f else data
    path = chunk_path(item_id, part_number)
    tmp = path + f".{secrets.token_hex(4)}.tmp"
    with open(tmp, "wb") as fh:
        fh.write(payload)
    os.replace(tmp, path)          # 原子写：中途崩溃不会留下半个分块
    return len(data)


def load_chunk(item_id, part_number):
    """读取一个分块（自动解密）。"""
    f = _fernet()
    with open(chunk_path(item_id, part_number), "rb") as fh:
        data = fh.read()
    return f.decrypt(data) if f else data


def list_chunk_numbers(item_id):
    """已落盘分块的 part_number 升序列表（续传校验/组装用）。"""
    d = chunk_dir(item_id)
    nums = []
    for name in os.listdir(d):
        if name.endswith(".part"):
            try:
                nums.append(int(name.split(".", 1)[0]))
            except ValueError:
                continue
    nums.sort()
    return nums


def count_chunks_bytes(item_id):
    """已落盘分块的数量与总字节数。"""
    total = 0
    for num in list_chunk_numbers(item_id):
        with open(chunk_path(item_id, num), "rb") as fh:
            payload = fh.read()
        f = _fernet()
        total += len(f.decrypt(payload) if f else payload)
    return len(list_chunk_numbers(item_id)), total


def assemble(item_id, filename):
    """按 part_number 顺序拼接分块 → 成品文件，返回 (路径, sha256)。"""
    nums = list_chunk_numbers(item_id)
    if not nums:
        raise MediaFileError("没有任何分块，无法组装")
    out = final_path(item_id, filename)
    digest = hashlib.sha256()
    f = _fernet()
    with open(out, "wb") as fh:
        for num in nums:
            with open(chunk_path(item_id, num), "rb") as cfh:
                data = cfh.read()
            if f:
                data = f.decrypt(data)
            fh.write(data)
            digest.update(data)
    return out, digest.hexdigest()


def compute_sha256(path):
    """流式计算文件 SHA-256（内存安全，大文件可用）。"""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def cleanup_item(item_id):
    """删除某媒体的整个工作目录（分块 + 成品）。"""
    import shutil
    d = item_dir(item_id)
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)
