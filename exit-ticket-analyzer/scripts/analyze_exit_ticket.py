#!/usr/bin/env python3
"""Offline formative analysis for exit-ticket responses."""
import argparse
import html
import json
import math
import sys
from pathlib import Path

MAX_STUDENTS = 1000
MAX_QUESTIONS = 100


def text(value, limit=120):
    return str(value).replace("|", "/").replace("\n", " ").replace("\r", " ")[:limit]


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    return float(value)


def load_data(raw):
    issues = []
    if not isinstance(raw, dict):
        return None, [{"level": "error", "target": "root", "message": "输入顶层必须是 JSON 对象"}]
    questions = raw.get("questions")
    students = raw.get("students")
    if not isinstance(questions, list) or not questions:
        issues.append({"level": "error", "target": "questions", "message": "questions 必须是非空列表"})
    if not isinstance(students, list) or not students:
        issues.append({"level": "error", "target": "students", "message": "students 必须是非空列表"})
    if issues:
        return None, issues
    if len(questions) > MAX_QUESTIONS:
        issues.append({"level": "error", "target": "questions", "message": f"题目超过 {MAX_QUESTIONS} 道，已截断"})
        questions = questions[:MAX_QUESTIONS]
    if len(students) > MAX_STUDENTS:
        issues.append({"level": "error", "target": "students", "message": f"学生超过 {MAX_STUDENTS} 人，已截断"})
        students = students[:MAX_STUDENTS]
    clean_questions, ids = [], set()
    for i, item in enumerate(questions):
        tag = f"questions[{i}]"
        if not isinstance(item, dict):
            issues.append({"level": "error", "target": tag, "message": "题目必须是对象"})
            continue
        qid = item.get("id")
        topic = item.get("topic")
        maximum = number(item.get("max_score"))
        if not isinstance(qid, str) or not qid.strip() or qid in ids:
            issues.append({"level": "error", "target": tag, "message": "题目 id 缺失或重复"})
            continue
        if not isinstance(topic, str) or not topic.strip():
            issues.append({"level": "error", "target": tag, "message": "知识点 topic 不能为空"})
            continue
        if maximum is None or maximum <= 0:
            issues.append({"level": "error", "target": tag, "message": "max_score 必须是正数"})
            continue
        ids.add(qid)
        clean_questions.append({"id": text(qid, 40), "topic": text(topic, 80), "max_score": maximum})
    if not clean_questions:
        issues.append({"level": "error", "target": "questions", "message": "没有可计算的合法题目"})
        return None, issues
    clean_students = []
    seen = set()
    for i, item in enumerate(students):
        tag = f"students[{i}]"
        if not isinstance(item, dict):
            issues.append({"level": "error", "target": tag, "message": "学生必须是对象，已跳过"})
            continue
        sid = item.get("id")
        if not isinstance(sid, str) or not sid.strip() or sid in seen:
            issues.append({"level": "warning", "target": tag, "message": "学生 id 缺失或重复，已跳过"})
            continue
        seen.add(sid)
        answers = item.get("answers")
        if not isinstance(answers, dict):
            issues.append({"level": "warning", "target": sid, "message": "answers 缺失或不是对象，按全部缺答处理"})
            answers = {}
        clean_students.append({"id": text(sid, 40), "name": text(item.get("name", "未命名"), 80), "answers": answers})
    if not clean_students:
        issues.append({"level": "error", "target": "students", "message": "没有可计算的合法学生记录"})
        return None, issues
    return {"course": text(raw.get("course", "未标注课程"), 80), "lesson": text(raw.get("lesson", "未标注课次"), 80), "questions": clean_questions, "students": clean_students}, issues


def classify(rate, evidence, total):
    if evidence < max(1, math.ceil(total / 2)):
        return "insufficient", "证据不足"
    if rate >= 0.8:
        return "strong", "掌握较好"
    if rate >= 0.5:
        return "partial", "部分掌握"
    return "support", "需要支持"


