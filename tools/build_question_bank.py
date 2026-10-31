# -*- coding: utf-8 -*-
"""初中全科题库生成器（直接写入 SQLite questions 表）。

功能：
- 覆盖学科：数学 / 物理 / 化学 / 英语 / 语文（可用 --subject 只跑某科）
- 每学科目标 500 道（选择题 + 填空题 + 解答题混合），难度 简单30%/中等50%/较难20%
- topic 字段覆盖该学科初中全部知识板块
- 每题含答案、解析；解答题含完整分步解答与评分标准（step_rules JSON）
- 先清空旧题再写入 data/study_assistant.db 的 questions 表（默认 user_id=1）
- 内容由 DeepSeek 大模型生成（与项目原 gen_questions.py 同源思路）

用法：
    python tools/build_question_bank.py                # 全科生成（交互确认）
    python tools/build_question_bank.py --yes          # 跳过确认直接生成
    python tools/build_question_bank.py --subject 数学 --yes
"""
import argparse
import hashlib
import json
import os
import random
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# ============================================================
# 配置
# ============================================================

# DeepSeek API Key 只从环境变量读取（代码中不再内置任何密钥，缺失即拒绝运行）
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
if not DEEPSEEK_API_KEY:
    raise SystemExit(
        "错误：未设置环境变量 DEEPSEEK_API_KEY。\n"
        "密钥已从代码中移除（防止泄漏），请先设置环境变量后再运行本脚本。"
    )
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(ROOT, "data", "study_assistant.db")
DEFAULT_USER_ID = 1   # 题库归属用户（当前账号 111）

QUESTION_TYPES = ("选择题", "填空题", "解答题")
DIFFICULTIES = ("简单", "中等", "较难")

# 每学科三种题型的题量配比（总和 500；难度统一按 3:5:2 再拆分）
TYPE_SIZES = {
    "数学": {"选择题": 230, "填空题": 140, "解答题": 130},
    "物理": {"选择题": 220, "填空题": 150, "解答题": 130},
    "化学": {"选择题": 210, "填空题": 160, "解答题": 130},
    "英语": {"选择题": 240, "填空题": 140, "解答题": 120},
    "语文": {"选择题": 180, "填空题": 170, "解答题": 150},
}

# 各科初中知识板块与规划题量（第一轮铺量用；缺口由纠偏轮补齐）
SUBJECT_TOPICS = {
    "数学": [
        ("有理数与数轴", 26), ("有理数运算", 26), ("整式加减", 22),
        ("一元一次方程", 26), ("二元一次方程组", 24), ("不等式与不等式组", 24),
        ("实数与二次根式", 24), ("整式乘除与因式分解", 24), ("分式与分式方程", 22),
        ("平面直角坐标系与函数初步", 20), ("一次函数", 24), ("反比例函数", 18),
        ("二次函数", 26), ("相交线与平行线", 20), ("三角形与多边形", 24),
        ("全等三角形", 22), ("轴对称与等腰三角形", 20), ("勾股定理", 22),
        ("平行四边形与特殊平行四边形", 26), ("圆", 28), ("相似", 22),
        ("锐角三角函数与解直角三角形", 20), ("旋转与平移", 12), ("投影与视图", 12),
        ("统计与概率", 22),
    ],
    "物理": [
        ("机械运动与长度时间测量", 26), ("声现象", 20), ("物态变化", 26),
        ("光现象", 26), ("透镜及其应用", 22), ("质量与密度", 26),
        ("力与重力弹力摩擦力", 26), ("运动和力与二力平衡", 26), ("压强", 26),
        ("浮力", 26), ("功和功率", 22), ("机械能及其转化", 16),
        ("简单机械与机械效率", 22), ("内能与比热容", 22), ("热机与热值", 14),
        ("电流和电路", 26), ("电压电阻", 22), ("欧姆定律", 28),
        ("电功电功率", 28), ("电与磁", 20), ("生活用电", 12),
    ],
    "化学": [
        ("走进化学世界与实验基本操作", 30), ("空气与氧气", 28),
        ("物质构成的奥秘（分子原子离子）", 28), ("元素与元素周期表", 24),
        ("自然界的水", 24), ("化学式与化合价", 28), ("质量守恒定律与化学方程式", 30),
        ("碳和碳的氧化物", 26), ("燃料及其利用", 22),
        ("金属和金属材料", 30), ("溶液的组成与溶解度", 26),
        ("酸和碱", 30), ("盐和化肥", 30), ("化学与生活", 14),
        ("物质的检验鉴别与分离除杂", 26), ("化学计算", 28),
    ],
    "英语": [
        ("名词", 24), ("代词", 28), ("冠词", 20), ("数词", 16),
        ("介词与介词短语", 26), ("连词", 18), ("形容词", 24), ("副词", 22),
        ("动词时态", 38), ("被动语态", 22), ("非谓语动词", 22),
        ("情态动词", 20), ("主谓一致", 16), ("句子种类与句型转换", 24),
        ("宾语从句", 20), ("定语从句", 18), ("状语从句", 22),
        ("交际用语与情景对话", 20), ("词汇运用", 30), ("阅读理解技能", 22),
    ],
    "语文": [
        ("字音字形", 30), ("词语运用", 26), ("病句修改", 28), ("标点符号", 20),
        ("修辞手法", 22), ("句子衔接与仿写", 18), ("文学文化常识", 26),
        ("古诗文默写", 40), ("古诗词鉴赏", 28), ("文言文阅读", 32),
        ("课内现代文阅读", 22), ("课外现代文阅读", 28), ("名著导读", 24),
        ("综合性学习", 20), ("记叙文写作指导", 24),
    ],
}

