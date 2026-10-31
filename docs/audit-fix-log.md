# 代码审查修复记录

> 对应 2025 版代码审查报告逐条修复的结论与改动位置。验证基准：`python -m unittest discover -s tests`（39 项，全绿）；服务 `manage.py restart` 后健康检查 200。

## 🔴 安全

### 1. 源码泄漏硬编码密钥 / 明文密码
- **问题**：`gen_questions.py:19` 与 `tools/build_question_bank.py:36` 硬编码同一把 DeepSeek API Key；`tools/_deploy_check.py:12` 明文写 admin 密码。
- **修复**：
  - 两处脚本改为**只从环境变量 `DEEPSEEK_API_KEY` 读取**，缺失即报错退出（不再带默认回退值）。
  - 删除 `tools/_deploy_check.py` 及 `_deploy_check_out.txt`。
  - 全盘扫描残留（py/json/md/txt/bat/html）已确认无该 key / 密码。
- **注意**：密钥不留代码属纵深防御；若项目从未外发，可视需要决定是否轮换 DeepSeek Key / 修改 admin 密码。

### 2. OCR 保存导致任意文件删除（路径穿越链）
- **问题**：`blueprints/ocr.py` 的 `/ocr/save` 无条件信任表单 `stored` 文件名；`notes.py`、`admin.py` 删除笔记/清理文件时 `os.remove(join(UPLOAD_FOLDER, stored_filename))` 无目录校验，`stored=../../config.py` 可越权删文件。
- **修复**：新增 `services/file_guard.py`：
  - `is_safe_stored_filename()`：纯文件名白名单 `^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$`，拒绝含 `/ \` 或目录成分。
  - `uploaded_file_path()`：normpath + `os.path.commonpath` 确认仍在上传目录内。
  - `remove_uploaded_file()`：统一安全删除入口（非法名忽略、OSError 容错）。
  - `ocr.save` 对 `stored` 白名单校验，非法则丢弃关联文件仅存文本。
  - `notes.py`、`admin.py`（删用户清理 + 删笔记）全部改用 `remove_uploaded_file`。

### 3. 无 CSRF 防护 / 固定 SECRET_KEY / GET 登出
- **问题**：所有状态变更接口无 CSRF 校验；`config.py` 默认 `SECRET_KEY="study-assistant-dev-secret-change-me"`；登出允许 GET。
- **修复**：
  - 新增 `services/csrf.py`（零第三方依赖）：会话 `_csrf` 令牌，`before_request` 校验所有非安全方法；来源可为表单 `csrf_token` 字段或 `X-CSRFToken` 头；`hmac.compare_digest` 比较；失败 400。
  - `app.py` 安装 CSRF；模板注入 `csrf_token()`。
  - `base.html` / `admin/base_admin.html` 输出 `<meta name="csrf-token">`；新增 `static/js/csrf.js` 自动给表单加 hidden、给 fetch 加 `X-CSRFToken`。
  - 登出改 **POST-only**；前台与后台登出改为 POST 表单（含 token）。
  - `config.py`：`SESSION_COOKIE_SAMESITE="Lax"`、`HTTPONLY=True`；HTTPS 时 `Secure`；新增 `APP_ENV`，production 未显式设置 `SECRET_KEY` 拒绝启动。
  - 测试：`TestConfig.CSRF_ENABLED=False`（CSRF 行为另有断言验证）。

## 🟠 正确性 / 功能

### 4. 题目表单录不了填空 / 解答题
- **问题**：`_validate_form` 强制四选项非空且答案 ∈ A~D，与刷题三题型能力矛盾。
- **修复**：表单新增题型/难度/知识点/年级/分值；按题型校验——选择题要求四选项与 ABCD 答案；填空/解答仅要求答案非空；答案字段按题型取 `answer_choice`/`answer_text`（兼容旧 `answer`）。`models.create_question/update_question` 支持 topic/grade/question_type/difficulty/score。`form.html` 前端按题型显隐选项区与答案框。
- **验证**：冒烟——解答题/填空题可创建、选择题缺选项被拒。

### 5. 搜索 + 筛选组合失效
- **问题**：`questions.index` 有关键字时走旧查询，丢掉 type/topic/difficulty。
- **修复**：`get_questions_by_filter` 增加 `keyword` 参数；列表页统一单次组合查询，删除旧分支。

### 6. NULL 题型语义不一致
- **问题**：手工旧题 `question_type=NULL`，筛选「选择题」时被漏，列表/刷题却把 NULL 当选择题。
- **修复**：`get_questions_by_filter` 选择题分支 `(question_type IS NULL OR ='选择题')`；`get_distinct_types` 用 `COALESCE(NULLIF(question_type,''),'选择题')` 归一。

### 7. 手写 SVG 黑名单净化可绕过（潜在存储型 XSS）
- **问题**：`_sanitize_svg_content` 仅删 script/事件属性/大小写敏感 `javascript:`，detail 页 `|safe` 输出。
- **修复**：改为**白名单**——仅保留 `svg/rect/path/line/circle/polyline/polygon/g/title/desc` 标签与有限属性集合；`javascript:`/`&#`/`&colon` 等值拒绝；清理危险标签残留闭合片段；`detail` 渲染前二次净化（兜底存量）。
- **验证**：合法手写产物原样保留；`<script>`、`onload/onclick`、`iframe/foreignObject` 全部剥除。

