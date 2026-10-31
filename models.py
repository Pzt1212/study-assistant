# -*- coding: utf-8 -*-
"""数据访问层。

所有与数据库交互的查询/写入逻辑都集中在当前模块，路由层不直接写 SQL。
这样做到「表现层与数据层分离」，便于测试、维护与二次开发。
"""
from datetime import datetime, timedelta
import json

from flask_login import UserMixin

from db import get_db


# ============================================================
# 角色层级（用户权限分四层）
# ============================================================
ROLE_USER = 0    # 普通用户
ROLE_MOD = 1     # 协管：全站内容治理（题库/笔记删除、论坛删帖）
ROLE_ADMIN = 2   # 管理员：内容 + 数据概览 + 用户列表 / 删除普通用户 / OCR 状态
ROLE_SUPER = 3   # 超级管理员：管理员能力 + 角色任免
ROLE_LABELS = {ROLE_USER: "普通用户", ROLE_MOD: "协管",
               ROLE_ADMIN: "管理员", ROLE_SUPER: "超级管理员"}


# ============================================================
# 工具函数
# ============================================================
def _now():
    """返回当前本地时间字符串（格式 YYYY-MM-DD HH:MM:SS）。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today():
    """返回当前本地日期字符串（格式 YYYY-MM-DD）。"""
    return datetime.now().strftime("%Y-%m-%d")


def _escape_like(keyword):
    """转义 LIKE 模式中的特殊字符，避免用户输入 % _ 造成意外通配。"""
    return (
        keyword.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


# ============================================================
# 用户 (User)
# ============================================================
class User(UserMixin):
    """Flask-Login 所需的用户对象。

    从数据库行构造，提供 is_authenticated / get_id 等接口。
    """

    def __init__(self, row):
        self.id = row["id"]
        self.username = row["username"]
        self.email = row["email"]
        self.password_hash = row["password_hash"]
        # 四层权限：0 普通 / 1 协管 / 2 管理员 / 3 超级管理员
        if "role" in row.keys():
            self.role = int(row["role"] or 0)
        else:
            # 旧查询未带 role 列时回退：is_admin=1 的历史账号按最高层 3 处理
            self.role = 3 if int(row["is_admin"] or 0) else 0
        self.is_admin = self.role >= 1
        # avatar：自定义头像（JSON 字符串），防御性解析
        self.avatar = None
        if "avatar" in row.keys() and row["avatar"]:
            try:
                self.avatar = json.loads(row["avatar"])
            except (TypeError, ValueError):
                self.avatar = None
        self.created_at = row["created_at"]

    @property
    def role_name(self):
        """角色的显示名称（普通用户返回空串，界面按层展示）。"""
        return {1: "协管", 2: "管理员", 3: "超级管理员"}.get(self.role, "")

    @property
    def is_super(self):
        return self.role >= 3

    @staticmethod
    def from_db(user_id):
        """按主键加载用户（供 Flask-Login user_loader 使用）。"""
        row = get_user_by_id(user_id)
        return row


def create_user(username, email, password_hash):
    """创建新用户，返回新用户的 User 对象。"""
    db = get_db()
    db.execute(
        "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (username, email, password_hash, _now()),
    )
    db.commit()
    return get_user_by_username(username)


def update_user_avatar(user_id, avatar_payload):
    """保存用户自定义头像（avatar_payload 为 dict 或 None，内部序列化存储）。"""
    db = get_db()
    db.execute(
        "UPDATE users SET avatar = ? WHERE id = ?",
        (json.dumps(avatar_payload, ensure_ascii=False) if avatar_payload else None, user_id),
    )
    db.commit()


def get_user_by_id(user_id):
    """按主键查询用户。"""
    row = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return User(row) if row else None


def get_user_by_username(username):
    """按用户名查询用户。"""
    row = get_db().execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    return User(row) if row else None


def get_user_by_email(email):
    """按邮箱查询用户。"""
    row = get_db().execute(
        "SELECT * FROM users WHERE email = ?", (email,)
    ).fetchone()
    return User(row) if row else None


def username_exists(username):
    """判断用户名是否已被占用（注册校验用）。"""
    row = get_db().execute(
        "SELECT 1 FROM users WHERE username = ?", (username,)
    ).fetchone()
    return row is not None


def email_exists(email):
    """判断邮箱是否已被占用（注册校验用）。"""
    row = get_db().execute(
        "SELECT 1 FROM users WHERE email = ?", (email,)
    ).fetchone()
    return row is not None


# ============================================================
# 题目 (Question) 与答题统计
# ============================================================
def create_question(user_id, subject, content, option_a, option_b, option_c,
                    option_d, answer, analysis, topic=None, question_type=None,
                    difficulty=None, grade=None, score=None):
    """新增一道题目，返回新题目 id。

    topic / question_type / difficulty / grade / score 为可选的分类与刷题扩展字段；
    question_type 为空时按历史习惯视为选择题（刷题/列表统一归一）。
    """
    db = get_db()
    cur = db.execute(
        """INSERT INTO questions
           (user_id, subject, topic, grade, question_type, difficulty, score,
            content, option_a, option_b, option_c, option_d,
            answer, analysis, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, subject, topic, grade,
         (question_type or "").strip() or None, (difficulty or "").strip() or None,
         score,
         content, option_a, option_b, option_c, option_d,
         answer, analysis, _now(), _now()),
    )
    db.commit()
    return cur.lastrowid


