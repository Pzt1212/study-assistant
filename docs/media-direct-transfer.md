# 视频媒体库：绕过 Cloudflare Tunnel 的直连分块传输

> 适用仓库：`D:\study-assistant`（学习助手 Flask 应用，Windows 部署，
> 网页/API 走 Cloudflare Tunnel）。
>
> 一句话结论：本机**没有公网 IP**，视频字节无法"直连源服务器"。因此本方案
> 采用 Cloudflare 官方推荐的等价做法 —— **浏览器把视频切成小块，直接 PUT 到
> Cloudflare R2 的预签名分块 URL**（R2 全球边缘就近收流），视频数据完全不经过
> 本站、不穿 Tunnel，从根上消除"国内访问绕路海外"；本站（走 Tunnel）只处理
> 登录、建会话、按需签发 URL、记录元数据、异步校验/备份等轻量请求。

---

## 1. 为什么原来慢，现在为什么快

- 网页与 API 走 Cloudflare Tunnel：Tunnel 从本机连接到 Cloudflare 边缘，大陆
  用户访问时数据要在大陆 ↔ 海外边缘 ↔ 本机之间往返，且 Tunnel 是 HTTP 代理，
  大文件吞吐被进一步拖慢 —— 这就是"视频走 Tunnel 极慢"的原因。
- 本方案默认通道 `r2`：浏览器分块直传/直播 **Cloudflare R2**。R2 是对象存储，
  其 S3 兼容端点 `*.r2.cloudflarestorage.com` 在 Cloudflare 全球边缘就近接入，
  大陆用户通常连到香港/日本等最近节点，速度远好于穿 Tunnel 到你家宽带；
  且**字节流不占用你的上行带宽，也不占用 Tunnel 流量**。
- 若日后获得公网 IP / 国内 frp 直连端口，可一键切换 `proxy` 通道回到
  "先传本地、后台异步转存 R2" 的原始方案（后端已完整实现，前端 resumable.js 已就位）。

## 2. 架构总览

```
大陆用户浏览器
   │
   ├─ 网页/API/签名（轻量）──HTTPS──► Cloudflare Tunnel ──► 本站 Flask :5000
   │                                    │                     │ 登录/建会话/签发URL
   │                                    └──（不承载视频字节）   │ 元数据/配额/任务编排
   │                                                          ▼
   ├─ 视频上传（分块 PUT）──直连 HTTPS──► R2 S3 端点（最近边缘）  media_items(记录R2键)
   │    每块 16MiB，预签名 URL，支持断点续传/分块重试            media_chunks(进度)
   ├─ 视频播放（Range GET）──直连 HTTPS──► R2（私有桶+预签名）   ┌── 线程队列(默认) ──┐
   │                                                    ◄──────┤  或 Celery(Linux)  │
   └─ 完成后自动：SHA-256 审计 ──► R2 备份桶（服务端拷贝）◄──────┴────────────────────┘
```

数据流要点：
1. 前端 `POST /media/api/items`（走 Tunnel）→ 服务端调 R2 `CreateMultipartUpload`
   并入库，返回 `uploadId/partSize/partCount`；
2. 前端按需 `POST /media/api/items/<id>/part-urls`（走 Tunnel，只返回几十个小 JSON）
   批量换取分块预签名 PUT URL；
3. 前端把文件 `File.slice` 成小块，用 XHR **直连 R2** 逐个 PUT（不经过本站，
   可并发、可断点：重进页面后 `GET /parts` 从 R2 侧查询已传分块续传）；
4. 全部传完 `POST .../complete`：服务端以 R2 `ListParts` 为权威核对
   分块数/总字节 → `CompleteMultipartUpload` → 入队异步校验与备份；
5. 播放：前端 `GET .../play` 换取私有桶预签名 GET（有效期默认 1h，防盗链），
   直接塞给 `<video>`，R2 原生支持 Range（拖动/续播 206）。

## 3. 本次新增 / 改动文件

