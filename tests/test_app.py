# -*- coding: utf-8 -*-
"""学习助手 - 端到端单元测试。

使用 Python 标准库 unittest，无需额外依赖。
运行方式（项目根目录）：
    python -m unittest discover -s tests -v

测试覆盖：
- 注册 / 登录 / 退出（含表单校验）
- 题库：新增题目、随机抽题、答题判分
- 笔记：新建、上传文本文件、编辑、搜索
- 全局搜索
- 登录保护（未登录访问跳转登录页）
"""
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

# 确保可以导入应用模块（从项目根目录运行）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from models import (  # noqa: E402
    count_questions,
    create_question_detailed,
    get_user_by_username,
    set_user_admin,
)


class TestConfig:
    """测试专用配置：使用独立的临时数据库与上传目录。"""

    TESTING = True
    SECRET_KEY = "test-secret-key"
    CSRF_ENABLED = False  # 测试环境关闭 CSRF，具体 CSRF 行为另有专项测试（见 CSRF_Tests）
    DATABASE = os.path.join(tempfile.gettempdir(), "study_assistant_test.db")
    UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), "study_assistant_test_uploads")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    ALLOWED_UPLOAD_EXTENSIONS = {"txt", "md", "markdown", "png", "jpg", "jpeg", "gif", "bmp", "webp"}
    OCR_ENGINE = "local"
    TESSERACT_CMD = ""
    OCR_LANG = "chi_sim+eng"
    OCR_API_URL = ""
    OCR_API_KEY = ""


class BaseTestCase(unittest.TestCase):
    """测试基类：准备应用与客户端，清理临时数据库。"""

    def setUp(self):
        # 清理上次测试残留的数据库文件
        for suffix in ("", "-wal", "-shm"):
            path = TestConfig.DATABASE + suffix
            if os.path.exists(path):
                os.remove(path)
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

    def tearDown(self):
        # 清理测试数据库与上传目录
        for suffix in ("", "-wal", "-shm"):
            path = TestConfig.DATABASE + suffix
            if os.path.exists(path):
                os.remove(path)
        if os.path.isdir(TestConfig.UPLOAD_FOLDER):
            for f in os.listdir(TestConfig.UPLOAD_FOLDER):
                os.remove(os.path.join(TestConfig.UPLOAD_FOLDER, f))
            os.rmdir(TestConfig.UPLOAD_FOLDER)

    # ---- 辅助方法 ----
    def register(self, username="testuser", email="test@example.com",
                 password="secret123", confirm=None):
        """调用注册接口。"""
        return self.client.post(
            "/register",
            data={
                "username": username,
                "email": email,
                "password": password,
                "confirm": confirm if confirm is not None else password,
            },
            follow_redirects=True,
        )

    def login(self, username="testuser", password="secret123"):
        """调用登录接口。"""
        return self.client.post(
            "/login",
            data={"username": username, "password": password},
            follow_redirects=True,
        )

    def register_and_login(self):
        """注册并登录一个测试用户，返回响应。"""
        self.register()
        return self.login()