def get_question(question_id, user_id):
    """按 id 查询当前用户的一道题目（带归属校验）。"""
    return get_db().execute(
        "SELECT * FROM questions WHERE id = ? AND user_id = ?",
        (question_id, user_id),
    ).fetchone()


def update_question(question_id, user_id, subject, content, option_a, option_b,
                    option_c, option_d, answer, analysis, topic=None,
                    question_type=None, difficulty=None, grade=None, score=None):
    """更新一道题目（含分类 / 题型 / 难度等扩展字段）。"""
    db = get_db()
    db.execute(
        """UPDATE questions SET subject=?, topic=?, grade=?, question_type=?,
           difficulty=?, score=?, content=?, option_a=?, option_b=?,
           option_c=?, option_d=?, answer=?, analysis=?, updated_at=?
           WHERE id=? AND user_id=?""",
        (subject, topic, grade,
         (question_type or "").strip() or None, (difficulty or "").strip() or None,
         score,
         content, option_a, option_b, option_c, option_d, answer,
         analysis, _now(), question_id, user_id),
    )
    db.commit()


def set_question_image(question_id, image):
    """写入题图路径（image 为相对 /static 的 URL，如 /static/img/q/12.svg；None 清除）。"""
    db = get_db()
    db.execute("UPDATE questions SET image = ? WHERE id = ?", (image, question_id))
    db.commit()


def delete_question(question_id, user_id):
    """删除当前用户的一道题目（关联答题记录级联删除）。"""
    db = get_db()
    db.execute(
        "DELETE FROM questions WHERE id = ? AND user_id = ?",
        (question_id, user_id),
    )
    db.commit()


def list_questions(user_id, subject=None, keyword=None):
    """按科目/关键字筛选当前用户的题目列表（新题在前）。"""
    sql = "SELECT * FROM questions WHERE user_id = ?"
    params = [user_id]
    if subject:
        sql += " AND subject = ?"
        params.append(subject)
    if keyword:
        kw = _escape_like(keyword)
        sql += """ AND (content LIKE ? ESCAPE '\\' OR subject LIKE ? ESCAPE '\\'
                    OR analysis LIKE ? ESCAPE '\\')"""
        params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])
    sql += " ORDER BY id DESC"
    return get_db().execute(sql, params).fetchall()


def list_subjects(user_id):
    """返回当前用户的所有科目（含每科题数），按题数倒序。"""
    return get_db().execute(
        """SELECT subject, COUNT(*) AS count FROM questions
           WHERE user_id = ? GROUP BY subject ORDER BY count DESC, subject ASC""",
        (user_id,),
    ).fetchall()


def count_questions(user_id):
    """统计当前用户的题目总数。"""
    row = get_db().execute(
        "SELECT COUNT(*) AS c FROM questions WHERE user_id = ?", (user_id,)
    ).fetchone()
    return row["c"]