| 文件 | 作用 |
| --- | --- |
| `blueprints/media.py` | 媒体库蓝图：页面 + 全部 API（上传会话/续传/签发URL/完成/播放/删除 + proxy 通道） |
| `services/r2.py` | R2（boto3）封装：multipart 预签名、ListParts、complete/abort、播放 URL、桶级备份拷贝、CORS 一键配置 |
| `services/media_files.py` | proxy 通道：分块 Fernet 加密落盘、组装、SHA-256、清理 |
| `services/tasks.py` | 异步任务：线程队列（默认）+ 校验/备份/转存/远程删除 |
| `services/tasks_celery.py` | 可选 Celery 接入（Linux 生产用，函数体复用 tasks.py） |
| `templates/media/index.html` | 媒体库页面（上传/列表/播放器） |
| `static/js/media.js` | 前端引擎：设备自适应、R2 分块直传、resumable 兜底、预签名 Range 播放 |
| `static/vendor/resumable.js` | proxy 通道第三方库（resumable.js 1.1.0，已下载落库） |
| `models.py` / `db.py` | 新增 `media_items`、`media_chunks` 两表及数据访问层 |
| `config.py` | 媒体/R2/异步任务配置（含注释），环境变量可覆盖 |
| `app.py` / `extensions.py` / `templates/base.html` | 注册蓝图、401 JSON 处理器、侧边栏"媒体库"入口 |
| `tools/selfcheck_media.py` | 离线自测（22 项断言，无需 R2/网络） |
| `tools/download_resumable.py` | 重新下载 resumable.js 的备用脚本 |
| `requirements-media.txt` | boto3 / cryptography（celery 可选） |

## 4. 数据库设计（新增，不影响旧表）

`media_items`：一条记录 = 一次上传，存"双重地址"与状态机。

| 列 | 含义 |
| --- | --- |
| id / user_id | 主键 / 属主（外键 users，级联删除） |
| title / filename / mime / ext | 展示标题、原始文件名、类型、扩展名（白名单） |
| size_bytes | 声明的文件总字节 |
| sha256 | 整文件 SHA-256（审计任务流式计算回填） |
| channel | `r2`（浏览器直传）或 `proxy`（本站中转） |
| status | `init → uploading → (promoting →) ready → verifying → backed_up / failed` |
| r2_bucket / r2_key | R2 所在桶与对象键（`media/u<uid>/<uuid>-<name>`，用户隔离） |
| r2_upload_id | 分块上传会话 ID（上传中） |
| part_size / uploaded_bytes | 分块规格 / 已上传进度（续传展示） |
| local_file | proxy 通道本地成品相对路径（云端地址之外的"本地地址"） |
| error | 最近失败原因 |

`media_chunks`：`(item_id, part_number)` 唯一，记录每块大小/ETag/MD5，
支持断点续传与事后审计留痕。

启动时 `db.py` 的 `SCHEMA` 自动 `CREATE TABLE IF NOT EXISTS`，**老库无需手工迁移**。

## 5. 关键配置（config.py，环境变量覆盖）

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| `MEDIA_UPLOAD_CHANNEL` | `r2` | `r2`=浏览器直传 R2；`proxy`=本站中转后异步转 R2（需直连条件） |
| `MEDIA_PLAYBACK_SOURCE` | `r2` | `r2`=预签名直连（默认）；`self`=本站 Range 兜底流（仅本地成品还在时） |
| `MEDIA_PART_SIZE` | 16MiB | 分块大小（R2 下限 5MiB，勿低于） |
| `MEDIA_MAX_SIZE` | 4GB | 单文件上限 |
| `MEDIA_PER_USER_QUOTA_BYTES` | 0 | 个人配额（0=不限） |
| `MEDIA_URL_TTL` | 3600 | 预签名播放链接有效期（秒） |
| `MEDIA_VERIFY_ON_COMPLETE` | 1 | 完成后流式 SHA-256 审计（大文件超过审计阈值自动跳过） |
| `MEDIA_AUDIT_MAX_BYTES` | 2GB | 超过该大小的文件跳过整文件审计 |
| `MEDIA_SPOOL_ENCRYPT` / `MEDIA_FERNET_KEY` | 1 / 自动 | proxy 通道分块 Fernet 加密（自动生成密钥到媒体根目录） |
| `MEDIA_KEEP_LOCAL` | 1 | proxy 转存 R2 成功后是否保留本地原文件（1=双重地址；0=仅云端） |
| `R2_ACCOUNT_ID` | - | Cloudflare 账号 ID（R2 概览页） |
| `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | - | R2 API 令牌（对象读+写，见下） |
| `R2_BUCKET` | `study-media` | 主桶（视频本体） |
| `R2_BACKUP_BUCKET` | 空 | 备份桶（同账号；留空=只校验不另存） |
| `R2_ENDPOINT_URL` | 自动拼 | 一般无需设置 |
| `MEDIA_ASYNC_ENGINE` | `thread` | `thread`=内置线程队列（Windows 默认）；`celery`=标准 Celery |
| `MEDIA_ASYNC_WORKERS` | 2 | 线程 worker 数 |

## 6. 部署步骤（沿用现有 Windows + Tunnel 环境）

### 6.1 安装依赖（本机已执行）
```bat
pip install -r requirements-media.txt
```

### 6.2 创建 R2 桶与令牌（约 5 分钟，Cloudflare 控制台）
1. 控制台 → **R2** → 创建两个桶：`study-media`（主）、`study-media-backup`（备份，可选）；
2. 控制台 → 我的个人资料 → **API 令牌 → 创建令牌**，权限模板选
   **"对象读与写"**，资源范围限定到上面两个桶；
   记下 `Access Key ID` / `Secret Access Key`；
3. R2 概览页记下 **账号 ID**（account id）。

### 6.3 配置 CORS（浏览器跨域直传 R2 的必需步骤，一次性）
主桶必须允许你的 Tunnel 域名跨域。启动服务后执行（任选其一）：
```python
# 方式 A：用项目自带的封装
python -c "from app import create_app; a=create_app(initialize_db=False); \
import os; os.environ.setdefault('R2_ACCOUNT_ID','你的账号ID'); \
os.environ.setdefault('R2_ACCESS_KEY_ID','你的Key'); \
os.environ.setdefault('R2_SECRET_ACCESS_KEY','你的Secret'); \
from flask import current_app; \
with a.app_context(): \
  from services import r2; print(r2.ensure_bucket_cors(['https://你的公网域名']))"