class AuthTests(BaseTestCase):
    """认证功能测试。"""

    def test_register_success(self):
        resp = self.register()
        self.assertEqual(resp.status_code, 200)
        self.assertIn("注册成功".encode(), resp.data)

    def test_register_password_mismatch(self):
        resp = self.register(confirm="different")
        self.assertIn("两次输入的密码不一致".encode(), resp.data)

    def test_register_duplicate_username(self):
        self.register()
        resp = self.register(username="testuser", email="other@example.com")
        self.assertIn("该用户名已被注册".encode(), resp.data)

    def test_register_duplicate_email(self):
        self.register()
        resp = self.register(username="otheruser")
        self.assertIn("该邮箱已被注册".encode(), resp.data)

    def test_login_success(self):
        self.register()
        resp = self.login()
        self.assertIn("欢迎回来".encode(), resp.data)
        self.assertIn("testuser".encode(), resp.data)

    def test_login_wrong_password(self):
        self.register()
        resp = self.login(password="wrong-password")
        self.assertIn("用户名或密码错误".encode(), resp.data)

    def test_logout(self):
        self.register_and_login()
        # 登出仅允许 POST（防跨站 GET 触发）；GET 应 405
        resp = self.client.get("/logout", follow_redirects=True)
        self.assertEqual(resp.status_code, 405)
        resp = self.client.post("/logout", follow_redirects=True)
        self.assertIn("已退出登录".encode(), resp.data)

    def test_login_required(self):
        # 未登录访问受保护页面，应重定向到登录页（跟随重定向后显示提示）
        resp = self.client.get("/notes", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("请先登录".encode(), resp.data)


class QuestionTests(BaseTestCase):
    """题库功能测试。"""

    def setUp(self):
        super().setUp()
        self.register_and_login()

    def add_question(self):
        """新增一道测试题。"""
        return self.client.post(
            "/questions/new",
            data={
                "subject": "数学",
                "content": "1+1 等于多少？",
                "option_a": "1",
                "option_b": "2",
                "option_c": "3",
                "option_d": "4",
                "answer": "B",
                "analysis": "因为 1+1=2",
            },
            follow_redirects=True,
        )

    def test_create_question(self):
        resp = self.add_question()
        self.assertIn("题目已添加".encode(), resp.data)

    def test_create_question_missing_option(self):
        resp = self.client.post(
            "/questions/new",
            data={
                "subject": "数学",
                "content": "题干",
                "option_a": "1",
                "option_b": "",
                "option_c": "3",
                "option_d": "4",
                "answer": "A",
                "analysis": "",
            },
            follow_redirects=True,
        )
        self.assertIn("四个选项".encode(), resp.data)

    def test_random_and_answer(self):
        self.add_question()

        # 随机抽题
        resp = self.client.get("/questions/api/random")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        q = data["question"]
        self.assertEqual(q["subject"], "数学")
        # 答案不应泄露给前端
        self.assertNotIn("answer", q)

        # 回答正确
        resp = self.client.post(
            "/questions/api/answer",
            json={"question_id": q["id"], "answer": "B"},
        )
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["correct"])
        self.assertEqual(data["correct_answer"], "B")
        self.assertEqual(data["analysis"], "因为 1+1=2")

        # 回答错误
        resp = self.client.post(
            "/questions/api/answer",
            json={"question_id": q["id"], "answer": "A"},
        )
        data = resp.get_json()
        self.assertFalse(data["correct"])
        self.assertEqual(data["stats"]["correct"], 1)
        self.assertEqual(data["stats"]["wrong"], 1)