def get_random_question(user_id, question_type=None, subject=None, difficulty=None):
    """随机抽取当前用户的一道题目（刷题模式）。

    :param user_id: 用户 id
    :param question_type: 题型过滤，取值说明：
        - None / "" / "全部"：全题型混合抽取（默认）
        - "选择题" / "填空题" / "解答题"：只抽指定题型
        说明：用户在表单手工新增的题目没有设置 question_type（存 NULL），
        列表页默认把它们当作选择题展示，因此抽「选择题」时也纳入这类题目。
    :param subject: 学科过滤（None / "" = 全部学科）
    :param difficulty: 难度过滤（None / "" = 全部难度；取值如 简单/中等/较难）
    """
    params = [user_id]
    sql = "SELECT * FROM questions WHERE user_id = ?"
    if subject:
        sql += " AND subject = ?"
        params.append(subject)
    if difficulty:
        sql += " AND difficulty = ?"
        params.append(difficulty)
    qtype = (question_type or "").strip()
    if qtype and qtype != "全部":
        if qtype == "选择题":
            # 选择题 = 明确标注选择题 + 手工添加未标注题型的题目（NULL）
            sql += " AND (question_type = '选择题' OR question_type IS NULL)"
        else:
            sql += " AND question_type = ?"
            params.append(qtype)
    sql += " ORDER BY RANDOM() LIMIT 1"
    return get_db().execute(sql, params).fetchone()


def record_answer(user_id, question_id, user_answer, is_correct, score=0):
    """记录一次作答结果（供答题统计使用）。

    :param score: 本题得分（0~满分）。
        - 选择题 / 填空题：答对得满分、答错得 0 分；
        - 解答题：用户在参考评分标准后自评的得分。
    """
    db = get_db()
    db.execute(
        """INSERT INTO answer_records
           (user_id, question_id, user_answer, is_correct, score, answered_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, question_id, user_answer, 1 if is_correct else 0,
         int(score or 0), _now()),
    )
    db.commit()


def create_question_detailed(user_id, subject, content, answer,
                             question_type="选择题", difficulty="中等",
                             topic="", grade="初中", score=None,
                             analysis="", option_a="", option_b="",
                             option_c="", option_d="", step_rules=None):
    """创建一道「完整字段」的题目（支持题型 / 难度 / 知识点 / 分值 / 评分标准）。

    与 create_question 的区别：create_question 只写旧版表单字段（用于
    列表 / 编辑页手工录入），本函数用于题库生成器与测试直接构造
    带 topic / question_type / difficulty / score / step_rules 的题目。

    :param step_rules: 解答题的评分标准，dict（如 {"列对已知条件": 2, ...}），
                       内部会序列化为 JSON 字符串存储。
    :return: 新题目 id
    """
    db = get_db()
    cur = db.execute(
        """INSERT INTO questions
           (user_id, subject, topic, grade, question_type, difficulty, score,
            content, option_a, option_b, option_c, option_d, answer,
            analysis, step_rules, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, subject, topic, grade, question_type, difficulty, score,
         content, option_a, option_b, option_c, option_d, answer,
         analysis, json.dumps(step_rules, ensure_ascii=False)
         if step_rules else None,
         _now(), _now()),
    )
    db.commit()
    return cur.lastrowid


def get_quiz_stats(user_id):
    """统计答题情况：总题数 / 正确 / 错误 / 正确率。"""
    row = get_db().execute(
        """SELECT COUNT(*) AS total,
                  SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct
           FROM answer_records WHERE user_id = ?""",
        (user_id,),
    ).fetchone()
    total = row["total"] or 0
    correct = row["correct"] or 0
    wrong = total - correct
    accuracy = round(correct / total * 100, 1) if total else 0.0
    return {"total": total, "correct": correct, "wrong": wrong, "accuracy": accuracy}