```
或方式 B：在 R2 桶 → 设置 → CORS 手动粘贴：
```json
{
  "CORSRules": [
    { "AllowedOrigins": ["https://你的公网域名"],
      "AllowedMethods": ["GET", "PUT", "HEAD", "POST", "DELETE"],
      "AllowedHeaders": ["*"],
      "ExposeHeaders": ["ETag", "x-amz-request-id", "x-amz-checksum-crc64nvme"],
      "MaxAgeSeconds": 3600 }
  ]
}
```
> `AllowedHeaders: ["*"]` 与允许的源为浏览器签名所需，不影响其它对象安全
> （预签名 URL 本身是带时效的 bearer 凭据）。

### 6.4 写入环境变量
本项目不读 `.env`，请按现有习惯设置系统环境变量或写入启动脚本
（`start_server.bat` / `tools/run_server.py` 前的环境注入处），示例：
```bat
setx R2_ACCOUNT_ID "你的账号ID"
setx R2_ACCESS_KEY_ID "你的AccessKey"
setx R2_SECRET_ACCESS_KEY "你的Secret"
setx R2_BUCKET "study-media"
setx R2_BACKUP_BUCKET "study-media-backup"
rem 如域名是 https://你的域名，建议加（供生成绝对地址/分享链接等）：
setx PUBLIC_BASE_URL "https://你的域名"
```
> 新开终端/setx 后重启服务进程才生效。生产务必同时设置 `SECRET_KEY`
>（应用现有规则：production 下缺失会拒绝启动）。

### 6.5 重启并自检
```bat
python tools\selfcheck_media.py        :: 离线自测 22 项（不依赖 R2/网络）
```
重启服务（`stop_server.bat` + `start_server.bat`）与 Tunnel，浏览器打开
`https://你的域名/media` 登录后：
1. 顶部应显示"通道：R2 直传 · 分块 16.0 MB …"；
2. 拖入一个视频 → 观察分块进度条（并发：手机 1 / 电脑 3，可在"自动/手机/电脑"切换）；
3. 上传完成状态流转 `上传中 → 就绪/校验中 → 已备份`（校验/备份为后台异步）；
4. 点"播放"应流畅拖动（Range 206）；URL 过期后前端自动续签并从原位置续播。

## 7. 两种上传通道怎么选

### 7.1 `r2`（默认，推荐当前部署）
- 优点：字节不占本站带宽、不经 Tunnel；上传与播放都走 R2 边缘；断点续传原生；
- 前提：仅需"本站能访问 R2 API"（现在就能用）。
- 注意：上传/播放的是 **R2 对象**，不是服务器磁盘；本地不再存整文件
  （`data/media_store` 仅 proxy 通道使用）。

### 7.2 `proxy`（拿到公网 IP / 国内 frp 直连端口后启用）
- 设置 `MEDIA_UPLOAD_CHANNEL=proxy`，并把**仅媒体通道**的端口用防火墙放行
  （不建议整站 0.0.0.0 裸奔；可用下方 Nginx 只反代 `/media/api/proxy/*` 与
  `/media/api/items/*/stream`）。
- 前端自动改用 `resumable.js` 分块 POST 到本站 → 本地 **Fernet 加密落盘** →
  齐了组装 → 后台线程/Celery 整体转存 R2 → （可选）删本地。
