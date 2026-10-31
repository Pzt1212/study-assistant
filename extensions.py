# -*- coding: utf-8 -*-
"""扩展初始化模块。

将 Flask 生态的第三方扩展统一在此实例化，避免循环导入，
遵循 "扩展分离" 的 Flask 应用工厂最佳实践。
"""
from flask import flash, jsonify, redirect, request, url_for
from flask_login import LoginManager

# 登录管理扩展：负责会话管理、登录保护、记住我等功能
login_manager = LoginManager()
# 未登录访问受保护页面时，跳转到登录视图（路由名 auth.login）
login_manager.login_view = "auth.login"
# 未登录跳转时的提示信息
login_manager.login_message = "请先登录后再访问该页面。"
login_manager.login_message_category = "warning"


@login_manager.unauthorized_handler
def _unauthorized():
    """未登录处理：/media/api 等 JSON 接口返回 401 JSON，页面保持跳转登录。"""
    if request.path.startswith("/media/api/"):
        return jsonify(ok=False, error="请先登录"), 401
    # 与 Flask-Login 默认行为一致：flash 提示后跳登录页并带回 next
    flash(login_manager.login_message, login_manager.login_message_category)
    return redirect(url_for(login_manager.login_view, next=request.path))