# 并发请求数与单批题量上限
CONCURRENCY = 3
CHUNK_SIZE = 10
MAX_ATTEMPTS = 5
CORRECTION_ROUNDS = 10  # 每学科纠偏轮数上限（防 API 长期异常时死循环）

# 全局日志文件句柄（--progress 指定后，进度实时落盘）
LOG_FH = None


def emit(line):
    """打印一行进度（同时写入 --progress 指定的日志文件）。"""
    print(line, flush=True)
    if LOG_FH is not None:
        LOG_FH.write(line + "\n")
        LOG_FH.flush()


# ============================================================
# 配额计算
# ============================================================
def alloc_largest_remainder(total, parts):
    """按 parts 占比把 total 分摊为整数（最大余数法，和恰为 total）。"""
    if not parts or total <= 0:
        return [0] * len(parts)
    sum_p = sum(parts)
    base = [total * p / sum_p for p in parts]
    floors = [int(x) for x in base]
    rest = total - sum(floors)
    order = sorted(range(len(parts)), key=lambda i: base[i] - floors[i], reverse=True)
    for i in range(rest):
        floors[order[i % len(order)]] += 1
    return floors


def bucket_quotas(subject):
    """返回该学科 9 个 (题型, 难度) 配额字典（和 = 500）。"""
    sizes = TYPE_SIZES[subject]
    types = list(sizes.keys())
    counts = [sizes[t] for t in types]
    easy = alloc_largest_remainder(150, counts)   # 简单 30%
    hard = alloc_largest_remainder(100, counts)   # 较难 20%
    quotas = {}
    for i, t in enumerate(types):
        quotas[(t, "简单")] = easy[i]
        quotas[(t, "中等")] = counts[i] - easy[i] - hard[i]  # 剩余即中等 50%
        quotas[(t, "较难")] = hard[i]
    return quotas


# ============================================================
# DeepSeek API 调用
# ============================================================
def _http_post(payload, timeout=180):
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + DEEPSEEK_API_KEY,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def chat_json(system, user):
    """调用 chat 接口并返回 message.content 文本；带指数退避重试。"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.7,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }
    last_err = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            data = _http_post(payload)
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                pass
            last_err = f"HTTP {e.code} {body}"
            if e.code < 500 and e.code != 429:
                raise RuntimeError(last_err)  # 参数等 4xx 错误无需重试
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
        time.sleep(min(2 ** attempt * 2, 60) + random.uniform(0, 2))
    raise RuntimeError(f"多次请求失败：{last_err}")


def extract_json(text):
    """从模型输出里稳健提取 JSON 对象。"""
    if not text:
        return None
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except ValueError:
            pass
    return None


def gen_batch(subject, topic, count, bucket=None):
    """生成一批原始题目（bucket=(题型,难度) 时只生成该题型该难度）。

    解析失败时自动换一轮重新请求（最多 3 次），提高成功命中率。
    """
    if bucket:
        ty, di = bucket
        mix_line = f"本批请恰好生成 {count} 道「{ty}」，全部为「{di}」难度。"
    else:
        mix_line = (
            f"本批请恰好生成 {count} 道题，三种题型都要覆盖"
            f"（选择题、填空题、解答题大约 4:3:3），"
            f"难度大致 简单30% / 中等50% / 较难20%。"
        )
    user = f"""你是资深中考命题专家，熟悉「{subject}」初中全部考点与中考命题规范。