class QuizExtendedTests(BaseTestCase):
    """刷题模式多题型测试：填空题 / 解答题纳入抽题、判分与自评。"""

    def setUp(self):
        super().setUp()
        self.register_and_login()
        with self.app.app_context():
            self.uid = get_user_by_username("testuser").id

    def _insert(self, question_type, difficulty="简单", **kw):
        """用数据层直接插入一道完整字段的题目，返回 id。"""
        with self.app.app_context():
            return create_question_detailed(
                self.uid,
                subject=kw.get("subject", "数学"),
                content=kw.get("content", "占位题干"),
                answer=kw.get("answer", "占位答案"),
                question_type=question_type,
                difficulty=difficulty,
                topic=kw.get("topic", "测试专题"),
                score=kw.get("score", 3),
                analysis=kw.get("analysis", "测试解析。"),
                option_a=kw.get("option_a", ""),
                option_b=kw.get("option_b", ""),
                option_c=kw.get("option_c", ""),
                option_d=kw.get("option_d", ""),
                step_rules=kw.get("step_rules"),
            )

    def test_random_filter_by_type(self):
        """?type= 能按题型过滤随机抽题；缺省为混合抽取。"""
        choice_id = self._insert("选择题", "简单", content="选择题题干",
                                 answer="B", option_a="A", option_b="B",
                                 option_c="C", option_d="D")
        fill_id = self._insert("填空题", "简单", content="填空题题干____", answer="5")
        answer_id = self._insert("解答题", "简单", content="解答题题干",
                                 answer="解：详细过程……", score=8,
                                 step_rules={"列式": 3, "计算": 3, "作答": 2})

        for qtype, qid in (("选择题", choice_id), ("填空题", fill_id),
                           ("解答题", answer_id)):
            resp = self.client.get(f"/questions/api/random?type={qtype}")
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data["ok"])
            self.assertEqual(data["question"]["question_type"], qtype)
            # 随机抽题不允许泄露答案/解析/评分标准
            for secret in ("answer", "analysis", "reference_answer", "step_rules"):
                self.assertNotIn(secret, data["question"])

        # 混合抽取（不带 type）至少能抽到合法题目
        resp = self.client.get("/questions/api/random")
        self.assertTrue(resp.get_json()["ok"])

    def test_fill_answer_and_grade(self):
        """填空题去空格判分 + 解答题自评得分均写库。"""
        fill_id = self._insert("填空题", "简单", content="2x+1=5，x=____。",
                               answer="2", analysis="2x=4 得 x=2。")

        # 空格容错：首尾空白应判对
        resp = self.client.post("/questions/api/answer",
                                json={"question_id": fill_id, "answer": " 2 "})
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["correct"])

        # 打错判错
        resp = self.client.post("/questions/api/answer",
                                json={"question_id": fill_id, "answer": "3"})
        self.assertFalse(resp.get_json()["correct"])

        # 解答题：先提交解答拿参考答案与评分标准（不落答题记录）
        answer_id = self._insert("解答题", "中等", content="解方程 2x-3=5。",
                                 answer="解：移项得 2x=8，所以 x=4。",
                                 score=6, step_rules={"移项": 2, "合并": 2, "得解": 2})
        resp = self.client.post("/questions/api/answer",
                                json={"question_id": answer_id, "answer": "我的解答过程"})
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["answer_type"], "解答题")
        self.assertIn("x=4", data["reference_answer"])
        self.assertGreaterEqual(len(data["step_rules"]), 2)
        self.assertEqual(data["full_score"], 6)

        # 自评满分 → 判对且记录得分
        resp = self.client.post("/questions/api/grade",
                                json={"question_id": answer_id,
                                      "answer": "我的解答过程", "score": 6})
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["correct"])
        self.assertEqual(data["score"], 6)

        # 解答过程与得分确实写入答题记录表
        with self.app.app_context():
            from db import get_db
            rows = get_db().execute(
                "SELECT user_answer, is_correct, score FROM answer_records "
                "WHERE user_id = ? AND question_id = ?",
                (self.uid, answer_id)).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["user_answer"], "我的解答过程")
            self.assertEqual(rows[0]["score"], 6)
            self.assertEqual(rows[0]["is_correct"], 1)


