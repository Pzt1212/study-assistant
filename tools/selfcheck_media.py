# -*- coding: utf-8 -*-
"""媒体库离线自测（不需要任何 R2 凭据/网络）。

覆盖：
1. 应用可正常创建并注册 /media 蓝图（含 db 新表）；
2. r2 直传通道在缺少凭据时优雅报错（而非 500）；
3. proxy 通道：创建会话 → 分块上传（加密落盘）→ 探测断点 → 组装 →
   本地文件生成 + SHA-256 → 异步 promote 任务在无 R2 时降级为"仅本地"；
4. 本地 Range 流（206）正常；
5. /media/api/config、列表接口正常。

用法：python tools/selfcheck_media.py
（使用独立临时数据库，不影响 data/study_assistant.db）
"""
import os
import shutil
import sys
import tempfile
import time

# 让脚本可独立运行：把项目根加入 sys.path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ["DATABASE"] = os.path.join(tempfile.gettempdir(),
                                      "sa_media_selfcheck.db")
os.environ["MEDIA_ITEM_ROOT"] = os.path.join(tempfile.gettempdir(),
                                             "sa_media_selfcheck_store")
os.environ["MEDIA_UPLOAD_CHANNEL"] = "proxy"   # 本测试覆盖 proxy 全链路
os.environ["MEDIA_SPOOL_ENCRYPT"] = "1"
os.environ["MEDIA_ASYNC_WORKERS"] = "1"

from app import create_app  # noqa: E402
from db import init_db  # noqa: E402
from models import create_user, get_media_item  # noqa: E402

PASS = 0


