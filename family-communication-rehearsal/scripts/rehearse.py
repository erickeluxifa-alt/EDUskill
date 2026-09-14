#!/usr/bin/env python3
"""Generate an offline, review-only family communication rehearsal."""
import argparse
import html
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

MAX_TEXT = 600
MAX_ITEMS = 20
MAX_FILE_BYTES = 1_000_000
RISK_TERMS = {
    "labeling": ["懒", "笨", "问题学生", "没救", "差生", "不听话"],
    "absolute": ["总是", "从不", "肯定", "一定是", "根本不"],
    "diagnostic": ["抑郁症", "多动症", "心理有问题", "智力问题"],
    "blaming": ["家长没管", "家庭教育失败", "故意捣乱"],
}
CRISIS_TERMS = ["自伤", "他伤", "想死", "不想活", "危机", "人身安全", "失联"]
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def error_result(*errors):
    return {"status": "INVALID_INPUT", "errors": list(errors), "warnings": [],
            "side_effects": {"message_sent": False, "external_write": False}}


def clean(value):
    value = re.sub(r"[\x00-\x1f\x7f]", " ", value[:MAX_TEXT * 2])
    return re.sub(r"\s+", " ", value).strip()[:MAX_TEXT]


def text(value, field, errors, required=False):
    if value is None:
        if required:
            errors.append(f"{field} 必须是字符串")
        return ""
    if not isinstance(value, str):
        errors.append(f"{field} 必须是字符串")
        return ""
    cleaned = clean(value)
    if required and not cleaned:
        errors.append(f"{field} 不能为空")
    return cleaned


def safe_list(value, field, errors):
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{field} 必须是数组")
        return []
    if len(value) > MAX_ITEMS:
        errors.append(f"{field} 最多包含 {MAX_ITEMS} 项")
        return []
    cleaned = []
    for index, item in enumerate(value):
        item_text = text(item, f"{field}[{index + 1}]", errors)
        if item_text:
            cleaned.append(item_text)
    return cleaned