# ============================================================
# 笔记 (Note)
# ============================================================
def create_note(user_id, title, content, source_filename="", stored_filename="",
                file_type="text"):
    """创建一篇笔记，返回新笔记 id。"""
    db = get_db()
    cur = db.execute(
        """INSERT INTO notes
           (user_id, title, content, source_filename, stored_filename,
            file_type, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, title, content, source_filename, stored_filename, file_type,
         _now(), _now()),
    )
    db.commit()
    return cur.lastrowid


def get_note(note_id, user_id):
    """按 id 查询当前用户的一篇笔记（带归属校验）。"""
    return get_db().execute(
        "SELECT * FROM notes WHERE id = ? AND user_id = ?",
        (note_id, user_id),
    ).fetchone()


def update_note(note_id, user_id, title, content, file_type=None):
    """更新笔记标题与正文（可选更新 file_type，供手写 SVG 笔记切换类型）。"""
    db = get_db()
    db.execute(
        "UPDATE notes SET title=?, content=?, updated_at=? WHERE id=? AND user_id=?",
        (title, content, _now(), note_id, user_id),
    )
    if file_type:
        db.execute(
            "UPDATE notes SET file_type=?, updated_at=? WHERE id=? AND user_id=?",
            (file_type, _now(), note_id, user_id),
        )
    db.commit()


def delete_note(note_id, user_id):
    """删除当前用户的一篇笔记。"""
    db = get_db()
    db.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id))
    db.commit()


def get_note_by_stored_filename(stored_filename):
    """按上传存储文件名反查笔记（用于上传文件访问的归属校验）。"""
    return get_db().execute(
        "SELECT id, user_id, title FROM notes WHERE stored_filename = ? LIMIT 1",
        (stored_filename,),
    ).fetchone()


def list_notes(user_id, keyword=None):
    """列出当前用户笔记（支持关键字过滤），新笔记在前。"""
    sql = "SELECT * FROM notes WHERE user_id = ?"
    params = [user_id]
    if keyword:
        kw = _escape_like(keyword)
        sql += """ AND (title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\')"""
        params.extend([f"%{kw}%", f"%{kw}%"])
    sql += " ORDER BY updated_at DESC, id DESC"
    return get_db().execute(sql, params).fetchall()


def count_notes(user_id):
    """统计当前用户笔记总数。"""
    row = get_db().execute(
        "SELECT COUNT(*) AS c FROM notes WHERE user_id = ?", (user_id,)
    ).fetchone()
    return row["c"]


# ============================================================
# 番茄钟 (Pomodoro)
# ============================================================
def add_pomodoro_record(user_id, mode, duration_seconds):
    """记录一个完成的番茄钟。"""
    db = get_db()
    db.execute(
        """INSERT INTO pomodoro_records (user_id, mode, duration_seconds, completed_at)
           VALUES (?, ?, ?, ?)""",
        (user_id, mode, duration_seconds, _now()),
    )
    db.commit()


def get_today_focus_count(user_id):
    """统计今天完成的专注番茄数（每日完成数统计）。"""
    row = get_db().execute(
        """SELECT COUNT(*) AS c FROM pomodoro_records
           WHERE user_id = ? AND mode = 'focus' AND date(completed_at) = ?""",
        (user_id, _today()),
    ).fetchone()
    return row["c"]


def get_recent_daily_focus(user_id, days=7):
    """返回最近 N 天每天完成的专注番茄数（用于折线/柱状图）。

    返回形如 [{"day": "09-01", "count": 3}, ...]，按日期升序。
    """
    start = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    rows = get_db().execute(
        """SELECT date(completed_at) AS day, COUNT(*) AS c
           FROM pomodoro_records
           WHERE user_id = ? AND mode = 'focus' AND date(completed_at) >= ?
           GROUP BY date(completed_at)""",
        (user_id, start),
    ).fetchall()
    by_day = {row["day"]: row["c"] for row in rows}
    result = []
    for i in range(days - 1, -1, -1):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        result.append({"day": day[5:], "count": by_day.get(day, 0)})
    return result


# ============================================================
# 全局搜索
# ============================================================
def search_notes(user_id, keyword):
    """按关键字搜索笔记标题与正文（只返回当前用户的）。"""
    kw = _escape_like(keyword)
    return get_db().execute(
        """SELECT id, title, content, updated_at FROM notes
           WHERE user_id = ? AND (title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\')
           ORDER BY updated_at DESC LIMIT 20""",
        (user_id, f"%{kw}%", f"%{kw}%"),
    ).fetchall()


def search_questions(user_id, keyword):
    """按关键字搜索题目（题干/解析/科目），只返回当前用户的。"""
    kw = _escape_like(keyword)
    return get_db().execute(
        """SELECT id, subject, content, analysis FROM questions
           WHERE user_id = ? AND (content LIKE ? ESCAPE '\\'
                  OR analysis LIKE ? ESCAPE '\\' OR subject LIKE ? ESCAPE '\\')
           ORDER BY id DESC LIMIT 20""",
        (user_id, f"%{kw}%", f"%{kw}%", f"%{kw}%"),
    ).fetchall()


# ============================================================
# 后台管理（管理员专属，跨用户操作）
# ============================================================
def count_users():
    """统计全站用户总数。"""
    row = get_db().execute("SELECT COUNT(*) AS c FROM users").fetchone()
    return row["c"]


def count_admins():
    """统计全站"管理员及以上"数量（role>=2，用于概览页展示）。"""
    row = get_db().execute(
        "SELECT COUNT(*) AS c FROM users WHERE role >= 2"
    ).fetchone()
    return row["c"]


def count_super_admins():
    """统计超级管理员数量（role=3，用于"至少保留 1 名超管"保护）。"""
    row = get_db().execute(
        "SELECT COUNT(*) AS c FROM users WHERE role = 3"
    ).fetchone()
    return row["c"]


def get_overview_stats():
    """后台概览统计：用户 / 题目 / 笔记 / 答题记录 / 番茄记录数。"""
    db = get_db()

    def _count(table):
        row = db.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
        return row["c"]

    return {
        "users": count_users(),
        "questions": _count("questions"),
        "notes": _count("notes"),
        "answer_records": _count("answer_records"),
        "pomodoro_records": _count("pomodoro_records"),
    }


def list_users_with_stats(keyword=None):
    """列出全站用户，附各用户的内容量统计（题目/笔记/答题/番茄）。

    支持按用户名或邮箱关键字过滤。
    """
    sql = """SELECT u.id, u.username, u.email, u.is_admin, u.role, u.created_at,
                    (SELECT COUNT(*) FROM questions q WHERE q.user_id = u.id)    AS question_count,
                    (SELECT COUNT(*) FROM notes n      WHERE n.user_id = u.id)    AS note_count,
                    (SELECT COUNT(*) FROM answer_records a WHERE a.user_id = u.id) AS answer_count,
                    (SELECT COUNT(*) FROM pomodoro_records p WHERE p.user_id = u.id) AS pomodoro_count
             FROM users u"""
    params = []
    if keyword:
        kw = _escape_like(keyword)
        sql += " WHERE u.username LIKE ? ESCAPE '\\' OR u.email LIKE ? ESCAPE '\\'"
        params.extend([f"%{kw}%", f"%{kw}%"])
    sql += " ORDER BY u.id ASC"
    return get_db().execute(sql, params).fetchall()


def set_user_role(user_id, role):
    """设置用户的四层角色（0 普通 / 1 协管 / 2 管理员 / 3 超级管理员）。

    同步维护兼容列 is_admin（role>=1 → 1），保证旧查询/工具仍可用。
    """
    role = int(role or 0)
    if role not in ROLE_LABELS:
        role = ROLE_USER
    db = get_db()
    db.execute(
        "UPDATE users SET role = ?, is_admin = ? WHERE id = ?",
        (role, 1 if role >= ROLE_MOD else 0, user_id),
    )
    db.commit()


def set_user_admin(user_id, is_admin):
    """旧接口兼容：设为管理员 = 超级管理员（role 3）；取消 = 普通用户（role 0）。"""
    set_user_role(user_id, ROLE_SUPER if is_admin else ROLE_USER)


def get_user_notes_for_cleanup(user_id):
    """返回某用户的全部笔记（后台删除用户前，用于清理上传文件）。"""
    return get_db().execute(
        "SELECT id, stored_filename FROM notes WHERE user_id = ?",
        (user_id,),
    ).fetchall()


def delete_user_by_id(user_id):
    """删除用户（题目/笔记/答题记录/番茄记录通过外键级联删除）。"""
    db = get_db()
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()


def list_all_questions(subject=None, keyword=None, limit=200):
    """后台全站题目列表（附作者用户名），支持按科目 / 关键字过滤。"""
    sql = """SELECT q.*, u.username AS owner_username
             FROM questions q
             LEFT JOIN users u ON u.id = q.user_id"""
    conditions = []
    params = []
    if subject:
        conditions.append("q.subject = ?")
        params.append(subject)
    if keyword:
        kw = _escape_like(keyword)
        conditions.append(
            "(q.content LIKE ? ESCAPE '\\' OR q.subject LIKE ? ESCAPE '\\' "
            "OR q.analysis LIKE ? ESCAPE '\\')"
        )
        params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY q.id DESC LIMIT ?"
    params.append(limit)
    return get_db().execute(sql, params).fetchall()


def list_all_subjects():
    """后台全站科目列表（题目过滤用下拉框）。"""
    return get_db().execute(
        "SELECT DISTINCT subject FROM questions ORDER BY subject ASC"
    ).fetchall()


def delete_question_any(question_id):
    """管理员删除任意用户的题目（答题记录级联删除）。"""
    db = get_db()
    db.execute("DELETE FROM questions WHERE id = ?", (question_id,))
    db.commit()


def list_all_notes(keyword=None, limit=200):
    """后台全站笔记列表（附作者用户名），支持按标题 / 内容关键字过滤。"""
    sql = """SELECT n.*, u.username AS owner_username
             FROM notes n
             LEFT JOIN users u ON u.id = n.user_id"""
    params = []
    if keyword:
        kw = _escape_like(keyword)
        sql += " WHERE n.title LIKE ? ESCAPE '\\' OR n.content LIKE ? ESCAPE '\\'"
        params.extend([f"%{kw}%", f"%{kw}%"])
    sql += " ORDER BY n.updated_at DESC, n.id DESC LIMIT ?"
    params.append(limit)
    return get_db().execute(sql, params).fetchall()


def get_note_any(note_id):
    """管理员按 id 获取任意用户的笔记（不校验归属）。"""
    return get_db().execute(
        "SELECT * FROM notes WHERE id = ?", (note_id,)
    ).fetchone()


def delete_note_any(note_id):
    """管理员删除任意用户的笔记。"""
    db = get_db()
    db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    db.commit()


def get_recent_users(limit=6):
    """后台概览：返回最新注册的若干用户（仪表盘"最新注册"列表）。"""
    return get_db().execute(
        """SELECT id, username, email, is_admin, role, created_at
           FROM users ORDER BY id DESC LIMIT ?""",
        (limit,),
    ).fetchall()


def get_site_daily_focus(days=7):
    """后台概览：最近 N 天全站每天完成的专注番茄数（趋势图）。

    返回形如 [{"day": "09-01", "count": 3}, ...]，按日期升序。
    """
    start = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    rows = get_db().execute(
        """SELECT date(completed_at) AS day, COUNT(*) AS c
           FROM pomodoro_records
           WHERE mode = 'focus' AND date(completed_at) >= ?
           GROUP BY date(completed_at)""",
        (start,),
    ).fetchall()
    by_day = {row["day"]: row["c"] for row in rows}
    result = []
    for i in range(days - 1, -1, -1):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        result.append({"day": day[5:], "count": by_day.get(day, 0)})
    return result


def get_questions_by_filter(user_id, subject=None, topic=None, question_type=None,
                            difficulty=None, keyword=None):
    """按学科、主题、题型、难度筛选题目（可与关键字组合使用）。

    - question_type：题干未设置题型（NULL/空）的历史手工题视为「选择题」，
      与列表页/刷题页的归一化逻辑一致，避免同数据不同筛选结果。
    - keyword：对题干 / 解析 / 答案做 LIKE 过滤，可与上述维度叠加。
    """
    sql = "SELECT * FROM questions WHERE user_id = ?"
    params = [user_id]

    if subject:
        sql += " AND subject = ?"
        params.append(subject)
    if topic:
        sql += " AND topic = ?"
        params.append(topic)
    if question_type:
        if question_type == "选择题":
            # NULL / 空题型 == 选择题（历史手工题没有显式题型）
            sql += " AND (question_type IS NULL OR question_type = ?)"
        else:
            sql += " AND question_type = ?"
        params.append(question_type)
    if difficulty:
        sql += " AND difficulty = ?"
        params.append(difficulty)
    if keyword:
        kw = _escape_like(keyword)
        sql += """ AND (content LIKE ? ESCAPE '\\' OR analysis LIKE ? ESCAPE '\\'
                       OR answer LIKE ? ESCAPE '\\')"""
        params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])

    sql += " ORDER BY id DESC"
    return get_db().execute(sql, params).fetchall()