def check(name, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  [ok] {name}")
    else:
        print(f"  [FAIL] {name} {extra}")
        raise SystemExit(1)


def main():
    for p in (os.environ["DATABASE"], os.environ["MEDIA_ITEM_ROOT"]):
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(p + suffix):
                os.remove(p + suffix)

    app = create_app(initialize_db=False)
    app.config["TESTING"] = False
    init_db(app)
    with app.app_context():
        user = create_user("media_selfcheck", "media_selfcheck@test.local", "x")
        uid = user.id
    csrf = "selfcheck-token"

    print("== 1) 蓝图与页面 ==")
    with app.test_client() as c:
        r = c.get("/media/api/config")
        d = r.get_json() or {}
        check("未登录返回 401 JSON", r.status_code == 401 and d.get("ok") is False,
              str(d)[:200])
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["_user_id"] = str(uid)
        r = c.get("/media/api/config")
        d = r.get_json() or {}
        check("config 接口可用", r.status_code == 200 and d.get("ok"),
              str(d)[:200])
        check("配置回传 channel=proxy", d.get("config", {}).get("channel") == "proxy")
        check("r2Ready=False（无凭据）", d.get("config", {}).get("r2Ready") is False)
        r = c.get("/media")
        check("媒体库页面可访问", r.status_code == 200, f"status={r.status_code}")

    print("== 2) r2 直传在缺凭据时优雅报错 ==")
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["_user_id"] = str(uid)
            s["_csrf"] = csrf
        app.config["MEDIA_UPLOAD_CHANNEL"] = "r2"
        r = c.post("/media/api/items",
                   json={"filename": "demo.mp4", "size": 10 * 1024 * 1024},
                   headers={"X-CSRFToken": csrf})
        d = r.get_json() or {}
        check("返回 4xx/5xx 可读错误而非 500", r.status_code != 200 and d.get("ok") is False,
              f"status={r.status_code} {str(d)[:200]}")
        app.config["MEDIA_UPLOAD_CHANNEL"] = "proxy"

    print("== 3) proxy：创建会话 ==")
    item_id = None
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["_user_id"] = str(uid)
            s["_csrf"] = csrf
        r = c.post("/media/api/items",
                   json={"filename": "lesson.mp4", "size": 48,
                         "mime": "video/mp4"},
                   headers={"X-CSRFToken": csrf})
        d = r.get_json() or {}
        check("创建会话成功", r.status_code == 200 and d.get("ok"), str(d)[:300])
        item = d.get("item") or {}
        item_id = item.get("id")
        check("状态 uploading", item.get("status") == "uploading")

    print("== 4) proxy：分块上传（3×16B 加密落盘） ==")
    part_bodies = [bytes([i + 1]) * 16 for i in range(3)]
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["_user_id"] = str(uid)
            s["_csrf"] = csrf
        for n, body in enumerate(part_bodies, start=1):
            r = c.post(f"/media/api/proxy/chunks/{item_id}",
                       data={"resumableChunkNumber": str(n),
                             "resumableTotalChunks": "3",
                             "resumableChunkSize": "16",
                             "resumableTotalSize": "48",
                             "resumableFilename": "lesson.mp4",
                             "file": (io_BytesIO(body), "blob")},
                       content_type="multipart/form-data",
                       headers={"X-CSRFToken": csrf})
            check(f"分块 {n} 上传", r.status_code == 200,
                  f"status={r.status_code} {r.get_data(as_text=True)[:200]}")
        r = c.get(f"/media/api/proxy/chunks/{item_id}?resumableChunkNumber=1")
        check("断点探测：已存在分块 200", r.status_code == 200)
        r = c.get(f"/media/api/proxy/chunks/{item_id}?resumableChunkNumber=9")
        check("断点探测：缺失分块 404", r.status_code == 404)

    print("== 5) proxy：完成 → 组装 + SHA-256 + 本地文件 ==")
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["_user_id"] = str(uid)
            s["_csrf"] = csrf
        r = c.post(f"/media/api/proxy/complete/{item_id}",
                   headers={"X-CSRFToken": csrf})
        d = r.get_json() or {}
        check("complete 成功", r.status_code == 200 and d.get("ok"), str(d)[:300])
        it = d.get("item") or {}
        check("状态 promoting（转存 R2 中）", it.get("status") == "promoting")

    print("== 6) 异步 promote（无 R2 → 降级仅本地，状态 ready + 提示） ==")
    deadline = time.time() + 8
    final_status = None
    while time.time() < deadline:
        with app.app_context():
            row = get_media_item(item_id)
        final_status = row["status"] if row else None
        if final_status in ("ready", "failed"):
            break
        time.sleep(0.3)
    with app.app_context():
        row = get_media_item(item_id)
    check("promote 任务收敛", row and row["status"] in ("ready", "failed"),
          f"status={row and row['status']}")
    if row and row["status"] == "ready":
        check("本地文件已生成", bool(row["local_file"]))
        check("SHA-256 已回填", bool(row["sha256"]))

    print("== 7) Range 本地播放（206） ==")
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["_user_id"] = str(uid)
        r = c.get(f"/media/api/items/{item_id}/stream",
                  headers={"Range": "bytes=0-9"})
        check("Range 请求返回 206", r.status_code == 206, f"status={r.status_code}")
        data = r.get_data()
        check("内容与源文件一致", data == part_bodies[0][:10],
              f"got={data!r}")
        r2 = c.get(f"/media/api/items/{item_id}/stream", headers={"Range": "bytes=16-31"})
        check("第二段 Range 正确", r2.get_data() == part_bodies[1],
              f"got={r2.get_data()!r}")

    print("== 8) 删除 ==")
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["_user_id"] = str(uid)
            s["_csrf"] = csrf
        r = c.delete(f"/media/api/items/{item_id}",
                     headers={"X-CSRFToken": csrf})
        check("删除成功", r.status_code == 200 and (r.get_json() or {}).get("ok"),
              str(r.get_data(as_text=True))[:200])

    print(f"\n全部通过：{PASS} 项断言")
    return 0


def io_BytesIO(data):
    import io
    return io.BytesIO(data)


if __name__ == "__main__":
    sys.exit(main())