class NoteTests(BaseTestCase):
    """笔记功能测试。"""

    def setUp(self):
        super().setUp()
        self.register_and_login()

    def test_create_note(self):
        resp = self.client.post(
            "/notes/new",
            data={"title": "测试笔记", "content": "这是笔记内容"},
            follow_redirects=True,
        )
        self.assertIn("笔记已创建".encode(), resp.data)
        self.assertIn("这是笔记内容".encode(), resp.data)

    def test_upload_txt_note(self):
        # 上传一个 txt 文件，验证自动提取文本
        content = "这是一段上传的文本内容，用于测试提取。"
        data = {
            "file": (io.BytesIO(content.encode("utf-8")), "我的笔记.txt"),
        }
        resp = self.client.post(
            "/notes/upload", data=data, content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn("上传成功".encode(), resp.data)
        self.assertIn(content.encode(), resp.data)

    def test_delete_note(self):
        # 先创建一篇笔记
        self.client.post(
            "/notes/new",
            data={"title": "待删除", "content": "内容"},
            follow_redirects=True,
        )
        resp = self.client.post("/notes/1/delete", follow_redirects=True)
        self.assertIn("笔记已删除".encode(), resp.data)


class SearchTests(BaseTestCase):
    """全局搜索测试。"""

    def setUp(self):
        super().setUp()
        self.register_and_login()

    def test_search_notes_and_questions(self):
        # 准备数据：一篇笔记 + 一道题
        self.client.post(
            "/notes/new",
            data={"title": "高等数学笔记", "content": "导数与积分"},
            follow_redirects=True,
        )
        self.client.post(
            "/questions/new",
            data={
                "subject": "数学",
                "content": "什么是导数？",
                "option_a": "A1", "option_b": "B1",
                "option_c": "C1", "option_d": "D1",
                "answer": "A", "analysis": "导数描述变化率",
            },
            follow_redirects=True,
        )

        # 搜索 "数学"：应同时命中笔记标题和题目
        resp = self.client.get("/search?q=数学")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("高等数学笔记".encode(), resp.data)
        self.assertIn("什么是导数".encode(), resp.data)

        # 搜索笔记特有内容
        resp = self.client.get("/search?q=积分")
        self.assertIn("高等数学笔记".encode(), resp.data)

        # 搜索无结果
        resp = self.client.get("/search?q=不存在的内容xyz")
        self.assertIn("未找到匹配的笔记".encode(), resp.data)


class PomodoroTests(BaseTestCase):
    """番茄钟记录测试。"""

    def setUp(self):
        super().setUp()
        self.register_and_login()

    def test_record_pomodoro(self):
        resp = self.client.post(
            "/pomodoro/record",
            json={"mode": "focus", "duration_seconds": 1500},
        )
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["today_focus"], 1)

        # 再次记录，今日数应 +1
        self.client.post(
            "/pomodoro/record",
            json={"mode": "focus", "duration_seconds": 1500},
        )
        resp = self.client.get("/pomodoro/api/stats")
        data = resp.get_json()
        self.assertEqual(data["today_focus"], 2)


class MusicTests(BaseTestCase):
    """音乐播放器测试。"""

    def setUp(self):
        super().setUp()
        self.register_and_login()

    def test_tracks_api(self):
        resp = self.client.get("/music/api/tracks")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertGreaterEqual(len(data["tracks"]), 3)  # 至少 3 首占位曲目

    def test_music_page(self):
        resp = self.client.get("/music")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("背景音乐".encode(), resp.data)


