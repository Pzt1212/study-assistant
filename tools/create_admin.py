# -*- coding: utf-8 -*-
"""管理员账户管理工具。

用法：
    python tools/create_admin.py                          # 创建/重置 admin（随机强密码，仅打印一次）
    python tools/create_admin.py --username boss          # 指定用户名
    python tools/create_admin.py --password 你的密码      # 指定密码（代替随机生成）
    python tools/create_admin.py --username boss --password xxx --email b@e.com

行为：
- 用户名不存在 → 创建并把 is_admin 置 1；
- 用户名已存在 → 提升为管理员（不覆盖原密码，除非传 --password）；
- 创建后做一次自检：密码哈希校验通过才提示成功。

安全提示：随机密码只在终端打印一次，请立即记牢；
发布到公网后建议更换密码并修改 SECRET_KEY。
"""
import argparse
import os
import secrets
import string
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import create_app  # noqa: E402
from models import (  # noqa: E402
    create_user,
    email_exists,
    get_user_by_username,
    set_user_admin,
)
from blueprints.auth import hash_password  # noqa: E402

DEFAULT_USERNAME = "admin"
DEFAULT_EMAIL = "admin@localhost.local"


def random_password(length=14):
    """生成不含易混淆字符（0O1lI）的随机密码。"""
    alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%^&*-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def main():
    parser = argparse.ArgumentParser(description="创建 / 提升管理员账户")
    parser.add_argument("--username", default=DEFAULT_USERNAME,
                        help=f"用户名（默认 {DEFAULT_USERNAME}）")
    parser.add_argument("--password", default="", help="指定密码（缺省随机生成）")
    parser.add_argument("--email", default=DEFAULT_EMAIL, help="邮箱")
    args = parser.parse_args()

    username = args.username.strip()
    email = (args.email or "").strip().lower() or DEFAULT_EMAIL
    password = args.password or random_password()

    if len(username) < 2 or len(username) > 30:
        print("用户名长度需在 2~30 个字符之间。", file=sys.stderr)
        return 1
    if len(password) < 6:
        print("密码长度至少 6 个字符。", file=sys.stderr)
        return 1

    app = create_app()
    with app.app_context():
        user = get_user_by_username(username)
        created = user is None

        if created:
            # 邮箱冲突时自动换一个不冲突的本地邮箱
            candidate = email
            n = 0
            while email_exists(candidate):
                n += 1
                candidate = f"{username}{n}@local.admin"
            create_user(username, candidate, hash_password(password))
            user = get_user_by_username(username)
            email = candidate
        elif args.password:
            # 已存在且显式传了 --password：重置密码
            from db import get_db
            db = get_db()
            db.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (hash_password(password), user.id))
            db.commit()
            # 重新读取用户，确保自检用的是新哈希（旧对象快照会误判失败）
            user = get_user_by_username(username)

        # 确保管理员身份（已存在但非管理员也会被提升）
        set_user_admin(user.id, True)

        # ---- 自检：确认新密码可校验通过 ----
        # 以数据库中最新哈希为准（user 可能来自上述重置/提升前的快照）
        fresh = get_user_by_username(username)
        hash_to_check = fresh.password_hash if fresh is not None else user.password_hash
        import bcrypt
        if not bcrypt.checkpw(password.encode("utf-8"),
                              hash_to_check.encode("utf-8")):
            print("自检失败：密码哈希校验不通过。", file=sys.stderr)
            return 1

    print("=" * 56)
    print("管理员账户就绪 ✅")
    print("=" * 56)
    print(f"  用户名  ：{username}")
    print(f"  密码    ：{password}")
    print(f"  邮箱    ：{email}")
    print(f"  是否新建：{'是' if created else '否（已提升为管理员）'}")
    print("-" * 56)
    print("  登录地址：http://127.0.0.1:5000/login")
    print("  后台地址：http://127.0.0.1:5000/admin")
    print("-" * 56)
    print("  ⚠️  随机密码只在本次显示，请立即保存；")
    print("      公网发布后请及时更换密码并设置 SECRET_KEY。")
    print("=" * 56)
    return 0


if __name__ == "__main__":
    sys.exit(main())
