# -*- coding: utf-8 -*-
"""数据库模块。

职责：
1. 定义建表 SQL（SCHEMA），应用启动时自动执行，保证表结构存在；
2. 提供基于 Flask 请求上下文（g）的 SQLite 连接管理。

技术选择说明：
- 使用 Python 标准库 sqlite3，不引入 ORM，保持依赖精简、对二次开发者透明；
- 每个请求复用同一个连接（存于 g），请求结束自动关闭；
- 表之间通过 user_id 外键关联用户，开启外键约束以保证数据完整性。
"""
import os
import sqlite3

from flask import current_app, g

# ============================================================
# 建表 SQL（在应用启动时自动执行）
# ============================================================
# 设计说明：
#   - users          用户表（唯一的鉴权主体，其他表均外键关联它）
#   - questions      题目表（科目/知识点/题型/难度/分值/题干/选项/答案/解析/评分标准）
#   - answer_records 答题记录表（记录每次作答，含用户答案与本题得分，用于统计）
#   - notes          笔记表（存标题、正文内容，及上传文件信息）
#   - pomodoro_records 番茄钟完成记录表（每日完成数统计）
# 时间字段统一使用文本存储 "YYYY-MM-DD HH:MM:SS"，由 Python 端写入本地时间。
#
# 关于 questions 扩展列（topic/grade/question_type/difficulty/score/step_rules）：
# 早期版本没有这些列，后来通过 migrate_db.py 重建表加入；本文件保持与迁移后
# 的结构一致，保证全新安装（无旧库）也能直接使用「分类/筛选/刷题」功能。
# 手工在表单新增的旧式题目上述列为 NULL：题型按选择题处理、分值按题型兜底。
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    is_admin      INTEGER NOT NULL DEFAULT 0,  -- 兼容旧字段：1 表示 role>=1（后台角色）
    role          INTEGER NOT NULL DEFAULT 0,  -- 0 普通 / 1 协管 / 2 管理员 / 3 超级管理员
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject       TEXT    NOT NULL,                -- 科目名
    topic         TEXT,                            -- 知识点/主题（如：有理数）
    grade         TEXT,                            -- 年级（如：初中）
    question_type TEXT,                            -- 题型：选择题/填空题/解答题（NULL 视为选择题）
    difficulty    TEXT,                            -- 难度：简单/中等/较难
    score         INTEGER DEFAULT 3,               -- 分值（解答题通常 6~12 分）
    content       TEXT    NOT NULL,                -- 题干
    option_a      TEXT,                            -- 选项 A（仅选择题使用，可空）
    option_b      TEXT,
    option_c      TEXT,
    option_d      TEXT,
    answer        TEXT    NOT NULL,                -- 答案：选择题存 A~D，填空/解答存文本
    analysis      TEXT,                            -- 答案解析
    step_rules    TEXT,                            -- 解答题评分标准（JSON 字符串，如 {"步骤": 分值}）
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_questions_user_subject ON questions(user_id, subject);
CREATE INDEX IF NOT EXISTS idx_questions_user_type ON questions(user_id, question_type);

CREATE TABLE IF NOT EXISTS answer_records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    user_answer TEXT    NOT NULL DEFAULT '',    -- 用户答案：选择题存 A/B/C/D，填空/解答存输入文本
    is_correct  INTEGER NOT NULL DEFAULT 0,     -- 0=错误 1=正确（解答题自评满分视为正确）
    score       INTEGER NOT NULL DEFAULT 0,     -- 本题得分：选择题/填空题答对得满分；解答题为自评得分
    answered_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_answer_records_user ON answer_records(user_id);

CREATE TABLE IF NOT EXISTS notes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title           TEXT    NOT NULL,
    content         TEXT    NOT NULL DEFAULT '', -- 笔记正文（上传时自动提取的文本）
    source_filename TEXT    NOT NULL DEFAULT '', -- 上传时的原始文件名
    stored_filename TEXT    NOT NULL DEFAULT '', -- 存储时的 uuid 文件名
    file_type       TEXT    NOT NULL DEFAULT 'text', -- text / markdown / image 等
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id);

