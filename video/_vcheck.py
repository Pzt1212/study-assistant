# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, ".")
from app import create_app  # noqa: E402

app = create_app()
out = []
c = app.test_client()
with c.session_transaction() as s:
    s["_user_id"] = "1"
    s["_fresh"] = True

# 1) 播放页渲染
r = c.get("/video")
b = r.get_data(as_text=True)
out.append(f"{r.status_code} /video")
out.append(f"[{'PASS' if '视频' in b and 'video.js' in b else 'FAIL'}] 播放页结构")
out.append(f"[{'PASS' if 'video' in b and 'sa-mini' in b or 'video.js' in b else '?'}] 浮窗脚本引用")

# 2) 解析 B站链接
r = c.get("/video/api/resolve?url=" + "https://www.bilibili.com/video/BV1PmDWBKECC")
d = r.get_json() if r.is_json else {}
out.append(f"{r.status_code} resolve code={d.get('ok')}")
if d.get("ok"):
    v = d["video"]
    out.append(f"  title={v.get('title')} author={v.get('author')} embed={'embed_url' in v}")
else:
    out.append(f"  err={d.get('error')}")

# 3) 本地库 API（可能为空）
r = c.get("/video/api/local")
out.append(f"{r.status_code} local ok={r.get_json().get('ok')}")

# 4) 左侧栏入口
b2 = c.get("/").get_data(as_text=True)
out.append(f"[{'PASS' if '>视频<' in b2 or 'video.index' in b2 else 'FAIL'}] 侧栏视频入口")

open("video/_vcheck.txt", "w", encoding="utf-8").write("\n".join(out))
print("\n".join(out))
