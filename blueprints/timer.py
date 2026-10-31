# -*- coding: utf-8 -*-
"""计时器蓝图。

秒表（正计时）与倒计时两种模式，全部逻辑在前端 JS 中完成。
后端仅渲染页面模板，不记录数据。
"""
from flask import Blueprint, render_template
from flask_login import login_required

timer = Blueprint("timer", __name__, template_folder="../templates")


@timer.route("/timer")
@login_required
def index():
    """计时器页面。"""
    return render_template("timer.html")