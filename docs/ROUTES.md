# 路由清单 (ROUTES)

所有路由均位于应用根路径。除标注外，页面路由均需登录（`@login_required`）。

## 认证 (blueprints/auth.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/register` | 用户注册（未登录可访问） |
| GET/POST | `/login` | 用户登录（未登录可访问） |
| GET | `/logout` | 退出登录 |

## 仪表盘 (blueprints/main.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 仪表盘首页（今日番茄、笔记数、题目数、正确率） |
| GET | `/api/health` | 健康检查（JSON，无需登录，供监控/内网穿透探测） |
| GET | `/healthz` | 极简存活探测（纯文本 ok，无需登录） |

## 番茄钟 (blueprints/pomodoro.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/pomodoro` | 番茄钟页面 |
| POST | `/pomodoro/record` | 记录完成的番茄（JSON） |
| GET | `/pomodoro/api/stats` | 今日完成数 + 最近 7 天统计（JSON） |

## 计时器 (blueprints/timer.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/timer` | 计时器页面（逻辑在前端） |

## 音乐播放器 (blueprints/music.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/music` | 音乐播放器页面 |
| GET | `/music/api/tracks` | 曲目列表（JSON） |

## 笔记 (blueprints/notes.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/notes` | 笔记列表（支持 `?q=` 过滤） |
| GET/POST | `/notes/new` | 新建笔记 |
| GET | `/notes/<id>` | 笔记详情 |
| GET/POST | `/notes/<id>/edit` | 编辑笔记 |
| POST | `/notes/<id>/delete` | 删除笔记 |
| GET/POST | `/notes/upload` | 上传文件并提取文本 |
| GET | `/notes/files/<filename>` | 访问上传的文件（图片预览等） |

## 文字识别 (blueprints/ocr.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/ocr` | OCR 页面（POST 上传图片识别） |
| POST | `/ocr/save` | 将识别/修正的文本保存为笔记 |

## 题库 (blueprints/questions.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/questions` | 题目列表（支持 `?subject=`、`?topic=`、`?type=`、`?difficulty=`、`?q=` 过滤） |
| GET/POST | `/questions/new` | 新增题目 |
| GET/POST | `/questions/<id>/edit` | 编辑题目 |
| POST | `/questions/<id>/delete` | 删除题目 |
| GET | `/questions/quiz` | 刷题模式页面（支持选择/填空/解答三种题型） |
| GET | `/questions/api/random` | 随机抽题（JSON，不含答案；支持 `?type=选择题/填空题/解答题` 过滤，缺省混合抽取） |
| POST | `/questions/api/answer` | 提交答案判分（选择题/填空题自动判分；解答题返回参考答案+评分标准） |
| POST | `/questions/api/grade` | 解答题自评得分（记录用户解答与自评得分） |

## 全局搜索 (blueprints/search.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/search?q=关键词` | 搜索结果页（笔记/题目分组） |

## 后台管理 (blueprints/admin.py，仅管理员)

以下路由均需管理员身份：先登录，再校验 `is_admin`，非管理员返回 403。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin` | 概览页（用户/题目/笔记/答题记录/番茄记录统计） |
| GET | `/admin/users` | 用户管理列表（含各自内容量，支持 `?q=` 过滤） |
| POST | `/admin/users/<id>/toggle-admin` | 设为 / 取消管理员（至少保留 1 名管理员） |
| POST | `/admin/users/<id>/delete` | 删除用户（级联删除其全部数据，不能删自己） |
| GET | `/admin/questions` | 全站题目管理（支持 `?subject=`、`?q=` 过滤） |
| POST | `/admin/questions/<id>/delete` | 删除任意用户的题目 |
| GET | `/admin/notes` | 全站笔记管理（支持 `?q=` 过滤） |
| POST | `/admin/notes/<id>/delete` | 删除任意用户的笔记（同时清理上传文件） |
| GET | `/admin/ocr-status` | OCR 服务状态页（各引擎与配置情况） |

## 在线题库 (blueprints/question_bank.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/question-bank` | 在线题库首页（内置科目勾选 + wkapi 查询表单） |
| POST | `/question-bank/import` | 导入题目到当前用户题库（内置 free / wkapi 两种来源） |

## 静态资源

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/static/css/style.css` | 全局样式 |
| GET | `/static/js/*.js` | 前端脚本 |
| GET | `/static/music/*.wav` | 占位音乐文件（可替换） |
