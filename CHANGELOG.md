# 更新日志 (CHANGELOG)

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/) 规范，格式参考
[Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [1.1.0] - 2026-11-06

### 新增（单机桌面版 · 免安装 exe）
- **`standalone.py`**：单机单人版启动入口。数据（SQLite / uploads / logs / 媒体存储）全部重定向到
  exe 旁目录，整个文件夹复制到任意位置即可运行、删除即完全卸载；首次启动自动创建管理员账号
  （默认 `user` + 随机 6 位密码，写入 `data/账号信息.txt`），此后 `before_request` 自动登录、
  注册入口返回 403 以保持单用户；启动后自动打开系统默认浏览器。
- **端口与实例管理**：5000 被占用时先请求 `/api/health`——若已是本程序则直接打开浏览器而不重复启动，
  否则自动顺延到 5001+ 的可用端口；控制台会打印实际访问地址。
- **`packaging/standalone.spec`**：PyInstaller **onedir** 打包，把 `templates/`、`static/`、
  内置 Tesseract（中英文印刷体 OCR）打进 `_internal`；图标为新增的 `static/img/app_icon.ico`。
  onedir 启动快、杀软误报率低于 onefile，保留控制台窗口便于查看日志。
- **随包 `使用说明.txt`**：面向普通用户的下载、启动、账号、数据目录、常见问题与版本差异说明。

### 变更（界面重设计）
- **去掉分组侧边栏**：`templates/base.html` 改为「独立控件顶栏」（品牌 / 搜索 / 设置 / 头像 / 退出各自独立）；
  `templates/dashboard.html` 重写为问候区 + 4 张 KPI 卡 + 全部功能独立按钮网格，番茄钟为双倍宽主瓦片；
  `static/css/style.css` 追加 v3 样式段（`--c` 变量 + `color-mix`，图标色块自动适配暗色主题）。
- `templates/video/index.html` 移除已废弃的面包屑 block。

### 文档
- **README 顶部「下载与运行指南」改写**：不再声称「暂不提供 exe」，改为「单机桌面版 / 源码版」双入口，
  新增「单机桌面版（免安装 exe）」章节（下载、使用、特性、目录、账号重置、与源码版差异）。
- README 功能表、目录结构、环境变量表、技术栈表同步补充桌面版条目；界面预览注明截图拍摄于 v1.0.x 布局。
- README「单机桌面版」章节增加「从源码自行打包」折叠小节（构建命令、依赖、隐私检查、Release 分发说明）；
  新增 `packaging/使用说明.txt` 作为随包用户说明的源文件。

### 说明
- 打包产物（`学习助手-单机版.zip`，约 227 MB）**不纳入 git 仓库**（GitHub 单文件上限 100 MB），
  改由 **GitHub Release** 分发；仓库只保留可复现打包的源码与配置。

---

## [1.0.1] - 2026-10-31

### 修复（Windows 启动链路 · 致命）
- **`start.vbs` / `start_silent.vbs` 双击后完全无反应**：脚本以 UTF-8（无 BOM）保存且含中文注释，
  Windows Script Host 按 ANSI/GBK 解析导致字节错位，脚本静默失败、连报错都没有。
  已改为 **UTF-16LE + BOM** 保存。
- **`stop.bat` 无法停止服务**：`.bat` 为 LF 行尾 + UTF-8，cmd.exe 逐行解析时把 `if (...)` 块拆断，
  报「'件优先，端口' 不是内部或外部命令」；`start.bat` 同样受影响。已改为 **GBK + CRLF** 保存。
- **解释器探测路径多一层目录**：`%LOCALAPPDATA%\Local\Python\...` 指向不存在的路径，
  导致找不到 `pythonw.exe`。修正为 `%LOCALAPPDATA%\Python\...`（影响 5 个 `.bat`）。

> 以上三项叠加的后果是：按 README 双击启动会毫无反应，且无法用 `stop.bat` 收场。
> v1.0.1 已逐项实测：启动 → `/api/health` 返回 200 → `stop.bat` 停止 → 端口释放、PID 清理。

### 修复（前端与文档）
- **移除 Google Fonts 外链**：`templates/base.html` 与 `static/js/settings.js` 引用的
  `fonts.googleapis.com` 在国内会阻塞首屏渲染。删除后真正做到零 CDN 依赖，
  字体回退到系统字体栈（`--font` 原本就有回退）。
- **README 克隆地址**：`your-username` 替换为实际仓库地址；`docs/CONTRIBUTING.md` 两处同步修正。
- **README 截图说明**：删除"演示数据（`demo` 账号）"的表述——项目并不会自动创建该账号，
  改为"项目本地运行效果"，并补充注册与管理员提权指引。
- **README 启动说明**：入口更新为 `scripts\start.vbs`，与目录结构保持一致。
- **README 新增「下载与运行指南」**：说明 `Download ZIP` 只含源码、不含 exe。

### 修复（管理后台）
- **OCR 状态页**：在线题库区块仍写着旧 `wkapi` 与 `api.wkexam.com`；同步为"自带 API"，
  展示已配置的接口地址与令牌状态。

---

## [1.0.0] - 2026-10-31

首个开源版本。包含番茄钟、计时器、背景音乐、题库与刷题、笔记（文本/手写双模式）、
OCR（印刷体/手写体）、论坛、全局搜索、管理后台、本地视频与媒体库。

> 说明：开源版本从 `v1.0.0` 起重新编号；下方 `2.x` 条目为开源前的内部开发记录。

---
## [2.1.0] - 2026-09-09

### 新增（视频媒体库 · 绕过 Tunnel 的直连分块传输）
- **媒体库页面 `/media`**：视频/音频上传（拖拽/选择）+ 我的媒体列表 + 播放器；
  侧边栏新增「媒体库」入口（`blueprints/media.py`、`templates/media/index.html`）
- **无公网 IP 的"直连"方案**：浏览器把文件切成 16MiB 小块直接 PUT 到 Cloudflare
  R2 预签名分块 URL（S3 multipart），视频字节不再走 Tunnel/绕路海外；本站只负责
  登录、建会话、按需签发 URL、记录元数据（`services/r2.py`、`static/js/media.js`）
- **断点续传/分块校验**：`media_chunks` 进度表 + R2 ListParts 权威核对 +
  整文件 SHA-256 流式审计（异步）；完成态自动入队备份（主桶→备份桶服务端拷贝）
- **proxy 备用通道**：`MEDIA_UPLOAD_CHANNEL=proxy` 时前端改走 resumable.js
  分块 POST 到本站（`static/vendor/resumable.js` 已落库），本地 Fernet 加密落盘、
  组装后异步整体转存 R2（满足将来公网 IP / 国内 frp 直连场景）
- **设备自适应**：前端自动/手机/电脑三态手动切换（影响上传并发），所见即所感
- **防盗链播放**：私有桶 + 预签名（TTL）+ 用户目录键隔离；URL 过期自动续签续播
- **异步任务双引擎**：内置线程队列（Windows 免 Redis，`MEDIA_ASYNC_ENGINE=thread`）
  + Celery 兼容（`services/tasks_celery.py`）；`requirements-media.txt` 单独装依赖
- **运维与自检**：`tools/selfcheck_media.py` 离线自测 22 项断言（无需 R2/网络）；
  `docs/media-direct-transfer.md` 部署文档 + `docs/media-nginx-example.conf` 示例

### 变更
- `extensions.py`：新增 `unauthorized_handler`（`/media/api/*` 未登录返回 JSON 401，
  页面行为不变）；`app.py` 注册媒体蓝图并启动异步任务；`db.py` 新增两表
  （老库启动自动建表，无需手工迁移）；`config.py` 新增 `MEDIA_*`/`R2_*` 配置

### 测试
- `tools/selfcheck_media.py` 22 项通过（页面/会话/分块/组装/审计降级/Range 206/删除）
- 既有项目测试套件回归通过（见 `tools/run_project_tests.py`）

## [2.0.0] - 2026-09-04

### 新增（模块化改造）
- **刷题筛选器**：`/questions/quiz` 增加学科 / 难度 / 题型三个下拉筛选框，
  切换即自动抽题；`/questions/api/random` 支持 `subject+difficulty+type` 组合过滤，
  无符合条件题目时给出友好提示（`models.get_random_question` 扩展筛选参数）
- **笔记手写板**：笔记编辑页「文本 / 手写」双模式；Canvas 手写支持颜色 / 粗细 /
  橡皮擦 / 撤销 / 清空；保存时序列化为内嵌 SVG（含笔迹 JSON 注释）写入 content，
  file_type 标记为 `svg`，详情页渲染 SVG 画板；后端对 SVG 做 XSS 净化；
  手写笔记可一键切回纯文本
- **手写 OCR**：`/ocr` 增加「印刷体 / 手写体」选项；手写体优先本地插件
  rapidocr-onnxruntime（新增 `services/handwriting_ocr.py` + `requirements-handwriting.txt`），
  缺失时自动降级 Tesseract(psm6) 或给出友好提示
- **音乐升级**：不再读取本地 static/music/；改为「在线轻音乐」（SoundHelix 流式直链，
  `MUSIC_STREAM_URLS` 可覆盖）＋「脑波音频」（双耳节拍，前端 Web Audio 本地合成、离线可用）
  两类，含分类筛选 / 搜索 / 来源标识 / 播放失败提示（`services/music_source.py` 新增）
- **OCR 本地打包**：引擎自动解析优先级 = `TESSERACT_CMD` → 项目内置
  `bin/tesseract/tesseract.exe` → 系统 PATH；`tools/setup_tesseract.py` 一键下载内置
  安装包与中文语言包（走 GitHub Release 资产）
- **管理后台美化**：面包屑导航（当前页高亮）、统计卡片图标化（分类强调色）、
  表格/按钮/搜索框样式打磨，OCR 状态页新增手写插件与内置引擎状态
- **环境与运维**：`requirements.txt` 整理注释与可选依赖；`tools/check_env.py` 环境自检；
  `tools/verify_data.py` 数据完整性与联动验证；`manage.py`（start/stop/status/log/restart）、
  `start.bat` / `stop.bat` / `start.vbs` / `start_silent.vbs` 一键后台启动
  （pythonw 无窗口，日志 `logs/app.log`，PID `logs/app.pid`，端口查杀兜底）

### 变更
- `app.py` 不再启动时生成占位音乐文件（曲目改为服务端目录驱动）
- `tools/run_server.py` / `stop_server.py` / `status_server.py` 支持
  `APP_LOG_FILE` / `APP_PID_FILE` / `APP_PORT` 环境变量
- `notes` 蓝图新增 `_editor_type` / `_sanitize_svg_content`；
  `models.update_note` 支持更新 file_type；`models.get_random_question` 扩展筛选

### 测试
- 全部既有 37 项单元测试通过；新增 `tools/verify_data.py` 51 项联动验证
  （五科各 500 题、筛选组合、手写 SVG 保存/XSS/切换文本、OCR 选项降级、音乐双分类、
  管理页面包屑）

## [2.0.1] - 2026-09-04

### 修复 / 增强
- **内置 Tesseract 引擎落地**：`bin/tesseract/` 现已包含可开箱即用的
  Tesseract 5.4.0.20240606（tesseract.exe + libtesseract-5.dll + 全套依赖 DLL），
  `tessdata/` 含 chi_sim + eng 语言包；`services.ocr_service.resolve_tesseract_cmd()`
  自动发现该目录，印刷体 OCR 无需任何系统安装即可使用
- `tools/setup_tesseract.py` 升级为多通道下载：GitHub Release 主链 + ghfast.top /
  gh-proxy.com / ghproxy.net / gh.ddlc.top 镜像回退；语言包走 jsdelivr CDN +
  GitHub 镜像；已实测下载与静默安装流程
- 端到端验证：内置引擎自动发现 → pytesseract 版本 5.4.0 → 中英文图片识别
  （chi_sim「学习助手OCR」识别正确），环境自检核心失败 0 项

## [1.4.0] - 2026-09-03

### 新增
- 管理端独立界面（admin console）：深色侧边栏 + 顶栏布局
  `templates/admin/base_admin.html` + `static/css/admin.css` + `static/js/admin.js`，
  移动端抽屉导航；`/admin` 下 5 个页面（数据概览 / 用户 / 题目 / 笔记 / OCR 状态）
  全部改为管理端布局
- 管理端数据概览增强：最近 7 天全站专注柱状图、最新注册用户列表；
  全站题目/笔记列表展示作者用户名（`LEFT JOIN users`）

### 修复
- 修复 OCR 状态页在线题库配置键不一致（原为 `OPENTDB_ENABLED`，与在线题库实现脱节）
- 在线题库配置统一：`config.py` 以 `WKAPI_ENABLED` 控制 wkapi 在线题库开关，
  兼容识别旧环境变量 `OPENTDB_ENABLED`；状态页 / 文档同步更新
- 登出入口兼容 POST 请求（GET 链接与 POST 表单均可退出）
- 修复单元测试：数据层调用补充 `app_context`（AdminTests / QuestionBankTests）；
  QuestionBank 用例整体重写为 wkapi 实现（内置导入、wkapi mock 导入、禁用开关、
  未知来源、服务层反转义/嵌套结构/异常处理/字段标准化）

## [1.3.0] - 2026-09-02

### 新增
- 一键后台运行：`start_server.bat`（无窗口后台启动，日志 `logs/server.log`）、
  `stop_server.bat`、`status_server.bat`；对应入口 `tools/run_server.py` /
  `tools/stop_server.py` / `tools/status_server.py`（PID 文件防重复启动）
- 管理员工具 `tools/create_admin.py`：创建/提升管理员（默认随机强密码，
  支持 `--username/--password/--email`），含密码自检
- 对外发布 / 内网穿透预留：`config.py` 新增 `APP_HOST` / `APP_PORT` /
  `PUBLIC_BASE_URL` / `TRUST_PROXY_HEADERS`（可信代理 ProxyFix）；
  `app.py` 按配置监听并支持可信反代头；无需登录的健康检查接口
  `GET /api/health` 与 `GET /healthz`
- 文档 `docs/DEPLOY.md`：后台运行、健康检查、内网穿透（ngrok/cpolar/frp）与
  Nginx 反代示例、公网发布安全检查清单

## [1.2.0] - 2026-09-02

### 新增
- 刷题模式支持三种题型（选择题 / 填空题 / 解答题）：
  - 随机抽题接口支持 `?type=选择题|填空题|解答题` 按题型过滤，缺省全题型混合抽取
  - 选择题单选自动判分；填空题文本作答（去除首尾空白、支持「或」连接的等价答案）自动判分
  - 解答题先展示参考答案 + 解析 + 评分标准（step_rules），再由用户自评得分
    （新增 `POST /questions/api/grade` 接口；自评满分视为做对并计入统计）
- 前端刷题页动态渲染：选择题选项按钮 / 填空题输入框 / 解答题文本框 + 评分标准与自评控件，
  并提供「全部/只抽某题型」的题型过滤下拉框与「换一道」按钮
- questions 表结构扩展入库列：`topic` / `grade` / `question_type` / `difficulty` /
  `score` / `step_rules`；answer_records 增加 `score` 列（题目得分/自评得分）；
  建表 SQL（db.py）与旧库轻量迁移同步支持上述列
- 初中全科题库生成器 `tools/build_question_bank.py`：数学/物理/化学/英语/语文各 500 道，
  混合题型、难度 简单30%/中等50%/较难20%，带答案/解析/评分标准，直接写入
  data/study_assistant.db（默认清空旧题、归属 user_id=1），含多轮配额纠偏与数据校验

### 测试
- 新增 `QuizExtendedTests`：按题型随机抽题、填空判分、解答题自评与答题记录落库用例

## [1.1.0] - 2026-09-01

### 新增
- 后台管理（/admin）：全站概览统计、用户管理（设为/取消管理员、删除用户）、
  全站题目管理、全站笔记管理（删除时清理上传文件）、OCR 服务状态页
- 用户表 `is_admin` 字段与旧库轻量迁移（PRAGMA table_info 检查列，ALTER TABLE 补列，不丢数据）
- `admin_required` 管理权限装饰器（先登录后校验管理员，非管理员 403）
- Flask CLI 命令 `flask --app app create-admin <用户名>` 快捷设置管理员
- 免费在线题库（/question-bank）：内置 36 道题（数学/英语/语文/Python/历史/计算机基础）
  + Open Trivia Database 在线拉取（HTML 反转义、选项乱序、按分类/难度导入）
- OCR 免费在线引擎：OCR.space 与百度智能云 OCR（`OCR_PROVIDER` 切换，本地仍为默认），
  缺失密钥时友好提示
- 配置项：`OCR_PROVIDER` / `OCRSPACE_API_KEY` / `BAIDU_OCR_API_KEY` /
  `BAIDU_OCR_SECRET_KEY` / `OPENTDB_ENABLED`

### 修复
- 修复单元测试 `test_login_required` 已知 bug（缺少 `follow_redirects=True` 导致断言失败）

### 测试
- 新增后台管理测试（权限 403、用户管理、删除保护、OCR 状态页）
- 新增在线题库测试（内置导入、在线导入 mock、HTML 反转义与标准化）

## [1.0.0] - 2026-09-01

### 新增
- 用户系统：注册 / 登录 / 退出，bcrypt 单向加密存储密码，Flask-Login 会话管理
- 番茄钟：专注 / 短休息 / 长休息三模式，时长自定义，每日完成数统计
- 计时器：秒表（正计时）与倒计时双模式
- 背景音乐播放器：播放 / 暂停 / 上下一首 / 音量 / 循环模式，内置 3 首占位曲目
- 题库：题目的增删改查、按科目浏览、刷题模式（随机抽题 + 即时判分 + 解析）、答题统计
- 笔记：上传（txt/md/图片）、自动提取文本、在线编辑、删除
- OCR 文字识别：本地 pytesseract + Pillow，缺依赖友好提示，预留在线 API 配置位
- 全局搜索：笔记标题/内容、题目题干/解析、科目名，分组展示
- 数据存储：SQLite，多表外键关联用户，启动时自动建表
- 开源合规：MIT 许可证、README、CONTRIBUTING 指引、.gitignore、单元测试