请围绕学科「{subject}」的知识板块「{topic}」出题（覆盖该板块核心概念、公式、典型题型、易错点，题目不要重复）。

{mix_line}

题目要求：
1. 贴近中考真题风格，表述严谨无歧义，难度与标注一致；
2. 选择题有且仅有一个正确选项，其余为有迷惑性的合理干扰项，
   选项正文不要带「A. 」之类前缀；
3. 填空题只设一个空，题干用 ____ 表示；若多个等价答案均可，用「或」连接，
   如答案可写「1/2 或 0.5」；
4. 解答题必须给出完整规范的分步解答（answer 字段），并在 step_rules 字段
   按得分点给出评分标准（JSON 对象：步骤说明 -> 分值，各项分值之和不超过 20）；
5. 每题 analysis 写简明解析/思路点拨，不写题干复述、选项或自我评价等废话；
6. 数学式子用纯文本：x²、√2、π、≤、≠、1/2 等，禁止 LaTeX；
7. 只输出如下 JSON（不要输出任何多余文字）：
{{"questions": [
  {{"question_type": "选择题", "difficulty": "简单", "content": "题干",
    "option_a": "A项", "option_b": "B项", "option_c": "C项", "option_d": "D项",
    "answer": "A", "analysis": "解析"}},
  {{"question_type": "填空题", "difficulty": "中等", "content": "题干____",
    "answer": "答案", "analysis": "解析"}},
  {{"question_type": "解答题", "difficulty": "较难", "content": "题干",
    "answer": "完整分步解答", "analysis": "思路点拨",
    "step_rules": {{"得分点一": 2, "得分点二": 3, "得分点三": 3}}}}
]}}"""
    system = "你是严格按要求输出 JSON 的中考命题专家。"
    last_reason = ""
    for _ in range(3):
        text = chat_json(system, user)
        obj = extract_json(text)
        # 兼容两种结构：{"questions": [...]} 或直接输出 [...] 数组
        if isinstance(obj, dict) and isinstance(obj.get("questions"), list):
            return obj["questions"]
        if isinstance(obj, list):
            return obj
        last_reason = f"输出结构异常：{str(obj)[:200] if obj else text[:200]}"
    raise RuntimeError("模型输出缺少 questions 数组：" + last_reason)


# ============================================================
# 校验与规范化
# ============================================================
def _clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def validate_item(raw, subject, topic, expect_type=None, expect_diff=None):
    """校验并规范化一道题，非法返回 None。

    说明：模型偶发选项残缺、答案带前缀、解答题缺评分标准等，一律丢弃，
    由「纠偏轮」补足，保证不写入残缺/坏数据。
    """
    if not isinstance(raw, dict):
        return None

    qtype = (raw.get("question_type") or "").strip()
    if qtype not in QUESTION_TYPES:
        # 兜底：四个选项齐全就当选择题（兼容个别漏写题型的输出）
        if all(raw.get(k) for k in ("option_a", "option_b", "option_c", "option_d")):
            qtype = "选择题"
        else:
            return None

    diff = (raw.get("difficulty") or "").strip()
    if diff not in DIFFICULTIES:
        diff = expect_diff if expect_diff in DIFFICULTIES else "中等"

    content = _clean(raw.get("content"))
    answer = str(raw.get("answer") or "").strip()
    analysis = _clean(raw.get("analysis"))
    if not content or not answer or not analysis:
        return None
    if len(content) < 5 or len(content) > 800:
        return None
    if len(analysis) > 600:
        analysis = analysis[:600]

    item = {
        "subject": subject, "topic": topic, "grade": "初中",
        "question_type": qtype, "difficulty": diff,
        "content": content, "answer": answer, "analysis": analysis,
        "option_a": "", "option_b": "", "option_c": "", "option_d": "",
        "score": 3, "step_rules": None,
    }

    if qtype == "选择题":
        opts = [_clean(raw.get(k)) for k in ("option_a", "option_b", "option_c", "option_d")]
        if any(not o for o in opts) or len(set(opts)) < 4:
            return None
        letter = answer.upper()
        if letter not in ("A", "B", "C", "D"):
            return None
        item.update({"option_a": opts[0], "option_b": opts[1],
                     "option_c": opts[2], "option_d": opts[3],
                     "answer": letter, "score": 3})

    elif qtype == "填空题":
        if len(answer) > 120:
            return None
        item["answer"] = answer
        item["score"] = 3
        # 题干必须带且只带一个空位标记（前端据此保持「单空填空」语义）
        blanks = re.findall(r"[_＿]{2,}|（\s*）|\(\s*\)", content)
        if not blanks:
            item["content"] = content + "（请填空：____）"
        elif len(blanks) > 1:
            return None

    else:  # 解答题
        if len(answer) < 20:
            return None
        rules_raw = raw.get("step_rules")
        if isinstance(rules_raw, str):
            try:
                rules_raw = json.loads(rules_raw)
            except ValueError:
                rules_raw = None
        if not isinstance(rules_raw, dict):
            return None
        rules, total = {}, 0
        for k, v in rules_raw.items():
            try:
                pt = int(v)
            except (TypeError, ValueError):
                continue
            key = _clean(k)
            if pt > 0 and key:
                rules[key[:80]] = pt
                total += pt
        if len(rules) < 2 or total <= 0:
            return None
        if total > 20:
            return None  # 评分分值和异常，视为坏数据
        item["score"] = total          # 满分与评分标准自洽
        item["step_rules"] = json.dumps(rules, ensure_ascii=False)

    return item


def item_key(item):
    """题目去重键：科目 + 题干。"""
    return hashlib.sha1(
        (item["subject"] + "|" + item["content"]).encode("utf-8")).hexdigest()


# ============================================================
# 数据库
# ============================================================
def connect_db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_schema(conn):
    """确保 questions/answer_records 具备全部所需列（兼容新老库/全新库）。"""
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "questions" not in tables:
        sys.path.insert(0, ROOT)
        import db as db_mod
        conn.executescript(db_mod.SCHEMA)
        conn.commit()
    cols = {t: {r[1] for r in conn.execute(
        f"PRAGMA table_info({t})").fetchall()} for t in ("questions", "answer_records")}
    extra = {
        "questions": [("topic", "TEXT"), ("grade", "TEXT"),
                      ("question_type", "TEXT"), ("difficulty", "TEXT"),
                      ("score", "INTEGER DEFAULT 3"), ("step_rules", "TEXT")],
        "answer_records": [("score", "INTEGER NOT NULL DEFAULT 0")],
    }
    for table, adds in extra.items():
        for col, ddl in adds:
            if col not in cols.get(table, set()):
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    conn.commit()


def clear_questions(conn, user_id):
    """清空某用户全部旧题目（外键级联清理答题记录）。"""
    conn.execute("DELETE FROM questions WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM sqlite_sequence WHERE name = 'questions'")
    conn.commit()


def insert_question(conn, item, user_id, now):
    conn.execute(
        """INSERT INTO questions
           (user_id, subject, topic, grade, question_type, difficulty, score,
            content, option_a, option_b, option_c, option_d, answer,
            analysis, step_rules, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, item["subject"], item["topic"], item["grade"],
         item["question_type"], item["difficulty"], item["score"],
         item["content"], item["option_a"], item["option_b"],
         item["option_c"], item["option_d"], item["answer"],
         item["analysis"], item["step_rules"], now, now))