class AdminTests(BaseTestCase):
    """后台管理功能测试。"""

    def setUp(self):
        super().setUp()
        self.register_and_login()
        # 将当前测试用户提升为管理员（等价于执行过 flask create-admin）
        with self.app.app_context():
            user = get_user_by_username("testuser")
            set_user_admin(user.id, True)

    def _get_user(self, username):
        """在应用上下文中读取用户（数据层依赖 Flask g，不能脱离上下文调用）。"""
        with self.app.app_context():
            return get_user_by_username(username)

    def test_admin_overview(self):
        """管理员可访问概览页并看到统计。"""
        resp = self.client.get("/admin")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("管理后台".encode(), resp.data)
        self.assertIn("用户总数".encode(), resp.data)
        self.assertIn("题目总数".encode(), resp.data)

    def test_admin_users_page(self):
        """用户管理列表展示用户名。"""
        resp = self.client.get("/admin/users")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("testuser".encode(), resp.data)

    def test_admin_required_for_normal_user(self):
        """普通用户访问 /admin 应返回 403。"""
        self.client.post("/logout")  # 先退出管理员账号
        self.register(username="normal", email="normal@example.com")
        self.login(username="normal")
        resp = self.client.get("/admin")
        self.assertEqual(resp.status_code, 403)
        self.assertIn("无权访问".encode(), resp.data)

    def test_admin_questions_page_and_delete(self):
        """全站题目管理：可看到并删除任意题目。"""
        self.client.post(
            "/questions/new",
            data={
                "subject": "测试科目",
                "content": "这是一道由管理员删除的题",
                "option_a": "A1", "option_b": "B1",
                "option_c": "C1", "option_d": "D1",
                "answer": "A", "analysis": "",
            },
            follow_redirects=True,
        )
        resp = self.client.get("/admin/questions")
        self.assertIn("这是一道由管理员删除的题".encode(), resp.data)

        resp = self.client.post("/admin/questions/1/delete", follow_redirects=True)
        self.assertIn("已删除题目".encode(), resp.data)
        self.assertNotIn("这是一道由管理员删除的题".encode(), resp.data)

    def test_admin_notes_page_and_delete(self):
        """全站笔记管理：可看到并删除任意笔记。"""
        self.client.post(
            "/notes/new",
            data={"title": "管理员可见笔记", "content": "笔记内容"},
            follow_redirects=True,
        )
        resp = self.client.get("/admin/notes")
        self.assertIn("管理员可见笔记".encode(), resp.data)

        resp = self.client.post("/admin/notes/1/delete", follow_redirects=True)
        self.assertIn("已删除笔记".encode(), resp.data)

    def test_delete_self_forbidden(self):
        """管理员不能删除自己。"""
        resp = self.client.post("/admin/users/1/delete", follow_redirects=True)
        self.assertIn("不能删除当前登录的管理员账号".encode(), resp.data)
        self.assertIsNotNone(self._get_user("testuser"))

    def test_cannot_revoke_last_admin(self):
        """全站仅剩 1 名超级管理员时，超级管理员不能修改自己的角色。"""
        resp = self.client.post("/admin/users/1/set-role",
                                data={"role": "0"}, follow_redirects=True)
        self.assertIn("不能修改自己的角色".encode(), resp.data)
        self.assertEqual(self._get_user("testuser").role, 3)

    def test_set_role_and_delete_user(self):
        """超管任免角色 → 新任超管删除原超管（连带数据）。"""
        # 退出当前超管账号后注册第二人，再以超管身份登录
        self.client.post("/logout", follow_redirects=True)
        self.register(username="admin2", email="admin2@example.com")
        self.login(username="testuser", password="secret123")

        admin2 = self._get_user("admin2")
        # 把 admin2 设为超级管理员
        resp = self.client.post(
            f"/admin/users/{admin2.id}/set-role",
            data={"role": "3"}, follow_redirects=True
        )
        self.assertIn("超级管理员".encode(), resp.data)
        self.assertEqual(self._get_user("admin2").role, 3)

        # 已存在第 2 名超管时，原超管仍不能修改自己的角色（设计如此）
        me = self._get_user("testuser")
        resp = self.client.post(
            f"/admin/users/{me.id}/set-role",
            data={"role": "0"}, follow_redirects=True
        )
        self.assertIn("不能修改自己的角色".encode(), resp.data)
        self.assertEqual(self._get_user("testuser").role, 3)

        # admin2（超管）删除已无用的 testuser（连带数据）
        self.client.post("/logout", follow_redirects=True)
        self.login(username="admin2", password="secret123")
        resp = self.client.post(
            f"/admin/users/{me.id}/delete", follow_redirects=True
        )
        self.assertIn("已删除用户".encode(), resp.data)
        self.assertIsNone(self._get_user("testuser"))

    def test_moderator_level_scope(self):
        """协管（role 1）：可管理内容页，但无概览/用户管理/角色权限。"""
        self.client.post("/logout", follow_redirects=True)
        self.register(username="mod1", email="mod1@example.com")
        self.login(username="testuser", password="secret123")
        mod = self._get_user("mod1")
        with self.app.app_context():
            from models import set_user_role
            set_user_role(mod.id, 1)
        self.client.post("/logout", follow_redirects=True)
        self.login(username="mod1", password="secret123")
        self.assertEqual(self.client.get("/admin/questions").status_code, 200)
        self.assertEqual(self.client.get("/admin/notes").status_code, 200)
        self.assertEqual(self.client.get("/admin").status_code, 403)
        self.assertEqual(self.client.get("/admin/users").status_code, 403)
        self.assertEqual(self.client.get("/admin/ocr-status").status_code, 403)

    def test_admin_level2_scope(self):
        """管理员（role 2）：可看概览/用户/OCR，但不能任免角色。"""
        self.client.post("/logout", follow_redirects=True)
        self.register(username="adm2", email="adm2@example.com")
        self.login(username="testuser", password="secret123")
        adm2 = self._get_user("adm2")
        with self.app.app_context():
            from models import set_user_role
            set_user_role(adm2.id, 2)
        self.client.post("/logout", follow_redirects=True)
        self.login(username="adm2", password="secret123")
        self.assertEqual(self.client.get("/admin").status_code, 200)
        self.assertEqual(self.client.get("/admin/users").status_code, 200)
        # role2 访问 set-role（仅超管）→ 403
        resp = self.client.post(
            f"/admin/users/{self._get_user('testuser').id}/set-role",
            data={"role": "0"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_ocr_status_page(self):
        """OCR 状态页展示引擎与配置情况。"""
        resp = self.client.get("/admin/ocr-status")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("当前生效引擎".encode(), resp.data)
        self.assertIn("OCR_PROVIDER".encode(), resp.data)


class QuestionBankTests(BaseTestCase):
    """在线题库：用户自备 API 的接入与导入（项目不内置题目）。"""

    def setUp(self):
        super().setUp()
        self.register_and_login()

    def _count_questions(self):
        """在应用上下文中统计当前测试用户题目数（数据层依赖 Flask g）。"""
        with self.app.app_context():
            uid = get_user_by_username("testuser").id
            return count_questions(uid)

    def test_index_page(self):
        """首页展示自备 API 接入表单，且不再包含内置题库。"""
        resp = self.client.get("/question-bank")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("在线题库".encode(), resp.data)
        self.assertIn("接入你的题库 API".encode(), resp.data)
        self.assertNotIn("内置免费题库".encode(), resp.data)

    def test_import_with_api_url_mocked(self):
        """填写接口地址 + mock 网络请求，题目应写入题库。"""
        before = self._count_questions()
        with mock.patch("services.question_bank.requests.get") as mocked_get:
            mocked_get.return_value.json.return_value = {"answer": "四"}
            resp = self.client.post(
                "/question-bank/import",
                data={"api_url": "https://example.com/ask",
                      "questions": "一加三等于多少？"},
                follow_redirects=True,
            )
        mocked_get.assert_called_once()
        self.assertIn("已通过在线题库导入 1 道题目".encode(), resp.data)
        self.assertEqual(self._count_questions() - before, 1)

        # 落库字段校验：答案置于 option_a，answer 固定为 A，科目固定
        with self.app.app_context():
            from db import get_db
            uid = get_user_by_username("testuser").id
            row = get_db().execute(
                "SELECT content, option_a, answer, subject FROM questions "
                "WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (uid,),
            ).fetchone()
        self.assertEqual(row["content"], "一加三等于多少？")
        self.assertEqual(row["option_a"], "四")
        self.assertEqual(row["answer"], "A")
        self.assertEqual(row["subject"], "在线题库（API）")

    def test_import_uses_config_api_url(self):
        """未在页面填写地址时，回落到环境变量/配置中的地址。"""
        self.app.config["QUESTION_BANK_API_URL"] = "https://config.example.com/ask"
        with mock.patch("services.question_bank.requests.get") as mocked_get:
            mocked_get.return_value.json.return_value = {"answer": "答案"}
            resp = self.client.post(
                "/question-bank/import",
                data={"questions": "任意题目"},
                follow_redirects=True,
            )
        self.assertIn("已通过在线题库导入 1 道题目".encode(), resp.data)
        args, kwargs = mocked_get.call_args
        self.assertEqual(args[0], "https://config.example.com/ask")

    def test_import_missing_api_url(self):
        """未配置任何接口地址时应提示。"""
        resp = self.client.post(
            "/question-bank/import", data={"questions": "任意题目"}, follow_redirects=True
        )
        self.assertIn("请填写你的题库 API 地址".encode(), resp.data)
        self.assertEqual(self._count_questions(), 0)

    def test_import_disabled(self):
        """WKAPI_ENABLED=False 时拒绝导入。"""
        self.app.config["WKAPI_ENABLED"] = False
        resp = self.client.post(
            "/question-bank/import",
            data={"api_url": "https://example.com/ask", "questions": "任意题目"},
            follow_redirects=True,
        )
        self.assertIn("已被管理员关闭".encode(), resp.data)
        self.assertEqual(self._count_questions(), 0)

    def test_import_no_questions(self):
        """未填写题目应给出提示。"""
        resp = self.client.post(
            "/question-bank/import",
            data={"api_url": "https://example.com/ask"},
            follow_redirects=True,
        )
        self.assertIn("请输入至少一道题目".encode(), resp.data)

    def test_fetch_normalization(self):
        """服务层：HTML 反转义 / 嵌套结构 / 异常处理 / 字段标准化。"""
        import requests

        from services import question_bank as qb

        url = "https://example.com/ask"

        # 1) 普通结构 + HTML 反转义：&amp; → &
        with mock.patch("services.question_bank.requests.get") as mocked_get:
            mocked_get.return_value.json.return_value = {"answer": "Four &amp; Five"}
            self.assertEqual(qb.fetch_answer(url, "q1"), "Four & Five")

        # 2) 兼容 {"data": {"answer": ...}} 嵌套结构
        with mock.patch("services.question_bank.requests.get") as mocked_get:
            mocked_get.return_value.json.return_value = {"data": {"answer": "嵌套答案"}}
            self.assertEqual(qb.fetch_answer(url, "q2"), "嵌套答案")

        # 3) 兼容 {"data": "..."} 字符串结构
        with mock.patch("services.question_bank.requests.get") as mocked_get:
            mocked_get.return_value.json.return_value = {"data": "扁平答案"}
            self.assertEqual(qb.fetch_answer(url, "q3"), "扁平答案")

        # 4) 缺 answer 字段时抛 QuestionBankError，并附带接口返回信息
        with mock.patch("services.question_bank.requests.get") as mocked_get:
            mocked_get.return_value.json.return_value = {"msg": "rate limited"}
            with self.assertRaises(qb.QuestionBankError) as ctx:
                qb.fetch_answer(url, "q4")
            self.assertIn("rate limited", str(ctx.exception))

        # 5) 网络异常包装为 QuestionBankError
        with mock.patch(
            "services.question_bank.requests.get",
            side_effect=requests.RequestException("network down"),
        ):
            with self.assertRaises(qb.QuestionBankError):
                qb.fetch_answer(url, "q5")

        # 6) 非 JSON 响应包装为 QuestionBankError
        with mock.patch("services.question_bank.requests.get") as mocked_get:
            mocked_get.return_value.json.side_effect = ValueError("bad json")
            with self.assertRaises(qb.QuestionBankError):
                qb.fetch_answer(url, "q6")

        # 7) 未配置地址时直接报错，不发起请求
        with self.assertRaises(qb.QuestionBankError):
            qb.fetch_answer("", "q7")

        # 8) 批量标准化：option_a=答案、answer=A、subject 固定，空行跳过
        answers = iter(["2", "北京"])

        def _fake_get(*_args, **_kwargs):
            resp = mock.Mock()
            resp.json.return_value = {"answer": next(answers)}
            return resp

        with mock.patch("services.question_bank.requests.get", side_effect=_fake_get):
            items = qb.fetch_questions(url, ["1+1=？", "中国的首都是？", "  "])

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["content"], "1+1=？")
        self.assertEqual(items[0]["option_a"], "2")
        self.assertEqual(items[0]["answer"], "A")
        self.assertEqual(items[0]["subject"], "在线题库（API）")
        self.assertEqual(items[1]["option_a"], "北京")


if __name__ == "__main__":
    unittest.main()
