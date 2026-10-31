# -*- coding: utf-8 -*-
"""【已废弃，仅供参考】初中全科题库生成器 v0（原型版）。

请改用 tools/build_question_bank.py：
- 支持按学科独立运行、多轮按「题型×难度」配额纠偏、数据校验与去重；
- 生成的题目带 topic/grade/question_type/difficulty/score/step_rules 完整字段，
  与刷题模式（选择题/填空题/解答题）完全兼容。
不要直接运行本文件，否则会清空现有题库并写入缺少校验的旧格式数据。
"""

import json
import os
import sqlite3
from openai import OpenAI

# ============================================================
# 配置
# ============================================================
# 【安全】密钥不再内置在代码里，只从环境变量读取；缺失即拒绝运行。
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
if not DEEPSEEK_API_KEY:
    raise SystemExit(
        "[gen_questions.py 已废弃] 请改用 tools/build_question_bank.py，"
        "并先设置环境变量 DEEPSEEK_API_KEY"
    )
DB_PATH = "data/study_assistant.db"

# ============================================================
# 学科与知识点
# ============================================================

SUBJECTS = {
    "数学": {
        "grade": "初中",
        "topics": [
            "有理数", "整式", "一元一次方程", "二元一次方程组", "不等式",
            "实数", "平面直角坐标系", "一次函数", "反比例函数", "二次函数",
            "三角形", "全等三角形", "勾股定理", "平行四边形", "圆",
            "相似", "锐角三角函数", "投影与视图", "概率初步"
        ]
    },
    "物理": {
        "grade": "初中",
        "topics": [
            "机械运动", "声现象", "物态变化", "光现象", "透镜及其应用",
            "质量与密度", "力", "运动和力", "压强", "浮力",
            "功和机械能", "简单机械", "内能", "电流和电路",
            "电压 电阻", "欧姆定律", "电功率", "电与磁"
        ]
    },
    "化学": {
        "grade": "初中",
        "topics": [
            "走进化学世界", "我们周围的空气", "物质构成的奥秘",
            "自然界的水", "化学方程式", "碳和碳的氧化物",
            "燃料及其利用", "金属和金属材料", "溶液",
            "酸和碱", "盐 化肥", "化学与生活"
        ]
    },
    "英语": {
        "grade": "初中",
        "topics": [
            "名词", "代词", "冠词", "数词", "介词", "连词",
            "形容词", "副词", "动词时态", "被动语态", "非谓语动词",
            "句子种类", "主谓一致", "定语从句", "状语从句"
        ]
    },
    "语文": {
        "grade": "初中",
        "topics": [
            "字音字形", "词语运用", "病句修改", "标点符号",
            "修辞手法", "文学常识", "古诗文默写", "文言文阅读",
            "现代文阅读", "名著导读", "综合性学习"
        ]
    }
}

# ============================================================
# 核心函数
# ============================================================

def get_client():
    return OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com"
    )


def generate_questions(subject, topic):
    """生成 20 道题（5选择 + 5填空 + 10解答）"""
    client = get_client()
    prompt = f"""
你是中考命题专家，精通各学科命题标准。

请根据学科「{subject}」、知识点「{topic}」，生成 20 道题：

1. 选择题：5 道（简单2，中等2，较难1）
2. 填空题：5 道（简单2，中等2，较难1）
3. 解答题：10 道（简单2，中等4，较难4）

输出 JSON 格式：
{{
  "questions": [
    {{"type": "choice", "subject": "{subject}", "topic": "{topic}", "grade": "初中", "difficulty": "easy|medium|hard", "score": 3, "content": "题干", "option_a": "A", "option_b": "B", "option_c": "C", "option_d": "D", "answer": "A", "analysis": "解析"}},
    {{"type": "fill", "subject": "{subject}", "topic": "{topic}", "grade": "初中", "difficulty": "easy|medium|hard", "score": 3, "content": "题干", "answer": "答案", "analysis": "解析"}},
    {{"type": "answer", "subject": "{subject}", "topic": "{topic}", "grade": "初中", "difficulty": "easy|medium|hard", "score": 10, "content": "题干", "answer": "完整解答", "analysis": "解题思路", "step_rules": {{"步骤1": "得分点1"}}}}
  ]
}}
直接输出 JSON，不要额外文字。
"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content)
        return data.get("questions", [])
    except Exception as e:
        print(f"生成失败：{e}")
        return []


def clear_questions():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM questions")
    conn.commit()
    conn.close()
    print("已清空旧题目")


def save_questions(questions, user_id=1):
    if not questions:
        return 0
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    inserted = 0
    for q in questions:
        try:
            q.setdefault("option_a", "")
            q.setdefault("option_b", "")
            q.setdefault("option_c", "")
            q.setdefault("option_d", "")
            q.setdefault("analysis", "")
            q.setdefault("step_rules", {})
            cur.execute("""
                INSERT INTO questions (
                    user_id, subject, topic, grade, question_type, difficulty, score,
                    content, option_a, option_b, option_c, option_d,
                    answer, analysis, step_rules, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id, q.get("subject"), q.get("topic"), q.get("grade"),
                q.get("type"), q.get("difficulty"), q.get("score"),
                q.get("content"), q.get("option_a"), q.get("option_b"),
                q.get("option_c"), q.get("option_d"), q.get("answer"),
                q.get("analysis"), json.dumps(q.get("step_rules", {})),
                "2026-09-02 00:00:00", "2026-09-02 00:00:00"
            ))
            inserted += 1
        except Exception as e:
            print(f"导入失败：{e}")
    conn.commit()
    conn.close()
    return inserted


if __name__ == "__main__":
    print("=" * 50)
    print("初中全科题库生成器")
    print("⚠️ 会清空旧题，请确认已备份")
    print("=" * 50)

    confirm = input("继续？清空旧题并导入新题 (y/n): ")
    if confirm.lower() != "y":
        print("已取消")
        exit()

    clear_questions()

    total = 0
    for subject, info in SUBJECTS.items():
        print(f"\n📚 {subject}")
        for topic in info["topics"]:
            print(f"  {topic}...", end=" ")
            qs = generate_questions(subject, topic)
            if qs:
                n = save_questions(qs)
                total += n
                print(f"✅ {n}道")
            else:
                print("❌ 失败")

    print(f"\n🎉 完成！共导入 {total} 道题")