def analyze(raw):
    data, issues = load_data(raw)
    if data is None:
        return {"status": "INVALID_INPUT", "issues": issues, "side_effects": ["不写回成绩", "不发送通知", "不连接 LMS/SIS"]}
    questions = data["questions"]
    valid_ids = {q["id"] for q in questions}
    rows, question_stats = [], {q["id"]: {"question": q, "sum": 0.0, "answered": 0, "correct": 0} for q in questions}
    for student in data["students"]:
        score, maximum, evidence = 0.0, sum(q["max_score"] for q in questions), 0
        answer_rows = {}
        for q in questions:
            value = student["answers"].get(q["id"])
            points = number(value)
            if points is None or points < 0 or points > q["max_score"]:
                if value not in (None, ""):
                    issues.append({"level": "warning", "target": f"{student['id']}.{q['id']}", "message": "分数非法或越界，按缺答处理"})
                answer_rows[q["id"]] = None
                continue
            evidence += 1
            score += points
            stat = question_stats[q["id"]]
            stat["sum"] += points / q["max_score"]
            stat["answered"] += 1
            if points == q["max_score"]:
                stat["correct"] += 1
            answer_rows[q["id"]] = points
        rate = score / maximum if maximum else 0.0
        state, label = classify(rate, evidence, len(questions))
        rows.append({"id": student["id"], "name": student["name"], "score": round(score, 2), "max_score": round(maximum, 2), "score_rate": round(rate, 4), "answered": evidence, "state": state, "state_label": label, "answers": answer_rows})
    topic_buckets = {}
    for stat in question_stats.values():
        q = stat["question"]
        bucket = topic_buckets.setdefault(q["topic"], {"topic": q["topic"], "questions": [], "rate_sum": 0.0, "answered": 0, "correct": 0})
        rate = stat["sum"] / stat["answered"] if stat["answered"] else 0.0
        bucket["questions"].append(q["id"])
        bucket["rate_sum"] += rate
        bucket["answered"] += stat["answered"]
        bucket["correct"] += stat["correct"]
    topics = []
    for bucket in topic_buckets.values():
        rate = bucket["rate_sum"] / len(bucket["questions"])
        state = "reteach" if rate < 0.5 else "reinforce" if rate < 0.8 else "maintain"
        topics.append({"topic": bucket["topic"], "questions": bucket["questions"], "score_rate": round(rate, 4), "answered": bucket["answered"], "correct": bucket["correct"], "priority": state, "priority_label": {"reteach": "优先再教", "reinforce": "巩固练习", "maintain": "保持与迁移"}[state]})
    topics.sort(key=lambda x: (x["score_rate"], x["topic"]))
    groups = {"support": [r["id"] for r in rows if r["state"] == "support"], "partial": [r["id"] for r in rows if r["state"] == "partial"], "strong": [r["id"] for r in rows if r["state"] == "strong"], "insufficient": [r["id"] for r in rows if r["state"] == "insufficient"]}
    return {"status": "needs_review" if issues else "ok", "course": data["course"], "lesson": data["lesson"], "summary": {"students": len(rows), "questions": len(questions), "average_score_rate": round(sum(r["score_rate"] for r in rows) / len(rows), 4), "support": len(groups["support"]), "partial": len(groups["partial"]), "strong": len(groups["strong"]), "insufficient": len(groups["insufficient"]), "warnings": sum(1 for i in issues if i["level"] == "warning"), "errors": sum(1 for i in issues if i["level"] == "error")}, "question_analysis": [{"id": s["question"]["id"], "topic": s["question"]["topic"], "score_rate": round(s["sum"] / s["answered"], 4) if s["answered"] else 0.0, "answered": s["answered"], "correct": s["correct"]} for s in question_stats.values()], "topic_analysis": topics, "students": sorted(rows, key=lambda r: (r["score_rate"], r["id"])), "groups": groups, "next_lesson_plan": [{"group": "support", "student_ids": groups["support"], "action": "教师示范关键步骤，随后完成一题分步练习"}, {"group": "partial", "student_ids": groups["partial"], "action": "同伴解释错因，完成一题变式练习"}, {"group": "strong", "student_ids": groups["strong"], "action": "完成迁移题，可在教师确认后承担小导师角色"}, {"group": "insufficient", "student_ids": groups["insufficient"], "action": "先补采证据，不依据本次结果分层"}], "review_items": ["教师确认知识点命名和阈值是否符合本课目标", "教师确认分组是否适合课堂隐私与心理安全", "连续多次使用前结合教师观察复核趋势"], "issues": issues, "side_effects": ["仅生成形成性教学预览", "不写回成绩", "不发送通知", "不连接 LMS/SIS"]}


