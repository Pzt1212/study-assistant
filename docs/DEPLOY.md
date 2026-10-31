# 运行管理与对外发布说明 (DEPLOY)

本文说明如何：后台运行服务、用健康检查探测存活、做内网穿透、以及预留的对外发布配置。

## 1. 两种运行方式

| 方式 | 命令 | 适用场景 |
|------|------|---------|
| 开发前台 | `python app.py` | 日常开发（自动重载，debug 开） |
| 后台运行 | 双击 `start_server.bat`，或 `python tools/run_server.py` | 长驻后台、供手机/内网穿透访问 |

后台运行细节：
- 日志：`logs/server.log`（滚动保留 3 份）；
- 进程标记：`logs/server.pid`（JSON：pid / 启动时间 / 地址）；
- 停止：双击 `stop_server.bat`（等价 `python tools/stop_server.py`）；
- 状态：双击 `status_server.bat`（等价 `python tools/status_server.py`，会请求健康检查）；
- 重复启动保护：已运行时会直接提示并退出。

## 2. 健康检查接口（监控 / 穿透探测用）

- `GET /api/health` → `{"ok": true, "app": "study-assistant", "time": "..."}`
- `GET /healthz` → 纯文本 `ok`

两者都不需要登录、不泄露敏感信息，可交给负载均衡/监控（如 UptimeRobot）轮询。

## 3. 对外发布预留配置（config.py 均已支持，用环境变量覆盖即可）

| 环境变量 | 默认 | 说明 |
|----------|------|------|
| `APP_HOST` | `127.0.0.1` | 监听地址。穿透指向本机时无需改；直接对外监听请设 `0.0.0.0` |
| `APP_PORT` | `5000` | 监听端口 |
| `PUBLIC_BASE_URL` | 空 | 对外完整访问地址（如 `https://study.example.com`），供后续生成绝对链接/分享用 |
| `TRUST_PROXY_HEADERS` | `0` | 位于反向代理/穿透之后设 `1`，信任 `X-Forwarded-For/Proto/Host`（Flask ProxyFix） |
| `SECRET_KEY` | 开发默认值 | **公网发布务必改**：`set SECRET_KEY=随机长字符串` |
| `DATABASE` | `data/study_assistant.db` | 数据库路径（可按环境切换） |

## 4. 内网穿透示例（cpolar / ngrok / frp 同理）

场景：让手机 / 外网用户通过公网地址访问本机服务。

1. 先启动后台服务：双击 `start_server.bat`（监听 `127.0.0.1:5000`）。
2. 再启动一条隧道指向本机服务：
   - ngrok：`ngrok http 5000`
   - cpolar：`cpolar http 5000`
   - frp：配置 `local_ip = 127.0.0.1`、`local_port = 5000` 即可
3. 拿到公网地址（形如 `https://xxxx.ngrok-free.app`）。
4. 设置对外配置并重启服务（可选，但推荐）：
   ```bat
   set PUBLIC_BASE_URL=https://xxxx.ngrok-free.app
   set TRUST_PROXY_HEADERS=1
   start_server.bat
   ```
   `TRUST_PROXY_HEADERS=1` 让 Flask 信任隧道的 `X-Forwarded-Proto`，
   保证 https 环境下 `url_for(..., _external=True)` 等生成正确协议地址。

> 注意：免费隧道地址每次重启可能变化，属正常现象；如需固定域名请购买对应服务。

## 5. 反向代理示例（公网 VPS / 长期部署）

Nginx（监听 443/80，转发到本机或内网服务器 5000）：

```nginx
server {
    listen 80;
    server_name study.example.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

应用侧环境变量（与上节相同）：`PUBLIC_BASE_URL=https://study.example.com`、`TRUST_PROXY_HEADERS=1`。

## 6. 公网发布安全检查清单

- [ ] 修改 `SECRET_KEY`（会话签名密钥，泄露可伪造会话）
- [ ] 更换 / 加强管理员密码（`python tools/create_admin.py --username 管理员 --password 新密码`）
- [ ] 关闭 debug（后台运行默认已关闭）
- [ ] 如直接监听公网网卡（`APP_HOST=0.0.0.0`），请配置防火墙仅放行所需端口，并优先考虑反代 + HTTPS
- [ ] 定期备份数据库：直接复制 `data/study_assistant.db`（建议先停服或用 WAL 下复制，稳妥起见复制前执行 `python tools/status_server.py` 确认或直接复制 `-wal`/`-shm` 一并备份）
- [ ] 健康检查接口无需登录，仅暴露运行状态，不含敏感数据，可放心开放
