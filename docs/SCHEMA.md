# 数据库设计文档 (SCHEMA)

本项目使用 SQLite 存储所有数据，数据库文件默认位于 `data/study_assistant.db`。
建表 SQL 定义在 `db.py` 的 `SCHEMA` 变量中，应用启动时自动执行（幂等，可安全重复运行）。

## 表结构汇总

### 1. users 用户表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 用户主键 |
| username | TEXT | NOT NULL UNIQUE | 用户名 |
| email | TEXT | NOT NULL UNIQUE | 邮箱 |
| password_hash | TEXT | NOT NULL | bcrypt 密码哈希（单向加密） |
| created_at | TEXT | NOT NULL | 注册时间 |

### 2. questions 题目表

支持三种题型（选择题 / 填空题 / 解答题），答案不限于 A~D：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 题目主键 |
| user_id | INTEGER | NOT NULL, FK → users.id | 所属用户（级联删除） |
| subject | TEXT | NOT NULL | 科目名（如：数学） |
| topic | TEXT | 可空 | 知识点/主题（如：有理数），列表页筛选用 |
| grade | TEXT | 可空 | 年级（如：初中） |
| question_type | TEXT | 可空 | 题型：选择题 / 填空题 / 解答题（NULL 视为选择题） |
| difficulty | TEXT | 可空 | 难度：简单 / 中等 / 较难 |
| score | INTEGER | 默认 3 | 分值（解答题通常 6~12 分） |
| content | TEXT | NOT NULL | 题干 |
| option_a ~ option_d | TEXT | 可空 | 四个选项（仅选择题使用；填空/解答留空） |
| answer | TEXT | NOT NULL | 答案：选择题存 A/B/C/D；填空/解答存文本答案 |
| analysis | TEXT | 可空 | 答案解析 / 解题思路 |
| step_rules | TEXT | 可空 | 解答题评分标准（JSON 对象字符串，如 `{"列出已知条件": 2}`） |
| created_at / updated_at | TEXT | NOT NULL | 创建/更新时间 |

说明：
- 早期版本 questions 表只有 subject/content/选项/answer/analysis，
  通过迁移补入了 topic/grade/question_type/difficulty/score/step_rules 列；
  表单手工添加的题目这些列为 NULL，列表与刷题时默认按选择题处理。

### 3. answer_records 答题记录表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 记录主键 |
| user_id | INTEGER | NOT NULL, FK → users.id | 所属用户（级联删除） |
| question_id | INTEGER | NOT NULL, FK → questions.id | 被作答的题目（级联删除） |
| user_answer | TEXT | NOT NULL DEFAULT '' | 用户答案：选择题存 A/B/C/D；填空/解答存输入文本 |
| is_correct | INTEGER | NOT NULL DEFAULT 0 | 0=错误 1=正确（解答题自评满分视为正确） |
| score | INTEGER | NOT NULL DEFAULT 0 | 本题得分：选择/填空答对得满分；解答题为自评得分 |
| answered_at | TEXT | NOT NULL | 作答时间 |

### 4. notes 笔记表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 笔记主键 |
| user_id | INTEGER | NOT NULL, FK → users.id | 所属用户（级联删除） |
| title | TEXT | NOT NULL | 笔记标题 |
| content | TEXT | NOT NULL DEFAULT '' | 笔记正文（上传时自动提取的文本） |
| source_filename | TEXT | NOT NULL DEFAULT '' | 上传时的原始文件名 |
| stored_filename | TEXT | NOT NULL DEFAULT '' | 存储时的 uuid 文件名 |
| file_type | TEXT | NOT NULL DEFAULT 'text' | text / markdown / image 等 |
| created_at / updated_at | TEXT | NOT NULL | 创建/更新时间 |

### 5. pomodoro_records 番茄钟记录表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 记录主键 |
| user_id | INTEGER | NOT NULL, FK → users.id | 所属用户（级联删除） |
| mode | TEXT | NOT NULL DEFAULT 'focus' | focus / short_break / long_break |
| duration_seconds | INTEGER | NOT NULL DEFAULT 1500 | 本次番茄钟时长（秒） |
| completed_at | TEXT | NOT NULL | 完成时间 |

## 索引

```sql
CREATE INDEX idx_questions_user_subject ON questions(user_id, subject);
CREATE INDEX idx_questions_user_type ON questions(user_id, question_type);
CREATE INDEX idx_answer_records_user ON answer_records(user_id);
CREATE INDEX idx_notes_user ON notes(user_id);
CREATE INDEX idx_pomodoro_user_time ON pomodoro_records(user_id, completed_at);
```

## 关系说明

- 所有业务表通过 `user_id` 外键关联 `users.id`，并开启 `ON DELETE CASCADE`：
  删除用户时其题目、答题记录、笔记、番茄钟记录一并删除。
- 每个连接建立时执行 `PRAGMA foreign_keys = ON` 强制启用外键约束。

## 备份与重置

- 备份：直接复制 `data/study_assistant.db` 文件即可。
- 重置：停止应用后删除该文件，重启应用会自动重新建表。