def markdown(result):
    esc = lambda v, limit=120: html.escape(text(v, limit))
    s = result.get("summary", {})
    lines = [f"# 课后小测分层报告：{esc(result.get('course'))} / {esc(result.get('lesson'))}", "", f"状态：**{result.get('status')}**；学生 {s.get('students', 0)} 人，题目 {s.get('questions', 0)} 道，班级平均得分率 {s.get('average_score_rate', 0) * 100:.1f}% 。", "", "## 知识点诊断", "| 知识点 | 题目 | 得分率 | 判定 |", "|---|---|---:|---|"]
    for row in result.get("topic_analysis", []):
        lines.append(f"| {esc(row['topic'])} | {esc(', '.join(row['questions']))} | {row['score_rate'] * 100:.1f}% | {esc(row['priority_label'])} |")
    lines += ["", "## 学生分层", "| 学生 | 得分率 | 有效作答 | 分层 |", "|---|---:|---:|---|"]
    for row in result.get("students", []):
        lines.append(f"| {esc(row['name'])}（{esc(row['id'], 40)}） | {row['score_rate'] * 100:.1f}% | {row['answered']} | {esc(row['state_label'])} |")
    lines += ["", "## 下一课预览"]
    for plan in result.get("next_lesson_plan", []):
        lines.append(f"- **{esc(plan['group'])}**（{len(plan['student_ids'])} 人）：{esc(plan['action'])}")
    if result.get("issues"):
        lines += ["", "## 数据问题", "| 级别 | 对象 | 说明 |", "|---|---|---|"]
        for issue in result["issues"]:
            lines.append(f"| {esc(issue['level'])} | {esc(issue['target'])} | {esc(issue['message'])} |")
    lines += ["", "## 人工确认", *[f"- {esc(item)}" for item in result.get("review_items", [])], "", "本报告为离线形成性教学预览，不写回成绩、不发送通知、不连接 LMS/SIS。"]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="离线课后小测分层分析")
    parser.add_argument("--input", help="JSON 文件，- 表示 stdin")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--out-dir", default="output")
    parser.add_argument("--json", action="store_true", dest="json_only")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    if not args.demo and not args.input:
        parser.error("请提供 --input 或 --demo")
    try:
        path = Path(__file__).parents[1] / "examples" / "sample_input.json"
        raw = json.loads(path.read_text(encoding="utf-8")) if args.demo else (json.load(sys.stdin) if args.input == "-" else json.loads(Path(args.input).read_text(encoding="utf-8")))
        result = analyze(raw)
        if args.json_only or args.strict:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.strict and result["status"] != "ok":
            return 2
        if not args.json_only and not args.strict:
            out = Path(args.out_dir)
            out.mkdir(parents=True, exist_ok=True)
            (out / "exit_ticket_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            (out / "exit_ticket_report.md").write_text(markdown(result), encoding="utf-8")
            print(f"已生成 {out / 'exit_ticket_report.json'} 和 {out / 'exit_ticket_report.md'}")
        return 0
    except (OSError, json.JSONDecodeError, TypeError, ValueError, RecursionError, MemoryError) as exc:
        print(f"输入错误：{text(exc)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