# ============================================================
# 生成主流程
# ============================================================
def now_str():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def count_buckets(conn, user_id, subject):
    """统计该学科各 (题型, 难度) 现有题量。"""
    result = {}
    for row in conn.execute(
            """SELECT question_type, difficulty, COUNT(*) AS c FROM questions
               WHERE user_id = ? AND subject = ?
               GROUP BY question_type, difficulty""",
            (user_id, subject)).fetchall():
        result[(row["question_type"], row["difficulty"])] = row["c"]
    return result


def run_subject(conn, user_id, subject, seen):
    """生成一个学科：第一轮按主题铺量 + 多轮按(题型,难度)配额纠偏。"""
    emit(f"===== 开始生成：{subject} =====")
    quotas = bucket_quotas(subject)
    topic_pool = [t for t, _ in SUBJECT_TOPICS[subject]]
    stats = {"added": 0, "dup": 0, "invalid": 0}

    # 主题轮转指针：优先补题量少的主题（覆盖均衡）
    topic_count = {t: 0 for t in topic_pool}

    def pick_topic():
        min_c = min(topic_count.values())
        cands = [t for t in topic_pool if topic_count[t] == min_c]
        return random.choice(cands)

    def add_item(item):
        """校验通过后写库（去重）。"""
        key = item_key(item)
        if key in seen:
            stats["dup"] += 1
            return False
        seen.add(key)
        topic_count[item["topic"]] = topic_count.get(item["topic"], 0) + 1
        stats["added"] += 1
        insert_question(conn, item, user_id, now_str())
        return True

    def collect(raw_list, topic, expect=None):
        """把一批原始题经校验后写库；返回有效数。"""
        got = 0
        for raw in raw_list:
            et = expect[0] if expect else None
            ed = expect[1] if expect else None
            item = validate_item(raw, subject, topic, et, ed)
            if item is None:
                stats["invalid"] += 1
                continue
            if add_item(item):
                got += 1
        conn.commit()
        return got

    # ---- 第一轮：按主题铺量（并发请求，主线程校验写库） ----
    tasks = []   # (topic, count)
    for topic, weight in SUBJECT_TOPICS[subject]:
        n = weight
        while n > 0:
            tasks.append((topic, min(CHUNK_SIZE, n)))
            n -= CHUNK_SIZE

    done_first_round = 0
    for i in range(0, len(tasks), CONCURRENCY):
        chunk = tasks[i:i + CONCURRENCY]
        with ThreadPoolExecutor(max_workers=len(chunk)) as ex:
            futures = {ex.submit(gen_batch, subject, topic, cnt): (topic, cnt)
                       for topic, cnt in chunk}
            for fut in futures:
                topic, cnt = futures[fut]
                try:
                    raw_list = fut.result()
                except Exception as e:
                    emit(f"  [{subject}/{topic}] 生成失败：{e}")
                    stats["invalid"] += cnt
                    continue
                got = collect(raw_list, topic)
                done_first_round += got
        emit(f"  [{subject}] 第一轮完成 {done_first_round} 题"
             f"（累计 去重{stats['dup']} 无效{stats['invalid']}）")

    # ---- 纠偏轮：补齐 (题型, 难度) 配额 ----
    for rnd in range(1, CORRECTION_ROUNDS + 1):
        cur = count_buckets(conn, user_id, subject)
        missing = {k: quotas[k] - cur.get(k, 0) for k in quotas if cur.get(k, 0) < quotas[k]}
        if not missing:
            break
        emit(f"  [{subject}] 纠偏第 {rnd} 轮缺口："
             + ", ".join(f"{k[0]}{k[1]}+{v}" for k, v in sorted(missing.items())))
        filled_this_round = 0
        for bucket in sorted(missing):
            need = missing[bucket]
            while need > 0:
                topic = pick_topic()
                cnt = min(CHUNK_SIZE, need)
                try:
                    raw_list = gen_batch(subject, topic, cnt, bucket=bucket)
                except Exception as e:
                    emit(f"  [{subject}/{topic}] 纠偏生成失败：{e}")
                    break
                got = collect(raw_list, topic, expect=bucket)
                filled_this_round += got
                need -= got
                if got == 0:
                    break  # 连续无效则跳出，交下一轮处理
        emit(f"  [{subject}] 纠偏第 {rnd} 轮新增 {filled_this_round} 题")
        if filled_this_round == 0:
            break  # 一轮毫无进展说明 API 异常，直接结束避免死循环

    # ---- 收尾归一化：裁掉超出配额的题，保证每科恰好 500 且 9 个桶精确达标 ----
    trimmed = 0
    for (ty, di), quota in quotas.items():
        row = conn.execute(
            """SELECT COUNT(*) AS c FROM questions
               WHERE user_id = ? AND subject = ? AND question_type = ? AND difficulty = ?""",
            (user_id, subject, ty, di)).fetchone()
        excess = row["c"] - quota
        if excess > 0:
            ids = [r["id"] for r in conn.execute(
                """SELECT id FROM questions
                   WHERE user_id = ? AND subject = ? AND question_type = ? AND difficulty = ?
                   ORDER BY id DESC LIMIT ?""",
                (user_id, subject, ty, di, excess)).fetchall()]
            for qid in ids:
                conn.execute("DELETE FROM questions WHERE id = ?", (qid,))
                trimmed += 1
    conn.commit()
    if trimmed:
        emit(f"  [{subject}] 归一化裁剪超出配额 {trimmed} 题")

    cur = count_buckets(conn, user_id, subject)
    for k in quotas:
        cur.setdefault(k, 0)
    total = sum(cur.values())
    emit(f"===== {subject} 完成：共 {total} 道 "
         f"(新增 {stats['added']} 去重 {stats['dup']} 无效 {stats['invalid']}"
         f" 裁剪 {trimmed}) =====")
    return stats

