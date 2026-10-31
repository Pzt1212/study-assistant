# -*- coding: utf-8 -*-
"""在线题库服务：把「用户自备的问答 API」接入本地题库。

设计原则
--------
1. 项目**不内置任何题目**，也不内置任何 API 令牌或地址；
2. API 地址与令牌由使用者自行提供：可在「在线题库」页面填写，
   也可通过环境变量 ``QUESTION_BANK_API_URL`` / ``QUESTION_BANK_TOKEN`` 配置；
3. 默认按「一题一答」的 JSON 接口解析——请求参数 ``q`` 为题目内容，
   响应中取 ``answer`` 字段，兼容三种常见结构：
       {"answer": "..."}
       {"data": {"answer": "..."}}
       {"data": "..."}

接口不匹配时抛 :class:`QuestionBankError`，由蓝图转成页面提示。
"""
import html

import requests

# 单次批量提问上限（避免一次请求过多触发超时/限流）
WKAPI_MAX_QUESTIONS = 20


class QuestionBankError(Exception):
    """题库拉取/导入失败。"""


def _html_unescape(text):
    """HTML 反转义：接口返回的文本可能含 &amp; 等实体，需还原为普通字符。"""
    return html.unescape(text) if text else ""


def _extract_answer(data):
    """从接口响应中提取答案文本。

    兼容 ``{"answer": ...}``、``{"data": {"answer": ...}}``、
    ``{"data": "..."}`` 三种结构；取不到时抛出 QuestionBankError。
    """
    if isinstance(data, str):
        text = _html_unescape(data).strip()
        if text:
            return text
        raise QuestionBankError("接口返回了空字符串。")

    if not isinstance(data, dict):
        raise QuestionBankError("接口返回结构无法解析（既不是 JSON 对象也不是字符串）。")

    answer = data.get("answer")
    if answer is None and isinstance(data.get("data"), dict):
        answer = data["data"].get("answer")
    if answer is None:
        answer = data.get("data")

    if answer is None or str(answer).strip() == "":
        msg = data.get("msg") or data.get("message") or data.get("error") or ""
        raise QuestionBankError(f"接口未返回 answer 字段。{msg}".strip())

    return _html_unescape(str(answer)).strip()


def fetch_answer(api_url, question, token="", timeout=15):
    """向用户配置的题库 API 查询一道题的答案。

    :param api_url:  接口地址（必填）
    :param question: 题目内容
    :param token:    访问令牌（可选，为空时不带 token 参数）
    :param timeout:  请求超时秒数
    :return: 答案文本
    :raises QuestionBankError: 未配置地址、网络失败或接口未返回答案
    """
    api_url = (api_url or "").strip()
    if not api_url:
        raise QuestionBankError(
            "尚未配置题库 API 地址，请在页面填写，或设置环境变量 QUESTION_BANK_API_URL。")

    params = {"q": question}
    if token:
        params["token"] = token
    try:
        resp = requests.get(api_url, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise QuestionBankError(f"无法连接题库 API：{exc}")
    except ValueError:
        raise QuestionBankError("题库 API 返回了非 JSON 数据。")

    return _extract_answer(data)


def build_question(question, answer, subject="在线题库（API）"):
    """把「题目 + 答案」标准化为本项目题目字段格式。

    注意：一题一答接口不返回 A/B/C/D 选项，这里把答案放在 option_a，
    其余选项为占位干扰项，建议导入后在「编辑题目」页补充。
    """
    return {
        "content": question,
        "option_a": answer,
        "option_b": "（占位干扰项，请编辑补充）",
        "option_c": "（占位干扰项，请编辑补充）",
        "option_d": "（占位干扰项，请编辑补充）",
        "answer": "A",
        "analysis": f"答案来源：用户配置的在线题库 API。正确答案为：{answer}。",
        "subject": subject,
    }


def fetch_questions(api_url, questions, token=""):
    """批量查询答案并标准化为题目字段。

    :param api_url:   接口地址
    :param questions: 题目文本列表（每项一道题）
    :param token:     访问令牌（可选）
    :return: 标准化后的题目列表
    :raises QuestionBankError: 任一题目查询失败
    """
    result = []
    for question in questions:
        question = (question or "").strip()
        if not question:
            continue
        answer = fetch_answer(api_url, question, token=token)
        result.append(build_question(question, answer))
    return result