def valid_date(value):
    if not DATE_RE.match(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def scan_risks(texts):
    findings = []
    joined = " ".join(texts)
    for category, terms in RISK_TERMS.items():
        matches = sorted({term for term in terms if term in joined})
        if matches:
            findings.append({"category": category, "terms": matches,
                             "action": "保留原始事实供复核，正式沟通前改为具体、可观察、非定性的表达"})
    if any(term in joined for term in CRISIS_TERMS):
        findings.append({"category": "safety_signal", "terms": [term for term in CRISIS_TERMS if term in joined],
                         "action": "停止常规沟通预演，立即转学校既有人工安全处置流程"})
    return findings


def rehearse(payload):
    if not isinstance(payload, dict):
        return error_result("输入必须是 JSON 对象")
    errors = []
    student = payload.get("student")
    if not isinstance(student, dict):
        errors.append("student 必须是对象")
        student = {}
    student_id = text(student.get("id"), "student.id", errors)
    student_name = text(student.get("name"), "student.name", errors)
    if not student_id and not student_name and not any(item.startswith("student.") for item in errors):
        errors.append("student.id 或 student.name 至少提供一个")
    raw_observations = payload.get("observations")
    if not isinstance(raw_observations, list) or not raw_observations:
        errors.append("observations 必须是非空数组")
        raw_observations = []
    elif len(raw_observations) > MAX_ITEMS:
        errors.append(f"observations 最多包含 {MAX_ITEMS} 项，禁止静默截断")
        raw_observations = []
    observations = []
    for index, item in enumerate(raw_observations, 1):
        if not isinstance(item, dict):
            errors.append(f"observations[{index}] 必须是对象")
            continue
        date = text(item.get("date"), f"observations[{index}].date", errors, required=True)
        domain = text(item.get("domain"), f"observations[{index}].domain", errors, required=True)
        fact = text(item.get("fact"), f"observations[{index}].fact", errors, required=True)
        source = text(item.get("source", "未提供来源"), f"observations[{index}].source", errors, required=True)
        date_ok = valid_date(date)
        if date and not date_ok:
            errors.append(f"observations[{index}].date 必须是有效 YYYY-MM-DD 日期")
        if date_ok and domain and fact and source:
            observations.append({"date": date, "domain": domain, "fact": fact, "source": source})
    strengths = safe_list(payload.get("strengths"), "strengths", errors)
    supports = safe_list(payload.get("support_options"), "support_options", errors)
    actions = safe_list(payload.get("requested_actions"), "requested_actions", errors)
    raw_context = payload.get("context")
    if raw_context is not None and not isinstance(raw_context, dict):
        errors.append("context 必须是对象")
        raw_context = {}
    context = raw_context or {}
    purpose = text(context.get("purpose", "常规学习与在校表现沟通"), "context.purpose", errors, required=True)
    channel = text(context.get("channel", "待教师确认"), "context.channel", errors, required=True)
    class_name = text(payload.get("class_name", "未提供"), "class_name", errors, required=True)
    if errors:
        return error_result(*errors)
    observations.sort(key=lambda row: (row["date"], row["domain"]))
    fact_cards = [{**item, "statement": f"{item['date']}，根据{item['source']}，在{item['domain']}方面记录到：{item['fact']}"}
                  for item in observations]
    questions = [f"关于{item['domain']}记录，您是否了解到可能影响这一情况的背景？学校有哪些信息还需要补充核实？"
                 for item in observations[:5]]
    if not strengths:
        strengths = ["未提供已核实优势，请教师补充至少一项具体积极表现"]
    if not supports:
        supports = ["请教师根据学生需要和学校可用资源补充一项可执行支持"]
    if not actions:
        actions = ["确认一项双方可执行的下一步，并约定复核节点"]
    all_text = [student_id, student_name, class_name, purpose, channel]
    for row in observations:
        all_text.extend([row["domain"], row["fact"], row["source"]])
    all_text.extend(strengths + supports + actions)
    risks = scan_risks(all_text)
    safety_escalation = any(item["category"] == "safety_signal" for item in risks)
    agenda = [] if safety_escalation else ["说明沟通目的与隐私范围", "分享具体积极表现", "陈述可核实事实", "开放式核实背景", "讨论支持选项", "确认下一步与复核节点"]
    return {
        "status": "SAFETY_ESCALATION_REQUIRED" if safety_escalation else "REVIEW_REQUIRED",
        "must_stop": safety_escalation,
        "student": {"id": student_id or "未提供", "name": student_name or "未提供"},
        "context": {"class_name": class_name, "purpose": purpose, "channel": channel},
        "agenda": agenda,
        "strengths": [] if safety_escalation else strengths,
        "fact_cards": fact_cards,
        "open_questions": [] if safety_escalation else questions,
        "support_options": [] if safety_escalation else supports,
        "action_items": ["立即转学校既有人工安全处置流程；不要使用常规沟通草稿"] if safety_escalation else actions,
        "risk_review": risks,
        "confirmation": ["事实日期、来源和范围已核实", "沟通对象与渠道符合学校隐私要求", "已移除标签化、诊断性和责备性措辞", "支持选项真实可提供", "行动项责任人与复核节点已确认"],
        "side_effects": {"message_sent": False, "external_write": False, "note": "仅生成待人工确认预览，未接入真实系统"},
    }


def markdown_escape(value):
    escaped = html.escape(value, quote=True)
    return re.sub(r"([\\`*_{}\[\]()<>#+\-.!|])", r"\\\1", escaped)


def markdown(result):
    if result["status"] == "INVALID_INPUT":
        lines = ["# 家校沟通预演：输入需修复", ""] + [f"- {markdown_escape(error)}" for error in result["errors"]]
        return "\n".join(lines) + "\n"
    esc = markdown_escape
    heading = "# 家校沟通预演：安全升级（停止常规预演）" if result.get("must_stop") else "# 家校沟通预演（待人工确认）"
    lines = [heading, "", f"- 班级：{esc(result['context']['class_name'])}",
             f"- 目的：{esc(result['context']['purpose'])}",
             f"- 渠道：{esc(result['context']['channel'])}"]
    if result.get("must_stop"):
        lines += ["", "## 必须立即处理"] + [f"- {esc(item)}" for item in result["action_items"]]
    else:
        lines += ["", "## 建议议程"]
        lines += [f"{i}. {esc(item)}" for i, item in enumerate(result["agenda"], 1)]
        lines += ["", "## 积极表现"] + [f"- {esc(item)}" for item in result["strengths"]]
        lines += ["", "## 开放式核实问题"] + [f"- {esc(item)}" for item in result["open_questions"]]
        lines += ["", "## 可提供支持"] + [f"- {esc(item)}" for item in result["support_options"]]
        lines += ["", "## 待确认行动项"] + [f"- {esc(item)}" for item in result["action_items"]]
    lines += ["", "## 事实卡"] + [f"- {esc(item['statement'])}" for item in result["fact_cards"]]
    lines += ["", "## 风险复核"]
    lines += [f"- [{esc(item['category'])}] 命中：{esc('、'.join(item['terms']))}；建议：{esc(item['action'])}" for item in result["risk_review"]] or ["- 未命中内置高风险措辞；仍需教师人工复核。"]
    lines += ["", "## 正式沟通前确认"] + [f"- [ ] {esc(item)}" for item in result["confirmation"]]
    lines += ["", "> 本文件仅为预览，未发送消息、未写回任何系统。"]
    return "\n".join(lines) + "\n"


def load_payload(path):
    input_path = Path(path)
    try:
        stat = input_path.stat()
        if not input_path.is_file():
            return None, error_result("输入路径必须是普通文件")
        if stat.st_size > MAX_FILE_BYTES:
            return None, error_result(f"输入文件不得超过 {MAX_FILE_BYTES} 字节")
        with input_path.open(encoding="utf-8") as handle:
            return json.load(handle), None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, error_result(f"无法读取输入：{clean(str(exc))}")


def write_outputs(out, result):
    out.mkdir(parents=True, exist_ok=True)
    if not out.is_dir():
        raise OSError("输出路径不是目录")
    contents = {
        "communication_preview.json": json.dumps(result, ensure_ascii=False, indent=2),
        "communication_preview.md": markdown(result),
    }
    temporary = []
    try:
        for name, content in contents.items():
            target = out / name
            if target.is_symlink() or (target.exists() and not target.is_file()):
                raise OSError(f"输出目标不是普通文件：{name}")
            descriptor, temp_name = tempfile.mkstemp(prefix=f".{name}.", dir=out, text=True)
            temporary.append(Path(temp_name))
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        for temp_path, name in zip(temporary, contents):
            temp_path.replace(out / name)
        temporary.clear()
    finally:
        for temp_path in temporary:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


def main():
    parser = argparse.ArgumentParser(description="Generate review-only family communication rehearsal")
    parser.add_argument("input")
    parser.add_argument("--out-dir", default="output")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload, load_error = load_payload(args.input)
    result = load_error or rehearse(payload)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        out = Path(args.out_dir)
        try:
            write_outputs(out, result)
        except OSError as exc:
            print(f"无法写入输出：{clean(str(exc))}", file=sys.stderr)
            return 3
        print(f"status={result['status']} out={out}")
    return 0 if result["status"] == "REVIEW_REQUIRED" else 2


if __name__ == "__main__":
    sys.exit(main())