def main():
    global LOG_FH
    parser = argparse.ArgumentParser(description="初中全科题库生成器")
    parser.add_argument("--subject", default="", help="只生成指定学科（默认全部）")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite 数据库路径")
    parser.add_argument("--user", type=int, default=DEFAULT_USER_ID, help="归属 user_id")
    parser.add_argument("--yes", action="store_true", help="跳过清空确认")
    parser.add_argument("--progress", default="", help="进度日志文件路径（可选）")
    args = parser.parse_args()

    subjects = [args.subject] if args.subject else list(TYPE_SIZES.keys())
    for s in subjects:
        if s not in TYPE_SIZES:
            print(f"未知学科：{s}（可选 {list(TYPE_SIZES.keys())}）", file=sys.stderr)
            sys.exit(1)

    if args.progress:
        LOG_FH = open(args.progress, "w", encoding="utf-8")

    if not args.yes:
        ans = input(
            f"将清空 {args.db} 中 user_id={args.user} 的全部旧题目并重新生成"
            f"（学科：{subjects}），继续？(y/N): ").strip().lower()
        if ans != "y":
            print("已取消")
            sys.exit(0)

    conn = connect_db(args.db)
    ensure_schema(conn)
    clear_questions(conn, args.user)

    # 初始去重集（清空后为空，保留该逻辑便于将来复用）
    seen = set()

    total = {"added": 0, "dup": 0, "invalid": 0}
    for s in subjects:
        st = run_subject(conn, args.user, s, seen)
        for k in total:
            total[k] += st[k]

    emit(f"\n全部完成：新增 {total['added']}，去重 {total['dup']}，无效 {total['invalid']}")
    emit("\n=== 最终各科统计（难度 简单/中等/较难 = 30%/50%/20%） ===")
    for row in conn.execute(
            """SELECT subject, COUNT(*) AS total,
                      SUM(question_type='选择题') AS c,
                      SUM(question_type='填空题') AS f,
                      SUM(question_type='解答题') AS a,
                      SUM(difficulty='简单') AS e,
                      SUM(difficulty='中等') AS m,
                      SUM(difficulty='较难') AS h
               FROM questions WHERE user_id = ? GROUP BY subject ORDER BY subject""",
            (args.user,)).fetchall():
        emit(f"{row['subject']}: 总数{row['total']} | 选择{row['c']} 填空{row['f']} "
             f"解答{row['a']} | 简单{row['e']} 中等{row['m']} 较难{row['h']}")
    conn.close()
    if LOG_FH is not None:
        LOG_FH.close()


if __name__ == "__main__":
    main()
