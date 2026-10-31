# -*- coding: utf-8 -*-
"""tunnel 配置目录说明。

本目录存放学习助手「内网穿透」相关文件（Cloudflare Tunnel）：

- cloudflared.exe      cloudflared 可执行文件（官方 GitHub Release 下载，已加入 PATH）
- config-quick.yml     Quick Tunnel（免登录临时域名）参考配置
- config-named.yml     命名隧道配置模板（需先完成 login + tunnel create，见根目录
                       tunnel_start.bat 与 docs/TUNNEL.md）

安全约定（务必遵守）：
- 本目录及项目内【任何文件】不得写入 API 令牌 / Tunnel Token / Cookie / 证书私钥。
- 登录授权后 Cloudflare 会生成 ~/.cloudflared/cert.pem（证书，非机密 Token），
  位于用户主目录，不在项目内。
- 命名隧道凭据 ~/.cloudflared/<uuid>.json 同样位于用户主目录；config-named.yml 中
  {TUNNEL_UUID} 由 tunnel_start.bat 从该 JSON 自动读取，无需手填。
"""
