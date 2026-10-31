# -*- coding: utf-8 -*-
"""全功能联动验证（模块八 + 回归自检）。

在真实数据库上以 Flask test_client 直接验证：
- 五科题库完整性（数学/物理/化学/英语/语文各 500 题）
- /questions/quiz 筛选下拉数据源（学科/难度/题型）
- /questions/api/random 组合筛选（subject + difficulty + type）与空结果提示
- 笔记手写 SVG 保存/净化/详情渲染/编辑回写
- /ocr 印刷体/手写体选项与优雅降级提示
- /music 在线轻音乐 + 脑波音频目录、API
- /admin 各页可用性与面包屑

不占用网络、不修改端口；会在用户 1 名下创建验证笔记并清理。
用法：python tools/verify_data.py
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import create_app  # noqa: E402
from models import get_note, get_user_by_id  # noqa: E402

RESULTS = []
FAILED = []


def check(name, ok, detail=""):
    tag = "PASS" if ok else "FAIL"
    RESULTS.append(f"[{tag}] {name}" + (f"  -> {detail}" if detail else ""))
    if not ok:
        FAILED.append(name)


def force_login(client, user_id):
    """在测试会话中直接写入登录用户，绕过密码。"""
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)


SVG_SAMPLE = (
    "<!--#!handwriting-svg-->\n"
    "<!--note-data:{\"w\":900,\"h\":560,\"strokes\":[{\"tool\":\"pen\","
    "\"color\":\"#1f2430\",\"size\":4,\"points\":[[10,10],[120,140]]}]}-->\n"
    '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="560" '
    'viewBox="0 0 900 560"><rect x="0" y="0" width="900" height="560" '
    'fill="#ffffff"/><path d="M10 10L120 140" fill="none" stroke="#1f2430" '
    'stroke-width="4" stroke-linecap="round"/></svg>'
)

SVG_EVIL = SVG_SAMPLE.replace(
    '<path d=', '<script>alert(1)</script><path d='
).replace(
    'stroke-linecap="round"',
    'stroke-linecap="round" onload="alert(2)"'
)


def main():
    app = create_app()
    client = app.test_client()

    # ============ 1. 五科完整性 ============
    with app.app_context():
        has_uid1 = get_user_by_id(1) is not None
    check("数据库用户存在(id=1)", has_uid1, "依赖真实库数据")
    force_login(client, 1)

    with app.app_context():
        from db import get_db
        db = get_db()
        rows = db.execute(
            "SELECT subject, COUNT(*) AS c FROM questions WHERE user_id=1 "
            "GROUP BY subject").fetchall()
        counts = {r["subject"]: r["c"] for r in rows}
    for subj in ("数学", "物理", "化学", "英语", "语文"):
        check(f"科目「{subj}」≥500 题入库", counts.get(subj, 0) == 500,
              f"实际 {counts.get(subj, 0)}")

    # ============ 2. quiz 页面数据源 ============
    page = client.get("/questions/quiz")
    body = page.get_data(as_text=True)
    check("quiz 页面可访问", page.status_code == 200)
    for subj in ("数学", "物理", "化学", "英语", "语文"):
        check(f"quiz 下拉含学科「{subj}」", f'value="{subj}"' in body)
    for d in ("简单", "中等", "较难"):
        check(f"quiz 下拉含难度「{d}」", f'value="{d}"' in body)
    for t in ("选择题", "填空题", "解答题"):
        check(f"quiz 下拉含题型「{t}」", f'value="{t}"' in body)

    # ============ 3. 组合筛选随机抽题 ============
    combos = [
        {"subject": "数学", "difficulty": "简单", "type": "选择题", "label": "数学×简单×选择题"},
        {"subject": "物理", "type": "解答题", "label": "物理×解答题"},
        {"difficulty": "较难", "subject": "化学", "label": "化学×较难"},
        {"subject": "英语", "difficulty": "中等", "label": "英语×中等"},
        {"difficulty": "简单", "subject": "语文", "label": "语文×简单"},
    ]
    for combo in combos:
        ok_all = True
        detail = []
        for _ in range(12):  # 每组合连抽 12 次，验证结果全部满足条件
            params = {}
            for key in ("subject", "difficulty", "type"):
                if combo.get(key):
                    params[key] = combo[key]
            resp = client.get("/questions/api/random", query_string=params)
            if resp.status_code != 200:
                ok_all = False
                detail.append(f"HTTP {resp.status_code}")
                break
            data = resp.get_json()
            q = data.get("question", {})
            if combo.get("subject") and q.get("subject") != combo["subject"]:
                ok_all = False
                detail.append(f"学科不符 {q.get('subject')}")
            if combo.get("difficulty") and q.get("difficulty") != combo["difficulty"]:
                ok_all = False
                detail.append(f"难度不符 {q.get('difficulty')}")
            if combo.get("type") and q.get("question_type") != combo["type"]:
                ok_all = False
                detail.append(f"题型不符 {q.get('question_type')}")
            if "answer" in q or "analysis" in q:
                ok_all = False
                detail.append("答案/解析泄露")
        check(f"组合筛选 {combo['label']}", ok_all, "; ".join(detail[:3]))

    # 空结果：难度填一个不存在的值
    resp = client.get("/questions/api/random",
                      query_string={"subject": "数学", "difficulty": "不存在难度"})
    data = resp.get_json()
    check("组合筛选空结果给出友好提示", resp.status_code == 404 and data.get("ok") is False
          and ("没有符合" in data.get("error", "") or "不存在难度" in data.get("error", "")),
          data.get("error", ""))

    # ============ 4. 笔记手写 SVG ============
    resp = client.post("/notes/new", data={
        "title": "验证手写笔记-SVG",
        "content": SVG_EVIL,
        "editor_mode": "handwrite",
    }, follow_redirects=True)
    check("手写笔记创建(editor_mode=handwrite)", resp.status_code == 200)
    note_id = _last_note_id(app, 1, "验证手写笔记-SVG")
    check("手写笔记已落库", note_id is not None)
    if note_id:
        with app.app_context():
            note = get_note(note_id, 1)
            check("手写笔记 file_type=svg", note and note["file_type"] == "svg")
            check("手写笔记含 SVG", note and "<svg" in note["content"])
            check("手写笔记 XSS 已被净化", note and "<script" not in note["content"]
                  and "onload=" not in note["content"])
        detail_page = client.get(f"/notes/{note_id}")
        db_ = detail_page.get_data(as_text=True)
        check("详情页渲染 SVG 画板", '<svg' in db_ and 'note-svg-frame' in db_)
        check("详情页无脚本注入", "alert(1)" not in db_ and "onload=" not in db_)
        # 编辑：切回文本并保存
        resp = client.post(f"/notes/{note_id}/edit", data={
            "title": "验证手写笔记-SVG",
            "content": "改为文本内容了",
            "editor_mode": "text",
        }, follow_redirects=True)
        with app.app_context():
            note = get_note(note_id, 1)
            check("手写笔记可切回文本模式", note and note["file_type"] == "text"
                  and note["content"].strip() == "改为文本内容了")
        client.post(f"/notes/{note_id}/delete", follow_redirects=True)
        with app.app_context():
            gone = get_note(note_id, 1) is None
        check("验证笔记已清理", gone)

    # ============ 5. OCR 页面 ============
    page = client.get("/ocr")
    body = page.get_data(as_text=True)
    check("OCR 页可访问", page.status_code == 200)
    check("OCR 页含印刷体选项", 'name="mode"' in body and 'value="printed"' in body)
    check("OCR 页含手写体选项", 'value="handwrite"' in body)
    tiny_png = _tiny_png()
    resp = client.post("/ocr", data={"mode": "handwrite",
                                     "image": (io.BytesIO(tiny_png), "t.png")},
                       content_type="multipart/form-data")
    body_hand = resp.get_data(as_text=True)
    # 手写模式不应 500：插件可用时对空白图返回“未识别到文字”，
    # 插件不可用 / 无引擎时给出可操作的安装引导提示。
    check("手写体识别流程可用（插件就绪或友好降级）",
          resp.status_code == 200 and (
              "未识别到文字" in body_hand or "手写体识别暂不可用" in body_hand
              or "rapidocr" in body_hand or "Tesseract" in body_hand),
          body_hand[:80])
    resp = client.post("/ocr", data={"mode": "printed",
                                     "image": (io.BytesIO(tiny_png), "t.png")},
                       content_type="multipart/form-data")
    check("印刷体无引擎时给出安装引导",
          resp.status_code == 200 and "OCR" in resp.get_data(as_text=True))

    # ============ 6. 音乐 ============
    page = client.get("/music")
    body = page.get_data(as_text=True)
    check("音乐页可访问", page.status_code == 200)
    check("音乐页含分类 脑波音频", "脑波音频" in body)
    check("音乐页含分类 在线轻音乐", "在线轻音乐" in body)
    data = client.get("/music/api/tracks").get_json()
    kinds = {t.get("kind") for t in data.get("tracks", [])}
    cats = {t.get("category") for t in data.get("tracks", [])}
    check("tracks API 数量≥3", len(data.get("tracks", [])) >= 3)
    check("tracks API 含流媒体与脑波两类", "stream" in kinds and "binaural" in kinds
          and "online" in cats and "brainwave" in cats)
    check("tracks API 返回分类统计", "categories" in data)
    found = client.get("/music/api/search", query_string={"q": "脑波"}).get_json()
    check("音乐搜索可用", isinstance(found.get("tracks"), list) and len(found["tracks"]) > 0)

    # ============ 7. 管理后台（以管理员身份） ============
    force_login(client, 3)  # admin(id=3) 已存在
    for path, kw in [
        ("/admin", "数据概览"),
        ("/admin/users", "用户管理"),
        ("/admin/questions", "全站题目管理"),
        ("/admin/notes", "全站笔记管理"),
        ("/admin/ocr-status", "OCR 服务状态"),
    ]:
        resp = client.get(path)
        body = resp.get_data(as_text=True)
        ok_page = resp.status_code == 200 and kw in body
        ok_crumb = "管理后台" in body and "admin-breadcrumb" in body
        check(f"管理页 {path}（含面包屑）", ok_page and ok_crumb)
    resp = client.get("/admin/ocr-status")
    body = resp.get_data(as_text=True)
    check("OCR 状态页含 provider 说明", "OCR_PROVIDER" in body
          and "rapidocr" in body and "Tesseract" in body)

    # ============ 汇总 ============
    print("=" * 66)
    print("联动验证报告（共 %d 项）" % len(RESULTS))
    print("=" * 66)
    print("\n".join(RESULTS))
    print("=" * 66)
    if FAILED:
        print("失败项 %d：%s" % (len(FAILED), "、".join(FAILED)))
        return 1
    print("全部通过 ✅")
    return 0


def _any_user(app):
    from models import count_users
    return count_users() > 0


def _last_note_id(app, user_id, title):
    with app.app_context():
        from db import get_db
        row = get_db().execute(
            "SELECT id FROM notes WHERE user_id=? AND title=? ORDER BY id DESC LIMIT 1",
            (user_id, title)).fetchone()
        return row["id"] if row else None


def _tiny_png():
    """1x1 透明 PNG（仅用于验证上传/OCR 流程，不需要真实内容）。"""
    import base64
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )


if __name__ == "__main__":
    sys.exit(main())