### 8. 上传文件访问 IDOR
- **问题**：`/notes/files/<path>` 只要求登录，任意登录用户可读他人上传原件。
- **修复**：文件名白名单 + `get_note_by_stored_filename` 反查归属：必须是本人笔记或 `role>=1`（协管及以上内容治理），否则 403/404。

### 9. 计时器后台节流失真
- **问题**：番茄钟 / 倒计时每秒减 1，后台标签节流会变慢 / 暂停；番茄钟完成不复位按钮。
- **修复**：`pomodoro.js`、`timer.js` 倒计时改 **endAt 时间戳驱动**（剩余 = ceil((endAt-now)/1000)）；暂停时对齐真实值；`visibilitychange` 回到前台立即追平；完成时补 `setControls(false)`。秒表本就是时间戳累计，未动。

### 10. SQLite 并发脆弱
- **问题**：未开 WAL / busy_timeout，threaded 多线程偶发 `database is locked`。
- **修复**：`db.get_db()` 连接 `timeout=15`；`PRAGMA journal_mode=WAL`（不支持时静默回退）；`PRAGMA busy_timeout=15000`。

### 11. create_admin.py 改密自检假失败
- **问题**：重置密码/提升后自检仍用旧用户对象快照，哈希必然不匹配（结果与真实相反）。
- **修复**：重置密码后重查用户，并以数据库中最新哈希做 `bcrypt.checkpw`。

### 12. app.py 模块级副作用
- **问题**：模块级 `app = create_app()` 即建库建表，import app 污染目录。
- **修复**：`create_app(initialize_db=False)`；启动入口（`__main__`、CLI 命令）显式 `init_db(app)`。

## 🟡 测试与文档
- 适配登出改 POST：`test_logout` 断言 GET 405、其余登出调用改 POST。
- `TestConfig` 关闭 CSRF，避免旧 POST 用例全 400。
- 修复后全量 **39 项测试 OK**（含此前新增的四层角色分级用例）。

## 尚未处理（下次继续）
- 启动脚本族协调：`start.bat / manage.py` 与 `start_server.bat` 双套端口、`stop_server.py` 端口写死、健康检查端口写死。
- 文档过期：ROUTES.md（旧 toggle-admin、缺 forum/video/api/avatar）、SCHEMA.md（缺 role/avatar/forum 表）、README 功能表与目录树、CHANGELOG 止于 2.0.1。
- 仓库卫生：video/ 探针脚本、sakurafrp/、根目录 tesseract 手册、.gitignore 未覆盖（logs/、sakurafrp/、static/img/q/*.svg）。
- 补测试：OCR 保存链、CSRF、上传归属、论坛、头像、视频。
- setup_tesseract.py 下载无校验；依赖未锁版本；static/music/ 死资产。
