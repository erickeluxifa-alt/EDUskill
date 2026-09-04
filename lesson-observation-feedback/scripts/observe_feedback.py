#!/usr/bin/env python3
"""Turn lesson-observation notes into evidence-based feedback."""
import argparse
import html
import json
import sys
from pathlib import Path

DIMENSIONS = {
    "objective": "目标与任务",
    "interaction": "课堂互动",
    "evidence": "学习证据",
    "differentiation": "分层支持",
    "closure": "总结与迁移",
}

ACTIONS = {
    "objective": "把本节课目标改写成可观察的学生产出，并在开课 3 分钟内让学生复述成功标准。",
    "interaction": "为每个核心问题预留独立思考和同伴互证，再随机抽取不同层次学生展示，记录参与覆盖。",
    "evidence": "在中段加入一个 2 分钟快速检测，按答案把后续讲解分成‘继续/补讲/挑战’三路。",
    "differentiation": "为基础薄弱和进阶学生各准备一个同题异阶支架，避免只用统一难度任务。",
    "closure": "用‘我学会了什么/证据是什么/下一步怎么用’三句式收束，并布置一个迁移任务。",
}


def load(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取有效 JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("输入顶层必须是对象")
    required = ["course", "grade", "lesson_date", "observations"]
    missing = [key for key in required if not data.get(key)]
    if missing:
        raise ValueError("缺少必填字段: " + ", ".join(missing))
    if not isinstance(data["observations"], list) or not data["observations"]:
        raise ValueError("observations 必须是非空数组")
    return data


def bounded_score(value):
    try:
        return max(1, min(5, int(value)))
    except (TypeError, ValueError):
        return 3


def normalize(data):
    notes = []
    invalid = []
    for index, item in enumerate(data["observations"], 1):
        if not isinstance(item, dict):
            invalid.append(f"第{index}条不是对象")
            continue
        dimension = item.get("dimension")
        evidence_value = item.get("evidence")
        impact_value = item.get("impact")
        if not isinstance(dimension, str) or dimension not in DIMENSIONS or not isinstance(evidence_value, str) or not evidence_value.strip():
            invalid.append(f"第{index}条需包含合法 dimension 和 evidence")
            continue
        evidence = evidence_value.strip()
        impact = impact_value.strip() if isinstance(impact_value, str) else ""
        notes.append({
            "id": item.get("id", f"obs-{index}"),
            "dimension": dimension,
            "dimension_name": DIMENSIONS[dimension],
            "evidence": evidence,
            "impact": impact or "待补充影响描述",
            "severity": bounded_score(item.get("severity", 3)),
            "confidence": bounded_score(item.get("confidence", 3)),
        })
    if not notes:
        raise ValueError("没有可处理的观察记录")
    return notes, invalid


def build(data, notes, invalid):
    grouped = {}
    for note in notes:
        grouped.setdefault(note["dimension"], []).append(note)
    priorities = []
    for dimension, items in grouped.items():
        score = round(sum(x["severity"] * x["confidence"] for x in items) / len(items), 2)
        priorities.append({
            "dimension": dimension,
            "dimension_name": DIMENSIONS[dimension],
            "score": score,
            "evidence_count": len(items),
            "action": ACTIONS[dimension],
            "check_next_time": f"下次听课检查：{DIMENSIONS[dimension]}是否出现可记录的学生行为证据。",
        })
    priorities.sort(key=lambda x: (-x["score"], x["dimension"]))
    return {
        "meta": {"course": data["course"], "grade": data["grade"], "lesson_date": data["lesson_date"], "observer": data.get("observer", "未提供")},
        "summary": {
            "observation_count": len(notes),
            "valid_count": len(notes),
            "invalid_count": len(invalid),
            "overall_message": "优先改进课堂中最影响学生学习证据的环节，先做小步试验，再用下一次观察记录验证。",
        },
        "evidence": notes,
        "priorities": priorities[:3],
        "follow_up_preview": {
            "status": "待人工确认",
            "teacher_message_draft": f"关于{data['course']}本次听课，建议先聚焦：" + "、".join(x["dimension_name"] for x in priorities[:3]) + "。以上建议基于现场记录生成，请结合课程目标确认后使用。",
            "next_observation_window": "下次同主题课或 1-2 周内（由人工填写）",
        },
        "warnings": invalid + (["内容仅代表观察样本，不等同于对教师能力的定性评价。"]),
    }


def escape_md(value):
    escaped = html.escape(str(value), quote=False)
    return escaped.replace("\\", "\\\\").replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def markdown(report):
    meta = report["meta"]
    lines = [f"# 听课反馈与复课验证预览\n", f"- 课程：{escape_md(meta['course'])}\n- 年级：{escape_md(meta['grade'])}\n- 听课日期：{escape_md(meta['lesson_date'])}\n- 观察人：{escape_md(meta['observer'])}\n", "## 结论摘要\n", report["summary"]["overall_message"], f"\n有效观察 {report['summary']['valid_count']} 条，跳过 {report['summary']['invalid_count']} 条。\n", "## 证据记录\n", "| 维度 | 现场证据 | 学习影响 | 严重度 | 置信度 |\n|---|---|---|---:|---:|"]
    for item in report["evidence"]:
        lines.append(f"| {escape_md(item['dimension_name'])} | {escape_md(item['evidence'])} | {escape_md(item['impact'])} | {item['severity']} | {item['confidence']} |")
    lines += ["\n## 优先改进动作\n"]
    for i, item in enumerate(report["priorities"], 1):
        lines += [f"### {i}. {escape_md(item['dimension_name'])}（优先分 {item['score']}）", f"- 证据条数：{item['evidence_count']}", f"- 建议动作：{escape_md(item['action'])}", f"- 复课核验：{escape_md(item['check_next_time'])}\n"]
    lines += ["## 人工确认预览\n", f"- 状态：{escape_md(report['follow_up_preview']['status'])}", f"- 教师反馈草稿：{escape_md(report['follow_up_preview']['teacher_message_draft'])}", f"- 下次观察窗口：{escape_md(report['follow_up_preview']['next_observation_window'])}", "\n## 限制\n"]
    lines.extend(f"- {escape_md(warning)}" for warning in report["warnings"])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="生成证据化听课反馈")
    parser.add_argument("input", help="输入 JSON 文件")
    parser.add_argument("--out-dir", default=".", help="输出目录")
    args = parser.parse_args()
    try:
        data = load(args.input)
        notes, invalid = normalize(data)
        report = build(data, notes, invalid)
    except ValueError as exc:
        print(f"输入错误: {exc}", file=sys.stderr)
        return 2
    out = Path(args.out_dir)
    try:
        out.mkdir(parents=True, exist_ok=True)
        (out / "observation_feedback.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "observation_feedback.md").write_text(markdown(report), encoding="utf-8")
    except OSError as exc:
        print(f"输出错误: 无法写入结果目录: {exc}", file=sys.stderr)
        return 3
    print(json.dumps({"status": "ok", "files": ["observation_feedback.json", "observation_feedback.md"], "priority_count": len(report["priorities"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
