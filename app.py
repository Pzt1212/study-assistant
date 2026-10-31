# -*- coding: utf-8 -*-
"""学习助手 - 应用入口与应用工厂。

使用 Flask 应用工厂模式（create_app）：
- 集中注册扩展（数据库、登录）
- 注册所有功能蓝图
- 启动时自动建表、自动生成占位音乐

运行方式：
    python app.py
然后浏览器访问 http://127.0.0.1:5000
"""
import os

import click
from flask import Flask

from config import Config
from db import init_db
from extensions import login_manager
from models import get_user_by_id, get_user_by_username, set_user_admin


def create_app(config_class=Config, initialize_db=True):
    """创建并配置 Flask 应用实例。"""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # 媒体库相关配置缺省补齐：旧的自定义配置类（如测试 TestConfig）未继承
    # Config 的新增键，这里统一以 Config 里的默认值兜底，保证新蓝图可用。
    from config import Config as _DefaultConfig

    for _key in dir(_DefaultConfig):
        if _key.isupper() and (_key.startswith("MEDIA_") or _key.startswith("R2_")):
            app.config.setdefault(_key, getattr(_DefaultConfig, _key))

    # 生产环境（APP_ENV=production）必须显式提供随机会话密钥，否则拒绝启动，
    # 避免使用内置默认 SECRET_KEY 被伪造会话。
    if app.config.get("APP_ENV", "development") == "production":
        if not os.environ.get("SECRET_KEY"):
            raise RuntimeError(
                "生产环境必须设置环境变量 SECRET_KEY（随机值），拒绝使用默认密钥启动。"
            )

    # 位于反向代理 / 内网穿透之后时信任 X-Forwarded-* 头（见 config.TRUST_PROXY_HEADERS）
    if app.config.get("TRUST_PROXY_HEADERS"):
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # ---- 初始化数据库：确保目录存在并自动建表（可由入口选择关闭） ----
    # 说明：模块级 app = create_app(initialize_db=False) 避免「import 即建库」的副作用；
    # 真正启动服务的入口（tools/run_server.py / 测试）默认 initialize_db=True。
    if initialize_db:
        init_db(app)

    # ---- 配置 Flask-Login ----
    login_manager.init_app(app)

    # 用户加载器：根据会话中的用户 id 加载用户对象
    @login_manager.user_loader
    def load_user(user_id):
        return get_user_by_id(int(user_id))

    # ---- CSRF 防护（全站非安全方法校验会话令牌） ----
    from services.csrf import install as install_csrf

    install_csrf(app)

    # ---- 媒体库异步任务（默认内置线程队列；celery 引擎由独立 worker 消费） ----
    from services import tasks as media_tasks

    media_tasks.init(app)

    # ---- 注册蓝图（每个功能模块独立文件） ----
    from blueprints.auth import auth
    from blueprints.main import main
    from blueprints.pomodoro import pomodoro
    from blueprints.timer import timer
    from blueprints.music import music
    from blueprints.notes import notes
    from blueprints.ocr import ocr
    from blueprints.questions import questions
    from blueprints.search import search
    from blueprints.admin import admin
    from blueprints.question_bank import question_bank
    from blueprints.forum import forum
    from blueprints.video import video
    from blueprints.media import media as media_bp

    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(pomodoro)
    app.register_blueprint(timer)
    app.register_blueprint(music)
    app.register_blueprint(notes)
    app.register_blueprint(ocr)
    app.register_blueprint(questions)
    app.register_blueprint(search)
    app.register_blueprint(admin)
    app.register_blueprint(question_bank)
    app.register_blueprint(forum)
    app.register_blueprint(video)
    app.register_blueprint(media_bp)

    # ---- 模板全局：渲染用户头像（自定义头像兜底首字母） ----
    # 需引入 markupsafe 以保证 attr 转义
    from markupsafe import Markup, escape as _escape

    def _avatar_html(user, size=28):
        """返回一个圆形头像 HTML：图片/emoji/首字母。"""
        try:
            av = getattr(user, "avatar", None)
            letter = (user.username[:1] or "?").upper()
        except Exception:
            av, letter = None, "?"
        size = int(size) or 28
        radius = size + 4
        if isinstance(av, dict) and av.get("value"):
            if av.get("kind") == "image":
                return Markup(
                    f'<span class="user-avatar" style="width:{size}px;height:{size}px;'
                    f'border-radius:{radius}px;overflow:hidden">'
                    f'<img src="{_escape(av["value"])}" alt="" '
                    f'style="width:100%;height:100%;object-fit:cover;display:block"></span>'
                )
            color = _escape(av.get("color") or "#d9dde3")
            val = _escape(av.get("value"))
            return Markup(
                f'<span class="user-avatar" style="width:{size}px;height:{size}px;'
                f'border-radius:{radius}px;background:{color};'
                f'font-size:{size * 0.58}px">{val}</span>'
            )
        # 兜底：用户名首字母（中性浅灰底 + 深字）
        return Markup(
            f'<span class="user-avatar user-avatar-letter" '
            f'style="width:{size}px;height:{size}px;border-radius:{radius}px;'
            f'font-size:{size * 0.52}px">{_escape(letter)}</span>'
        )

    @app.context_processor
    def _inject_avatar():
        from models import ROLE_LABELS

        def role_label(role):
            return ROLE_LABELS.get(int(role or 0), ROLE_LABELS[0])

        return {"avatar_html": _avatar_html, "role_label": role_label}

    # ---- 简单错误页提示 ----
    @app.errorhandler(404)
    def not_found(_error):
        return "<h3>404 - 页面不存在</h3><p><a href='/'>返回首页</a></p>", 404

    @app.errorhandler(403)
    def forbidden(_error):
        return "<h3>403 - 无权访问</h3><p>需要管理员权限，<a href='/'>返回首页</a></p>", 403

    # ---- Flask CLI 命令 ----
    # 用法：flask --app app create-admin <用户名>
    @app.cli.command("create-admin")
    @click.argument("username")
    def create_admin_command(username):
        """把指定用户设为管理员（需先注册该用户）。"""
        # CLI 不经 HTTP 请求，模块级实例关闭了建库，这里显式初始化
        from db import init_db
        init_db(app)
        user = get_user_by_username(username)
        if not user:
            click.echo(f"错误：用户「{username}」不存在，请先注册。")
            raise SystemExit(1)
        set_user_admin(user.id, True)
        click.echo(f"已将用户「{username}」设为管理员。")

    return app


# 模块级应用实例（供 gunicorn / flask run 等使用）。
# initialize_db=False：避免 import app 即建库建表；由启动入口负责建库。
app = create_app(initialize_db=False)


if __name__ == "__main__":
    # 启动参数来自 config.APP_HOST / APP_PORT（可用环境变量 APP_HOST / APP_PORT 覆盖）。
    # 后台脚本（start_server.bat / tools/run_server.py）会设置 FLASK_DEBUG=0，
    # 日常 `python app.py` 仍保持 debug=True 便于开发。
    # 模块级实例关闭了建库，直接运行本文件时先显式建库。
    from db import init_db

    init_db(app)
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(
        host=app.config["APP_HOST"],
        port=app.config["APP_PORT"],
        debug=debug,
        threaded=True,
    )
