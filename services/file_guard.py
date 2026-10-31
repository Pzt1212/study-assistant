# -*- coding: utf-8 -*-
"""上传文件的统一安全守卫。

- 存储文件名白名单：只允许形如 <字母数字开头> 的纯文件名（uuid 生成），
  杜绝 stored=../../x 这类穿越；
- 提供统一的删除入口：normpath + 确认仍在上传目录内 + 容错。
所有涉及 stored_filename 的路径解析 / 文件删除都必须经由此模块。
"""
import os
import re

_SAFE_STORED_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")


def is_safe_stored_filename(name):
    """判断存储文件名是否安全（必须是不含路径分隔符的纯文件名）。"""
    if not name or not isinstance(name, str):
        return False
    if len(name) > 128:
        return False
    if os.path.basename(name) != name:  # 含 / \ 或目录成分
        return False
    return bool(_SAFE_STORED_RE.match(name))


def uploaded_file_path(upload_dir, stored_filename):
    """把存储文件名解析为绝对路径；非法或越界返回 None。"""
    if not is_safe_stored_filename(stored_filename):
        return None
    base = os.path.normpath(upload_dir)
    path = os.path.normpath(os.path.join(base, stored_filename))
    # 双保险：确认仍在上传目录内
    if os.path.commonpath([base, path]) != base:
        return None
    return path


def remove_uploaded_file(upload_dir, stored_filename):
    """安全删除上传文件：非法名直接忽略；文件不存在视为成功；OSError 吞掉。

    返回 True 表示“无需处理/已删除”，False 仅用于极端非法目录情形。
    """
    path = uploaded_file_path(upload_dir, stored_filename)
    if path is None:
        return False
    try:
        if os.path.exists(path):
            os.remove(path)
        return True
    except OSError:
        return False
