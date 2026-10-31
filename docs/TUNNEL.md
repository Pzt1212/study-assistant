# Cloudflare Tunnel 内网穿透说明 (TUNNEL)

让外网 / 手机通过公网 HTTPS 地址访问本机「学习助手」，使用 Cloudflare 官方免费隧道方案。

## 快速开始（默认：临时域名，免登录）

```bat
:: 1) 先启动本机服务（若未启动）
start_server.bat        rem 监听 127.0.0.1:5000

:: 2) 启动隧道
tunnel_start.bat        rem Quick Tunnel，免登录
```

启动后约 3~5 秒，Cloudflare 会分配一个形如
`https://xxxx-xxxx-xxxx.trycloudflare.com` 的临时公网地址。
运行 `tunnel_status.bat` 可自动提取该地址并做公网健康检查。

> 说明：
> - 临时域名**每次启动都会变化**，且免费账户级隧道无 SLA，仅供体验/联调；
> - 需要固定域名时请看下文「自定义域名 / 命名隧道」。

## 隧道启动命令

| 用途 | 命令 |
|------|------|
| 一键启动（后台） | 双击 `tunnel_start.bat` |
| 查看状态 + 提取公网地址 + 健康检查 | 双击 `tunnel_status.bat` |
| 停止隧道 | 双击 `tunnel_stop.bat` |

相关文件：

```
tunnel/
├── cloudflared.exe      # cloudflared 可执行文件（官方 GitHub Release，已加入 PATH）
├── config-quick.yml     # Quick Tunnel 参考配置
├── config-named.yml     # 命名隧道配置模板（占位，不含凭据）
├── launch.ps1           # 后台启动器（Quick / Named 两模式）
├── named_tunnel.py      # 命名隧道启动器（登录校验/创建/route/spawn）
└── logs/                # 运行日志 tunnel.out.log / tunnel.err.log + tunnel.pid
```

## 查看隧道状态

- 运行 `tunnel_status.bat`：显示
  - cloudflared 进程是否运行（PID）；
  - 日志末尾；
  - 从日志提取的公网地址（`https://...trycloudflare.com`）；
  - 公网健康检查（请求 `{公网地址}/api/health`）。
- 也可直接看日志：
  ```bat
  type tunnel\logs\tunnel.err.log
  ```
- 命令行原生方式：
  ```bat
  cloudflared tunnel list                    rem 命名隧道列表
  cloudflared tunnel info study-assistant    rem 隧道信息
  ```

## 停止隧道

- `tunnel_stop.bat`：优先按 `tunnel\logs\tunnel.pid` 精确结束进程；
  无 PID 文件时按进程名 `cloudflared.exe` 兜底。
- 命令行原生方式：
  ```bat
  cloudflared tunnel stop study-assistant    rem 优雅停止命名隧道
  ```

## 自定义域名 / 命名隧道（固定地址）

前提：域名已托管在 Cloudflare 账户（Nameserver 指向 Cloudflare）。

### 1) 登录授权（仅首次，需浏览器）

```bat
cloudflared tunnel login
```

浏览器会自动打开 Cloudflare 授权页；登录并选择站点后授权，
cloudflared 会把 `cert.pem` 写入用户目录 `%USERPROFILE%\.cloudflared\`。

### 2) 创建命名隧道（仅首次）

```bat
cloudflared tunnel create study-assistant
```

创建后会在 `%USERPROFILE%\.cloudflared\` 生成 `<隧道UUID>.json` 凭据文件
（仅保存在用户目录，项目内不存放 Token）。

### 3) 绑定域名并启动

```bat
set TUNNEL_DOMAIN=study.example.com   rem 换成你的域名
tunnel_start.bat
```

脚本会调用 `tunnel\named_tunnel.py`，自动完成：
- 校验已登录；
- 复用/创建名为 `study-assistant` 的隧道；
- 生成 `tunnel\config-named-active.yml`（仅含域名与本地地址，无任何 Token）；
- 执行 `cloudflared tunnel route dns study-assistant study.example.com`（幂等，
  在 Cloudflare DNS 中添加 CNAME 指向隧道）；
- 后台启动并写入 PID / 日志。

绑定成功后访问：`https://study.example.com`

> 需要等 DNS 生效（通常 1~5 分钟）。也可改用
> `set TUNNEL_DOMAIN=xxx.trycloudflare.com` 获得固定命名的 trycloudflare 地址。

### 4) 其它常用命令

```bat
cloudflared tunnel list                 rem 查看隧道与 UUID
cloudflared tunnel route dns study-assistant study.example.com   rem 手动配 DNS
cloudflared tunnel run study-assistant  rem 前台运行命名隧道
```

## 配置说明

- 应用侧环境变量（可选，公网发布建议）：`PUBLIC_BASE_URL=https://你的域名`、
  `TRUST_PROXY_HEADERS=1`（详见 `docs/DEPLOY.md`）。
- 项目运行入口始终为 `http://127.0.0.1:5000`（`config.APP_HOST/APP_PORT` 可覆盖，
  隧道启动脚本默认指向 5000）。
- cloudflared 会在用户目录生成 `~/.cloudflared/cert.pem` 与隧道凭据 JSON；
  项目内所有配置与脚本均**不写入 API 令牌 / Tunnel Token / Cookie / 私钥**。

## 故障排查

| 现象 | 处理 |
|------|------|
| status 显示公网不可达 | 确认本机 `start_server.bat` 已运行；`tunnel_status.bat` 会做公网健康检查 |
| 未分配 trycloudflare 地址 | 稍等 3~5 秒再看；检查日志 `tunnel\logs\tunnel.err.log` |
| 提示端口被占用 / PID 残留 | 先 `tunnel_stop.bat`；仍不行删除 `tunnel\logs\tunnel.pid` |
| 想换回临时域名 | 删除环境变量 `TUNNEL_DOMAIN` 后运行 `tunnel_start.bat` |
