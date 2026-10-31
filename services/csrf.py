# -*- coding: utf-8 -*-
"""轻量 CSRF 防护（无第三方依赖）。

方案：
- 登录态会话中维护一个随机会话令牌 session['_csrf']；
- 模板通过全局函数 csrf_token() 取令牌（<head> meta / 表单 hidden）；
- 所有非安全方法（POST/PUT/DELETE…）都要求令牌一致，来源可以是：
    * 表单字段 csrf_token（HTML 表单）
    * 请求头 X-CSRFToken（fetch / XHR）
- 校验失败返回 400。
- 通过配置 CSRF_ENABLED 可整体开关（测试环境关闭）。
"""
import hmac
import secrets

from flask import abort, request, session

_SAFE_METHODS = ("GET", "HEAD", "OPTIONS", "TRACE")


def install(app):
    """注册 CSRF 钩子到 Flask 应用。"""
    app.config.setdefault("CSRF_ENABLED", True)

    def _ensure_token():
        if not session.get("_csrf"):
            session["_csrf"] = secrets.token_urlsafe(32)

    @app.before_request
    def _csrf_guard():
        if not app.config.get("CSRF_ENABLED", True):
            return None
        _ensure_token()
        if request.method in _SAFE_METHODS:
            return None
        expected = session.get("_csrf", "")
        # 表单字段或请求头都可携带令牌
        token = request.form.get("csrf_token") or ""
        if not token:
            token = request.headers.get("X-CSRFToken", "") or ""
        if not token or not hmac.compare_digest(str(token), str(expected)):
            abort(400, description="CSRF 校验失败，请刷新页面后重试。")
        return None

    @app.context_processor
    def _inject_csrf():
        _ensure_token()
        return {"csrf_token": lambda: session.get("_csrf", "")}