CREATE TABLE IF NOT EXISTS pomodoro_records (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mode             TEXT    NOT NULL DEFAULT 'focus', -- focus / short_break / long_break
    duration_seconds INTEGER NOT NULL DEFAULT 1500,    -- 本次番茄钟持续秒数
    completed_at     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pomodoro_user_time ON pomodoro_records(user_id, completed_at);

-- 论坛：主题帖
CREATE TABLE IF NOT EXISTS forum_posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title      TEXT    NOT NULL,
    content    TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_forum_posts_user ON forum_posts(user_id);
CREATE INDEX IF NOT EXISTS idx_forum_posts_time ON forum_posts(updated_at);

-- 论坛：回帖
CREATE TABLE IF NOT EXISTS forum_replies (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id    INTEGER NOT NULL REFERENCES forum_posts(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content    TEXT    NOT NULL,
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_forum_replies_post ON forum_replies(post_id);

-- ==================================================================
-- 媒体库（视频直连分块传输，见 blueprints/media.py）
--   media_items   媒体记录：R2 对象地址（r2_key）+ 可选本地副本（local_file）
--                 即"双重地址"；分块上传会话、校验/备份状态也记在这里。
--   media_chunks  分块进度表（断点续传依据；r2 通道在完成后回填，
--                 proxy 通道边收边写）
-- 时间字段统一 "YYYY-MM-DD HH:MM:SS"（本地时间，与本站其它表一致）。
-- ==================================================================
CREATE TABLE IF NOT EXISTS media_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title         TEXT    NOT NULL,              -- 展示标题（默认原文件名去扩展名）
    filename      TEXT    NOT NULL,              -- 原始文件名（含扩展名，仅展示用）
    mime          TEXT,                          -- 内容类型（上传时声明，可空）
    ext           TEXT    NOT NULL,              -- 小写扩展名（白名单校验过）
    size_bytes    INTEGER NOT NULL DEFAULT 0,    -- 期望总字节数
    sha256        TEXT,                          -- 整文件 SHA-256（审计任务回填）
    channel       TEXT    NOT NULL DEFAULT 'r2', -- r2=浏览器直传R2 / proxy=本站中转
    status        TEXT    NOT NULL DEFAULT 'init', -- init/uploading/promoting/ready/
                                                 -- verifying/backed_up/failed
    r2_bucket     TEXT,                          -- 实际所在桶（默认主桶；备份后指主桶）
    r2_key        TEXT    NOT NULL,              -- R2 对象键（用户目录下 UUID，唯一）
    r2_upload_id  TEXT,                          -- 分块上传会话 ID（上传中）
    part_size     INTEGER NOT NULL DEFAULT 16777216,
    uploaded_bytes INTEGER NOT NULL DEFAULT 0,   -- 已成功分块字节数（续传进度展示）
    local_file    TEXT,                          -- proxy 通道本地文件相对路径（可空）
    error         TEXT,                          -- 最近一次失败原因
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_media_items_user   ON media_items(user_id);
CREATE INDEX IF NOT EXISTS idx_media_items_status ON media_items(status);
CREATE INDEX IF NOT EXISTS idx_media_items_r2key  ON media_items(r2_key);

CREATE TABLE IF NOT EXISTS media_chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id     INTEGER NOT NULL REFERENCES media_items(id) ON DELETE CASCADE,
    part_number INTEGER NOT NULL,                -- 从 1 开始
    size_bytes  INTEGER NOT NULL DEFAULT 0,
    etag        TEXT,                            -- R2 返回的 ETag（回填）
    md5         TEXT,                            -- 分块 MD5（base64，proxy 加密前算）
    created_at  TEXT    NOT NULL,
    UNIQUE(item_id, part_number)
);
CREATE INDEX IF NOT EXISTS idx_media_chunks_item ON media_chunks(item_id);
"""


def get_db():
    """获取当前请求的数据库连接（存在 Flask 上下文 g 中）。"""
    if "db" not in g:
        conn = sqlite3.connect(
            current_app.config["DATABASE"],
            timeout=15,  # 并发写等待最长 15s，减少 "database is locked"
        )
        conn.row_factory = sqlite3.Row          # 返回字典式行，便于模板/JSON 使用
        conn.execute("PRAGMA foreign_keys = ON")  # 开启外键约束
        try:
            # WAL：读写不互斥，多线程/多进程下显著降低锁冲突（仅 WAL 支持的存储可用）
            conn.execute("PRAGMA journal_mode = WAL")
        except sqlite3.DatabaseError:
            pass  # 网络/只读存储不支持 WAL 时静默回退默认模式
        conn.execute("PRAGMA busy_timeout = 15000")
        g.db = conn
    return g.db


def close_db(_error=None):
    """请求结束时关闭数据库连接。"""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def migrate_schema(app):
    """轻量数据库迁移：为旧库补充新增列，保证不丢已有数据。

    当前迁移（幂等，重复执行安全）：
    - users 表：补充 is_admin 列（旧版本建的表没有该列）
    - questions 表：补充 topic / grade / question_type / difficulty / score /
      step_rules 列（题库分类与刷题功能所需，旧版表单题没有这些列）
    - answer_records 表：补充 score 列（记录选择题/填空题得分与解答题自评得分）

    原理：用 PRAGMA table_info 检查列是否存在，不存在才 ALTER TABLE 补列，
    因此对新建数据库与已存在的旧数据库都安全。
    """
    with app.app_context():
        db = get_db()

        def _table_columns(table):
            return [row["name"] for row in db.execute(
                f"PRAGMA table_info({table})").fetchall()]

        def _add_column(table, column, definition):
            if column not in _table_columns(table):
                db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

        # users.is_admin：0=普通用户 1=管理员
        _add_column("users", "is_admin", "INTEGER NOT NULL DEFAULT 0")
        # users.role：四层权限（0 普通 / 1 协管 / 2 管理员 / 3 超级管理员）。
        # 旧库 is_admin=1 的历史管理员一律迁移为最高层（3），is_admin 同步为 1。
        _add_column("users", "role", "INTEGER NOT NULL DEFAULT 0")
        db.execute("UPDATE users SET role = 3, is_admin = 1 WHERE is_admin = 1 AND role = 0")

        # users.avatar：自定义头像（JSON：{"kind":"emoji"/"image", "value":..., "color":...}）
        _add_column("users", "avatar", "TEXT")

        # questions 的分类 / 刷题扩展列（允许为空，历史手工题保持原样）
        _add_column("questions", "topic", "TEXT")
        _add_column("questions", "grade", "TEXT")
        _add_column("questions", "question_type", "TEXT")
        _add_column("questions", "difficulty", "TEXT")
        _add_column("questions", "score", "INTEGER DEFAULT 3")
        _add_column("questions", "step_rules", "TEXT")
        # questions.image：自动生成的题图路径（/static/img/q/<id>.svg，可为空）
        _add_column("questions", "image", "TEXT")

        # answer_records.score：本题得分（默认 0）
        _add_column("answer_records", "score", "INTEGER NOT NULL DEFAULT 0")

        db.commit()


def init_db(app):
    """初始化数据库：确保目录存在并执行建表 SQL。

    在应用启动时调用，保证表结构总是存在（幂等）。
    """
    # 确保数据库目录存在（sqlite3 不会自动创建目录）
    db_path = app.config["DATABASE"]
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # 注册请求结束时的清理回调
    app.teardown_appcontext(close_db)

    # 在应用上下文中执行建表
    with app.app_context():
        db = get_db()
        db.executescript(SCHEMA)
        db.commit()

    # 轻量迁移：为旧库补充新列（不丢数据）
    migrate_schema(app)