def get_distinct_subjects(user_id):
    """获取当前用户所有学科"""
    return [row["subject"] for row in get_db().execute(
        "SELECT DISTINCT subject FROM questions WHERE user_id = ?", (user_id,)
    ).fetchall()]

def get_distinct_topics(user_id, subject=None):
    """获取某学科下的所有主题"""
    sql = "SELECT DISTINCT topic FROM questions WHERE user_id = ?"
    params = [user_id]
    if subject:
        sql += " AND subject = ?"
        params.append(subject)
    return [row["topic"] for row in get_db().execute(sql, params).fetchall()]

def get_distinct_types(user_id):
    """获取所有题型（NULL/空题型归并为「选择题」）。"""
    rows = get_db().execute(
        """SELECT DISTINCT COALESCE(NULLIF(question_type, ''), '选择题') AS qtype
           FROM questions WHERE user_id = ?""",
        (user_id,),
    ).fetchall()
    return [r["qtype"] for r in rows]

def get_distinct_difficulties(user_id):
    """获取所有难度"""
    return [row["difficulty"] for row in get_db().execute(
        "SELECT DISTINCT difficulty FROM questions WHERE user_id = ?", (user_id,)
    ).fetchall()]


# ============================================================
# 论坛（forum_posts / forum_replies）
# ============================================================
def create_forum_post(user_id, title, content):
    """发表主题帖，返回新帖子 id。"""
    db = get_db()
    cur = db.execute(
        """INSERT INTO forum_posts (user_id, title, content, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, title, content, _now(), _now()),
    )
    db.commit()
    return cur.lastrowid


def get_forum_post(post_id):
    """按 id 取帖子（含作者名与头像），不存在返回 None。"""
    return get_db().execute(
        """SELECT p.*, u.username AS author_name, u.avatar AS author_avatar
           FROM forum_posts p LEFT JOIN users u ON u.id = p.user_id
           WHERE p.id = ?""",
        (post_id,),
    ).fetchone()


def list_forum_posts(keyword=None, limit=200):
    """论坛帖子列表（新回复在前），附作者名/回帖数。"""
    sql = """SELECT p.*, u.username AS author_name, u.avatar AS author_avatar,
                    (SELECT COUNT(*) FROM forum_replies r WHERE r.post_id = p.id) AS reply_count
             FROM forum_posts p LEFT JOIN users u ON u.id = p.user_id"""
    params = []
    if keyword:
        kw = _escape_like(keyword)
        sql += " WHERE p.title LIKE ? ESCAPE '\\' OR p.content LIKE ? ESCAPE '\\'"
        params.extend([f"%{kw}%", f"%{kw}%"])
    sql += " ORDER BY p.updated_at DESC, p.id DESC LIMIT ?"
    params.append(limit)
    return get_db().execute(sql, params).fetchall()


def delete_forum_post(post_id):
    """删除主题帖（回帖级联删除）。"""
    db = get_db()
    db.execute("DELETE FROM forum_posts WHERE id = ?", (post_id,))
    db.commit()


def create_forum_reply(user_id, post_id, content):
    """回帖；同时刷新主题帖 updated_at 使帖子升到顶部。"""
    db = get_db()
    cur = db.execute(
        "INSERT INTO forum_replies (post_id, user_id, content, created_at) VALUES (?, ?, ?, ?)",
        (post_id, user_id, content, _now()),
    )
    db.execute(
        "UPDATE forum_posts SET updated_at = ? WHERE id = ?", (_now(), post_id)
    )
    db.commit()
    return cur.lastrowid


def list_forum_replies(post_id, limit=300):
    """帖子下回帖（时间正序），附作者名与头像。"""
    return get_db().execute(
        """SELECT r.*, u.username AS author_name, u.avatar AS author_avatar
           FROM forum_replies r LEFT JOIN users u ON u.id = r.user_id
           WHERE r.post_id = ?
           ORDER BY r.id ASC LIMIT ?""",
        (post_id, limit),
    ).fetchall()


def get_forum_reply(reply_id):
    """按 id 取回帖（权限判断用）。"""
    return get_db().execute(
        "SELECT * FROM forum_replies WHERE id = ?", (reply_id,)
    ).fetchone()


def delete_forum_reply(reply_id):
    """删除回帖。"""
    db = get_db()
    db.execute("DELETE FROM forum_replies WHERE id = ?", (reply_id,))
    db.commit()


# ============================================================
# 媒体库（视频直连分块传输，见 blueprints/media.py / db.py 建表段）
# ============================================================
# 说明：media_items 记录媒体"双重地址"——R2 对象键 r2_key（云端）与本地
# 文件 local_file（proxy 通道的本地副本）；分块进度记录在 media_chunks。
# 状态机：
#   init → uploading → (proxy: promoting →) ready → verifying → backed_up
#   任一步失败 → failed（error 记录原因）
MEDIA_ITEM_UPDATABLE = {
    "title", "mime", "size_bytes", "sha256", "status", "r2_bucket",
    "r2_upload_id", "part_size", "uploaded_bytes", "local_file", "error",
}


def _media_now():
    """媒体表时间戳（本地时间）。"""
    return _now()


def create_media_item(user_id, title, filename, ext, size_bytes, channel,
                      r2_key, part_size, mime=None, r2_upload_id=None):
    """新建一条媒体记录（分块上传会话），返回新 id。"""
    db = get_db()
    now = _media_now()
    cur = db.execute(
        """INSERT INTO media_items
           (user_id, title, filename, mime, ext, size_bytes, channel,
            status, r2_bucket, r2_key, r2_upload_id, part_size, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?, 'uploading', ?, ?, ?, ?, ?, ?)""",
        (user_id, title, filename, mime or "", ext, size_bytes, channel,
         _r2_main_bucket(), r2_key, r2_upload_id, part_size, now, now),
    )
    db.commit()
    return cur.lastrowid


def _r2_main_bucket():
    """主桶名：默认 'study-media'（与 config 默认一致，避免循环导入）。"""
    from config import Config
    return getattr(Config, "R2_BUCKET", None) or "study-media"


def get_media_item(item_id):
    """按 id 取媒体记录（不含权限判断）。"""
    return get_db().execute(
        "SELECT * FROM media_items WHERE id = ?", (item_id,)
    ).fetchone()


def get_media_item_owned(item_id, user_id, is_admin=False):
    """按 id 取媒体记录；非管理员只能取自己的（权限判断用）。"""
    if is_admin:
        return get_media_item(item_id)
    return get_db().execute(
        "SELECT * FROM media_items WHERE id = ? AND user_id = ?",
        (item_id, user_id),
    ).fetchone()


def list_media_items(user_id, limit=200, offset=0):
    """列出某用户的媒体记录（新建在前）。"""
    return get_db().execute(
        """SELECT * FROM media_items WHERE user_id = ?
           ORDER BY id DESC LIMIT ? OFFSET ?""",
        (user_id, limit, offset),
    ).fetchall()


def count_media_bytes(user_id):
    """某用户已用总字节数（配额检查用）。"""
    row = get_db().execute(
        "SELECT COALESCE(SUM(size_bytes), 0) AS total FROM media_items WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    return int(row["total"] or 0)


def update_media_item(item_id, **fields):
    """更新媒体记录；fields 键必须在白名单 MEDIA_ITEM_UPDATABLE 内。"""
    if not fields:
        return
    bad = set(fields) - MEDIA_ITEM_UPDATABLE
    if bad:
        raise ValueError(f"不允许更新的字段: {sorted(bad)}")
    cols = ", ".join(f"{k} = ?" for k in fields)
    db = get_db()
    db.execute(
        f"UPDATE media_items SET {cols}, updated_at = ? WHERE id = ?",
        (*fields.values(), _media_now(), item_id),
    )
    db.commit()


def set_media_status(item_id, status, error=None):
    """更新媒体状态（可选失败原因）。"""
    db = get_db()
    if error:
        db.execute(
            "UPDATE media_items SET status = ?, error = ?, updated_at = ? WHERE id = ?",
            (status, error, _media_now(), item_id),
        )
    else:
        db.execute(
            "UPDATE media_items SET status = ?, error = NULL, updated_at = ? WHERE id = ?",
            (status, _media_now(), item_id),
        )
    db.commit()


def delete_media_item(item_id):
    """删除媒体记录行（级联删除分块进度）。"""
    db = get_db()
    db.execute("DELETE FROM media_items WHERE id = ?", (item_id,))
    db.commit()


def add_media_chunk(item_id, part_number, size_bytes, etag=None, md5=None):
    """记录一个已成功上传的分块（断点续传依据）。"""
    db = get_db()
    db.execute(
        """INSERT OR IGNORE INTO media_chunks
           (item_id, part_number, size_bytes, etag, md5, created_at)
           VALUES (?,?,?,?,?,?)""",
        (item_id, part_number, size_bytes, etag, md5, _media_now()),
    )
    db.commit()


def set_media_chunk(item_id, part_number, size_bytes, etag=None, md5=None):
    """覆盖写一个分块记录（重传成功时更新 ETag/大小）。"""
    db = get_db()
    db.execute(
        """INSERT INTO media_chunks (item_id, part_number, size_bytes, etag, md5, created_at)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(item_id, part_number) DO UPDATE SET
             size_bytes = excluded.size_bytes,
             etag       = excluded.etag,
             md5        = excluded.md5""",
        (item_id, part_number, size_bytes, etag, md5, _media_now()),
    )
    db.commit()


def list_media_chunks(item_id):
    """列出某媒体的分块记录（按 part_number 升序）。"""
    return get_db().execute(
        "SELECT * FROM media_chunks WHERE item_id = ? ORDER BY part_number",
        (item_id,),
    ).fetchall()


def sum_media_chunks(item_id):
    """某媒体已上传分块的字节总和。"""
    row = get_db().execute(
        "SELECT COALESCE(SUM(size_bytes), 0) AS total FROM media_chunks WHERE item_id = ?",
        (item_id,),
    ).fetchone()
    return int(row["total"] or 0)


def clear_media_chunks(item_id):
    """清空某媒体的分块记录。"""
    db = get_db()
    db.execute("DELETE FROM media_chunks WHERE item_id = ?", (item_id,))
    db.commit()
