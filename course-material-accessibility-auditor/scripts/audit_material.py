#!/usr/bin/env python3
import argparse, json, re, sys
from pathlib import Path

GENERIC_LINKS = {"点击这里", "点此", "更多", "详情", "链接", "click here", "more", "read more"}
PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def issue(code, severity, location, message, suggestion, evidence=""):
    return {"code": code, "severity": severity, "location": location, "message": message,
            "suggestion": suggestion, "evidence": evidence[:80]}


def require_list(data, key):
    value = data.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{key} 必须是数组")
    return value


def audit(data):
    if not isinstance(data, dict):
        raise ValueError("顶层 JSON 必须是对象")
    issues = []
    title = data.get("title", "")
    if not isinstance(title, str) or not title.strip():
        issues.append(issue("TITLE_MISSING", "high", "title", "缺少清晰材料标题", "补充能说明课程与任务的标题"))
    sections = require_list(data, "sections")
    if not sections:
        issues.append(issue("SECTION_MISSING", "blocker", "sections", "材料没有可审核章节", "至少提供一个章节"))
    previous = 0
    all_text = []
    for idx, section in enumerate(sections):
        if not isinstance(section, dict):
            raise ValueError(f"sections[{idx}] 必须是对象")
        heading = section.get("heading", "")
        level = section.get("level", 1)
        paragraphs = section.get("paragraphs", [])
        if not isinstance(heading, str) or not heading.strip():
            issues.append(issue("HEADING_EMPTY", "high", f"sections[{idx}].heading", "章节标题为空", "补充描述该部分目的的标题"))
        if not isinstance(level, int) or level < 1 or level > 6:
            raise ValueError(f"sections[{idx}].level 必须是 1-6 的整数")
        if (previous and level > previous + 1) or (not previous and level > 1):
            prior_label = f"H{previous}" if previous else "文档起始"
            issues.append(issue("HEADING_LEVEL_SKIP", "blocker", f"sections[{idx}].level", f"标题层级从 {prior_label} 跳到 H{level}", "从 H1 开始并按连续层级重排标题"))
        previous = level
        if not isinstance(paragraphs, list) or any(not isinstance(p, str) for p in paragraphs):
            raise ValueError(f"sections[{idx}].paragraphs 必须是字符串数组")
        for pidx, paragraph in enumerate(paragraphs):
            all_text.append((f"sections[{idx}].paragraphs[{pidx}]", paragraph))
            if len(paragraph) > 400:
                issues.append(issue("PARAGRAPH_LONG", "medium", all_text[-1][0], "段落超过 400 字，扫读困难", "拆分段落并增加小标题", paragraph))
            for sentence in re.split(r"[。！？.!?]", paragraph):
                if len(sentence.strip()) > 120:
                    issues.append(issue("SENTENCE_LONG", "medium", all_text[-1][0], "存在超过 120 字的长句", "拆分为短句并显式标注步骤", sentence))
                    break
    for idx, image in enumerate(require_list(data, "images")):
        if not isinstance(image, dict):
            raise ValueError(f"images[{idx}] 必须是对象")
        alt = image.get("alt", "")
        if not image.get("decorative", False) and (not isinstance(alt, str) or not alt.strip() or alt.strip().lower() in {"图片", "image", "图"}):
            issues.append(issue("IMG_ALT_MISSING", "blocker", f"images[{idx}].alt", "信息图片缺少有效替代文本", "描述图片传达的关键信息和用途"))
    for idx, link in enumerate(require_list(data, "links")):
        if not isinstance(link, dict):
            raise ValueError(f"links[{idx}] 必须是对象")
        text = str(link.get("text", "")).strip().lower()
        if not text or text in GENERIC_LINKS:
            issues.append(issue("LINK_TEXT_GENERIC", "high", f"links[{idx}].text", "链接文字脱离上下文后含义不清", "改成资源名称或动作目的", text))
    for idx, table in enumerate(require_list(data, "tables")):
        if not isinstance(table, dict):
            raise ValueError(f"tables[{idx}] 必须是对象")
        if not str(table.get("caption", "")).strip():
            issues.append(issue("TABLE_CAPTION_MISSING", "high", f"tables[{idx}].caption", "表格缺少标题或说明", "补充表格主题和阅读目的"))
        headers = table.get("headers", [])
        if not isinstance(headers, list) or not headers:
            issues.append(issue("TABLE_HEADER_MISSING", "blocker", f"tables[{idx}].headers", "表格未标识表头", "明确每列或每行表头"))
    combined = "\n".join(text for _, text in all_text)
    for match in PHONE_RE.finditer(combined):
        issues.append(issue("PII_PHONE", "high", "content", "发现疑似手机号", "发布前删除、脱敏或确认授权", match.group()[:3] + "****" + match.group()[-4:]))
    for match in EMAIL_RE.finditer(combined):
        local, domain = match.group().split("@", 1)
        issues.append(issue("PII_EMAIL", "high", "content", "发现疑似邮箱地址", "发布前删除、脱敏或确认授权", local[:1] + "***@" + domain))
    order = {"blocker": 0, "high": 1, "medium": 2, "low": 3}
    issues.sort(key=lambda x: (order[x["severity"]], x["location"], x["code"]))
    summary = {key: sum(i["severity"] == key for i in issues) for key in order}
    return {"title": title, "summary": summary, "issues": issues,
            "release_preview": {"status": "blocked" if summary["blocker"] else "ready_for_human_review",
                                "requires_human_confirmation": True,
                                "automatic_changes": False}}


def report(result):
    lines = [f"# 课程材料审核报告：{result['title'] or '未命名材料'}", "",
             f"- 状态：`{result['release_preview']['status']}`", "- 发布前必须人工确认：是", "- 自动修改源材料：否", "",
             "## 汇总", "", "| 阻断 | 高 | 中 | 低 |", "|---:|---:|---:|---:|",
             f"| {result['summary']['blocker']} | {result['summary']['high']} | {result['summary']['medium']} | {result['summary']['low']} |", "", "## 问题清单", ""]
    if not result["issues"]:
        lines.append("未发现规则命中；仍建议使用键盘与屏幕阅读器做人工抽查。")
    for n, item in enumerate(result["issues"], 1):
        lines += [f"### {n}. [{item['severity']}] {item['message']}", f"- 位置：`{item['location']}`", f"- 建议：{item['suggestion']}"]
        if item["evidence"]:
            lines.append(f"- 脱敏证据：`{item['evidence']}`")
        lines.append("")
    lines += ["## 发布前确认", "", "- [ ] 已处理全部阻断项", "- [ ] 已核实图片替代文本与表格语义", "- [ ] 已清理或授权个人信息", "- [ ] 已进行人工可用性抽查"]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Audit structured course material accessibility")
    parser.add_argument("input")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        data = json.loads(Path(args.input).read_text(encoding="utf-8"))
        result = audit(data)
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "report.md").write_text(report(result), encoding="utf-8")
        print(json.dumps({"output": str(out), "summary": result["summary"], "status": result["release_preview"]["status"]}, ensure_ascii=False))
        return 2 if result["summary"]["blocker"] else 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"输入错误：{exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
