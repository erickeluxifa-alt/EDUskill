#!/usr/bin/env python3
"""Offline triage for student-service requests."""
import argparse
import json
import re
import sys

MAX_TEXT = 1000
TOPIC_RULES = [
    ("心理支持", ["自伤", "他伤", "不想活", "崩溃", "想死", "危机", "情绪"], "心理支持/危机处置人员"),
    ("资助事务", ["奖学金", "助学金", "困难认定", "资助", "学费", "贷款"], "学生资助老师"),
    ("学籍教务", ["选课", "学籍", "成绩", "补考", "转专业", "毕业", "证明", "请假"], "教务秘书/辅导员"),
    ("住宿生活", ["宿舍", "住宿", "食堂", "校园卡", "门禁", "维修"], "学生事务/后勤联系人"),
    ("就业实习", ["就业", "实习", "招聘", "简历", "签约", "单位"], "就业或实践管理员"),
    ("技术平台", ["系统", "登录", "密码", "平台", "打不开", "网络", "上传"], "平台管理员/信息中心"),
]
URGENCY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def clean(value):
    value = str(value)
    value = re.sub(r"[\x00-\x1f\x7f]", " ", value)
    return re.sub(r"\s+", " ", value).strip()[:MAX_TEXT]


def classify(text, explicit=None):
    topic, owner = "其他事务", "辅导员/学生服务台"
    for candidate, words, role in TOPIC_RULES:
        if any(word in text for word in words):
            topic, owner = candidate, role
            break
    if explicit in URGENCY_ORDER:
        urgency = explicit
        reason = "采用提交者标注的紧急度，仍需人工复核"
    elif topic == "心理支持" and any(word in text for word in ["自伤", "他伤", "不想活", "想死", "危机"]):
        urgency, reason = "critical", "出现人身安全或危机信号"
    elif topic == "心理支持" or any(word in text for word in ["今天", "马上", "无法上课", "无法入住", "截止", "逾期"]):
        urgency, reason = "high", "存在即时支持、学习生活影响或时限信号"
    elif topic == "其他事务":
        urgency, reason = "low", "当前更像一般信息咨询"
    else:
        urgency, reason = "medium", "需要办理或解释，但未发现即时危机信号"
    return topic, owner, urgency, reason


def action_and_reply(topic, urgency):
    if urgency == "critical":
        return ("立即由人工确认安全状况，按学校既有危机处置流程联系专业支持；不要等待自动回复。",
                "我已看到你的求助。这个情况需要老师尽快人工联系并按学校紧急支持流程处理，请先确保自己处于安全地点，并通过学校已公布的紧急求助渠道联系专业人员。此消息仅为待确认草稿。")
    if topic == "心理支持":
        return ("优先由辅导员人工确认需求，必要时转心理中心；不做诊断。",
                "谢谢你告诉我这些。我会安排老师尽快和你确认需要的支持，也可以由你选择合适的咨询渠道和时间。此消息仅为待确认草稿。")
    if urgency == "high":
        return ("当天由责任角色人工首响，核对截止时间或影响范围后办理/转交。",
                "收到你的问题，我会优先核对办理要求和时间，并在人工确认后回复你下一步怎么做。此消息仅为待确认草稿。")
    return ("按主题进入责任角色队列，补齐材料或具体诉求后处理。",
            "收到你的咨询。我会先核对相关办理信息，确认后回复所需材料、办理方式或对应联系人。此消息仅为待确认草稿。")


def triage(payload):
    if not isinstance(payload, dict):
        return {"status": "INVALID_INPUT", "error": "输入必须是 JSON 对象"}
    raw = payload.get("items", payload.get("requests"))
    if not isinstance(raw, list) or not raw:
        return {"status": "INVALID_INPUT", "error": "items/requests 必须是非空数组"}
    max_items = payload.get("max_items", len(raw))
    if not isinstance(max_items, int) or not 1 <= max_items <= 100:
        return {"status": "INVALID_INPUT", "error": "max_items 范围必须为 1—100"}
    queue, drafts, handoffs = [], [], []
    invalid = 0
    for index, item in enumerate(raw[:max_items], 1):
        if not isinstance(item, dict) or not clean(item.get("text", "")):
            invalid += 1
            continue
        text = clean(item["text"])
        item_id = clean(item.get("id", f"Q{index:02d}")) or f"Q{index:02d}"
        topic, owner, urgency, reason = classify(text, clean(item.get("urgency", "")))
        action, reply = action_and_reply(topic, urgency)
        record = {"id": item_id, "student": clean(item.get("student", "未提供")), "topic": topic,
                  "urgency": urgency, "reason": reason, "owner_role": owner,
                  "recommended_action": action, "draft_reply": reply, "status": "待人工确认"}
        queue.append(record)
        drafts.append({"id": item_id, "draft_reply": reply, "status": "待人工确认"})
        if urgency in ("critical", "high"):
            handoffs.append({"id": item_id, "to": owner, "reason": reason, "status": "待人工转交确认"})
    queue.sort(key=lambda row: (URGENCY_ORDER[row["urgency"]], row["id"]))
    counts = {level: sum(row["urgency"] == level for row in queue) for level in URGENCY_ORDER}
    return {"status": "OK", "summary": {"received": min(len(raw), max_items), "valid": len(queue),
            "invalid": invalid, "urgency_counts": counts, "critical_or_high": counts["critical"] + counts["high"]},
            "queue": queue, "reply_drafts": drafts, "handoff_preview": handoffs,
            "side_effects": {"external_write": False, "message_sent": False, "note": "仅生成预览，未接入真实系统"}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin)
        result = triage(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        result = {"status": "INVALID_INPUT", "error": f"JSON 解析失败: {exc.msg if hasattr(exc, 'msg') else '编码错误'}"}
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if result["status"] == "OK" else 2


if __name__ == "__main__":
    sys.exit(main())