- 该通道保留了"本地 + 云端"双重地址语义，代价是需要用户可直连本站。

## 8. 播放与防盗链（现状与边界，务必读）

- **默认防盗链**：R2 桶保持私有；播放 URL = 服务端按"登录用户 + 属主校验 +
  对象键"签发的**预签名 GET**，带有效期（默认 1h）。链接外泄也只在该时段有效；
  对象键含用户目录（`media/u<uid>/…`），不同用户互不可见。
- **播放中途 URL 过期**：前端自动重新取链接并从 `currentTime` 续播（Range）。
- **"自适应码率"边界（诚实说明）**：本方案**不转码**，文件只有一份原始码率，
  不存在多档位可"自动切码率"。所谓自适应 = 按设备调整上传并发 + 断点续播。
  若确需多码率 HLS，需引入 ffmpeg 转码管道（见 CHANGELOG/后续规划），本版本未内置。
- 本站 `self` 源（本地 Range 流）仅作 proxy 兜底，走 Tunnel 会慢，勿作主力。

## 9. 异步任务与运维

- 默认 `MEDIA_ASYNC_ENGINE=thread`：进程内 daemon 线程（数=MEDIA_ASYNC_WORKERS），
  Windows 无 Redis 开箱即用；任务失败写 `logs`/标准错误，状态回写 `media_items.error`。
- Linux 生产换 Celery：`pip install celery redis`，设
  `MEDIA_ASYNC_ENGINE=celery`、`CELERY_BROKER_URL`，并启动
  `celery -A services.tasks_celery:celery_app worker -l info -P solo`。
- 任务一览：`media.verify`（审计）→ `media.backup`（主桶→备份桶服务端拷贝，
  不占本站带宽）→ `media.promote`（proxy 本地成品转 R2）→
  `media.delete_remote`（删除主/备对象，删除接口即时响应、清理在后台）。
- 页面"删除"：删 DB 行 + 本地文件 + 异步删 R2 主/备对象；
  上传中删除会先 abort 分块会话。
- 备份即"主桶→备份桶"服务端拷贝（同账号）。若未来要异地容灾，可把备份桶
  换到另一账号（需扩展 r2.copy 支持第二组凭据，按需联系）。

## 10. Nginx 示例（Linux 生产 / 将来暴露直连端口时）

见同目录 `media-nginx-example.conf`。核心：对 proxy 分块与本地流关闭缓冲、
放开 body 上限；对 R2 直传场景 Nginx 不碰媒体字节，仅反代 API。

## 11. 常见问题排查

| 现象 | 处理 |
| --- | --- |
| 上传第一步就报"R2 未配置完整" | 检查 R2_ACCOUNT_ID / ACCESS_KEY / SECRET 是否注入并重启服务 |
| 上传时报 403 SignatureDoesNotMatch | 令牌权限不够或桶名不符；确认令牌范围含主/备桶 |
| 跨域报 CORS | 执行 §6.3 一键 CORS 后等待 1 分钟生效 |
| 播放几分钟后停 | 预签名过期，前端自动续签；确认 `MEDIA_URL_TTL` 足够（默认 3600s） |
| 拖入文件无反应/报"文件超过上限" | 检查扩展名白名单与 `MEDIA_MAX_SIZE` |
| proxy 通道分块 413 | 已按路径放开 `request.max_content_length`；若前面还有 Nginx，参照示例配置 |
| 状态停在 verifying / 失败(error 含审计) | 查看页面 error 列；R2 侧对象可能被改，用 `.../verify` 重跑或删除重传 |
| 删除后 R2 仍有对象 | 删除是异步任务，稍等并看日志；若失败手动在 R2 控制台清理 |

## 12. 安全设计自检清单

- [x] 传输加密：全程 HTTPS（Tunnel 域名 + R2 端点）
- [x] 接口鉴权：现有登录会话 + 全站 CSRF（X-CSRFToken）；API 未登录返回 JSON 401
- [x] 对象隔离：`media/u<uid>/…` 键空间 + 属主校验（管理员例外）
- [x] 防盗链：私有桶 + 预签名 + 有效期 + 续期续播
- [x] 数据加密：proxy 分块 Fernet 落盘；R2 侧由 Cloudflare 托管加密
- [x] 完整性：分块编号/总字节核对 + 整文件 SHA-256 流式审计（可配阈值）
- [x] 配额与白名单：扩展名白名单、单文件上限、个人配额
- [x] 失败可见：状态机 + error 字段 + 任务日志
