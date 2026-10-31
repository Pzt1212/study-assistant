# -*- coding: utf-8 -*-
"""学习论坛蓝图（/forum）。

- 主题帖：发帖、列表（含回帖数）、详情、删除（作者本人或管理员）
- 回帖：发表、删除（作者本人或管理员）
"""
from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from models import (
    create_forum_post,
    create_forum_reply,
    delete_forum_post,
    delete_forum_reply,
    get_forum_post,
    get_forum_reply,
    list_forum_posts,
    list_forum_replies,
)

forum = Blueprint("forum", __name__, template_folder="../templates")


def _can_manage(user_id):
    return user_id == current_user.id or current_user.is_admin


@forum.route("/forum")
@login_required
def index():
    """帖子列表，支持 ?q= 关键字。"""
    keyword = request.args.get("q", "").strip()
    posts = list_forum_posts(keyword=keyword or None)
    return render_template("forum/index.html", posts=posts, keyword=keyword)


@forum.route("/forum/new", methods=["GET", "POST"])
@login_required
def new():
    """发布新主题。"""
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        if not title:
            flash("标题不能为空。", "error")
            return render_template("forum/new.html", title=title, content=content)
        if not content:
            flash("内容不能为空。", "error")
            return render_template("forum/new.html", title=title, content=content)
        post_id = create_forum_post(current_user.id, title, content)
        flash("发布成功。", "success")
        return redirect(url_for("forum.detail", post_id=post_id))
    return render_template("forum/new.html", title="", content="")


@forum.route("/forum/<int:post_id>", methods=["GET", "POST"])
@login_required
def detail(post_id):
    """帖子详情 + 回帖。"""
    post = get_forum_post(post_id)
    if not post:
        abort(404)

    if request.method == "POST":
        content = request.form.get("content", "").strip()
        if not content:
            flash("回帖内容不能为空。", "error")
            return redirect(url_for("forum.detail", post_id=post_id))
        create_forum_reply(current_user.id, post_id, content)
        flash("回复成功。", "success")
        return redirect(url_for("forum.detail", post_id=post_id) + "#replies")

    replies = list_forum_replies(post_id)
    return render_template("forum/detail.html", post=post, replies=replies)


@forum.route("/forum/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id):
    """删除帖子（作者或管理员）。"""
    post = get_forum_post(post_id)
    if not post:
        abort(404)
    if not _can_manage(post["user_id"]):
        abort(403)
    delete_forum_post(post_id)
    flash("帖子已删除。", "info")
    return redirect(url_for("forum.index"))


@forum.route("/forum/reply/<int:reply_id>/delete", methods=["POST"])
@login_required
def delete_reply(reply_id):
    """删除回帖（作者或管理员）。"""
    reply = get_forum_reply(reply_id)
    if not reply:
        abort(404)
    if not _can_manage(reply["user_id"]):
        abort(403)
    delete_forum_reply(reply_id)
    flash("回复已删除。", "info")
    # 回到帖子并定位回帖区
    from models import get_forum_post
    return redirect(url_for("forum.detail", post_id=reply["post_id"]) + "#replies")
