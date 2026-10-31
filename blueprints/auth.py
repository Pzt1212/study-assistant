# -*- coding: utf-8 -*-
"""认证模块蓝图：注册 / 登录 / 退出。

密码使用 bcrypt 单向哈希存储，绝不明文保存。
登录状态由 Flask-Login 管理，提供 @login_required 保护。
"""
import bcrypt
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from models import (
    create_user,
    email_exists,
    get_user_by_email,
    get_user_by_username,
    username_exists,
)

auth = Blueprint("auth", __name__, url_prefix="", template_folder="../templates")


# ---------- 密码工具 ----------
def hash_password(password: str) -> str:
    """对明文密码进行 bcrypt 加盐哈希，返回可存储的字符串。"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(password_hash: str, password: str) -> bool:
    """校验明文密码是否与存储的哈希值匹配。"""
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, Exception):
        return False


# ---------- 注册 ----------
@auth.route("/register", methods=["GET", "POST"])
def register():
    """用户注册。

    GET  — 显示注册表单
    POST — 处理注册请求，校验 → 创建 → 重定向到登录页
    """
    # 已登录用户无需再注册，直接跳首页
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    error = None
    form_data = {"username": "", "email": ""}

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        form_data = {"username": username, "email": email}

        # ---- 校验 ----
        if not username or not email or not password or not confirm:
            error = "所有字段均为必填。"
        elif len(username) < 2 or len(username) > 30:
            error = "用户名长度需在 2~30 个字符之间。"
        elif "@" not in email or "." not in email:
            error = "邮箱格式不正确。"
        elif len(password) < 6:
            error = "密码长度至少 6 个字符。"
        elif password != confirm:
            error = "两次输入的密码不一致。"
        elif username_exists(username):
            error = "该用户名已被注册，请换一个。"
        elif email_exists(email):
            error = "该邮箱已被注册，请换一个。"
        else:
            # 通过校验 → 创建用户
            create_user(username, email, hash_password(password))
            flash("注册成功！请登录。", "success")
            return redirect(url_for("auth.login"))

        if error:
            flash(error, "error")

    return render_template("auth/register.html", form=form_data)


# ---------- 登录 ----------
@auth.route("/login", methods=["GET", "POST"])
def login():
    """用户登录。

    GET  — 显示登录表单
    POST — 验证凭据，登录成功跳转原目标页面或首页
    """
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"

        if not username or not password:
            flash("用户名和密码不能为空。", "error")
            return render_template("auth/login.html")

        # 允许用用户名或邮箱登录
        user = get_user_by_username(username) or get_user_by_email(username.lower())

        if user and check_password(user.password_hash, password):
            login_user(user, remember=remember)
            flash(f"欢迎回来，{user.username}！", "success")

            # 安全跳转：仅允许同站相对路径
            next_page = request.args.get("next", "")
            if next_page and next_page.startswith("/") and not next_page.startswith("//"):
                return redirect(next_page)
            return redirect(url_for("main.dashboard"))

        flash("用户名或密码错误。", "error")

    return render_template("auth/login.html")


# ---------- 退出 ----------
@auth.route("/logout", methods=["POST"])
@login_required
def logout():
    """退出登录，清空会话，重定向到登录页。

    仅允许 POST：GET 登出可被跨站 <img> 等方式触发，见代码审查 CSRF 项。
    """
    logout_user()
    flash("已退出登录。", "info")
    return redirect(url_for("auth.login"))