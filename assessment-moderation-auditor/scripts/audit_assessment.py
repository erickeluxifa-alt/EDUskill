#!/usr/bin/env python3
import argparse, html, json, math, os, sys
from pathlib import Path


def clean(value, limit=80):
    return str(value).replace("|", "/").replace("\n", " ")[:limit]


def load_data(path):
    if path == "-":
        return json.load(sys.stdin)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def audit(data, strict=False):
    issues, students = [], []
    rules = data.get("rules", {})
    weights = rules.get("weights", {})
    if not isinstance(weights, dict) or not weights:
        issues.append({"type": "data_error", "message": "缺少有效 weights"})
        return {"course": clean(data.get("course", "未命名课程")), "summary": {}, "students": [], "issues": issues}
    weight_sum = sum(float(v) for v in weights.values() if isinstance(v, (int, float)))
    if abs(weight_sum - 1) > 0.001:
        issues.append({"type": "data_error", "message": f"权重合计为 {weight_sum:.3f}，应为 1.000"})
    seen = set()
    pass_mark = float(rules.get("pass_mark", 60))
    attendance_min = float(rules.get("attendance_min", 70))
    for raw in data.get("students", []):
        sid, name = raw.get("id"), raw.get("name", "未命名")
        row_issues, flags = [], []
        if not sid:
            row_issues.append("缺少学号")
        elif sid in seen:
            row_issues.append("学号重复")
        else:
            seen.add(sid)
        scores = raw.get("scores") or {}
        valid, missing = {}, []
        for component in weights:
            value = scores.get(component)
            if value in (None, ""):
                missing.append(component)
                continue
            try:
                number = float(value)
                if not math.isfinite(number) or number < 0 or number > 100:
                    row_issues.append(f"{component}成绩越界或非有限数字")
                else:
                    valid[component] = number
            except (TypeError, ValueError):
                row_issues.append(f"{component}成绩不是数字")
        total = None
        if missing:
            flags.append("待补齐成绩")
            row_issues.append("缺少评价项: " + ", ".join(missing))
        elif not row_issues or all("成绩" not in x for x in row_issues):
            total = round(sum(valid[k] * float(weights[k]) for k in weights), 2)
        reported = raw.get("reported_total")
        if total is not None and reported not in (None, ""):
            try:
                if abs(total - float(reported)) > 0.5:
                    flags.append("总评与上报值不一致")
                    row_issues.append(f"计算总评 {total:.2f} 与上报值 {float(reported):.2f} 相差超过0.5")
            except (TypeError, ValueError):
                row_issues.append("reported_total 不是数字")
        attendance = raw.get("attendance")
        if attendance in (None, ""):
            flags.append("考勤待核验")
            row_issues.append("缺少考勤")
        else:
            try:
                attendance = float(attendance)
                if not 0 <= attendance <= 100:
                    row_issues.append("考勤不在0-100范围")
                elif attendance < attendance_min:
                    flags.append("考勤低于阈值")
                    row_issues.append(f"考勤 {attendance:.1f}% 低于 {attendance_min:.1f}%")
            except (TypeError, ValueError):
                row_issues.append("考勤不是数字")
        if total is not None and total < pass_mark:
            gap = pass_mark - total
            flags.append("补救候选")
            category = "接近及格" if gap <= 5 else "需重点关注"
            row_issues.append(f"总评 {total:.2f} 低于及格线 {pass_mark:.2f}（{category}）")
        if not valid:
            flags.append("无有效成绩")
        issue_type = "data_error" if any("缺少学号" in x or "重复" in x or "不是数字" in x or "越界" in x for x in row_issues) else "manual_review"
        students.append({"id": clean(sid or ""), "name": clean(name), "total": total, "attendance": attendance, "flags": flags, "issues": row_issues, "issue_type": issue_type})
    counts = {"students": len(students), "complete": sum(s["total"] is not None for s in students), "manual_review": sum(bool(s["issues"]) for s in students), "remediation_candidates": sum("补救候选" in s["flags"] for s in students), "data_errors": len(issues) + sum(s["issue_type"] == "data_error" for s in students)}
    return {"course": clean(data.get("course", "未命名课程")), "rules": {"pass_mark": pass_mark, "attendance_min": attendance_min, "weights": weights}, "summary": counts, "issues": issues, "students": students}


def markdown(result):
    s = result["summary"]
    lines = [f"# 成绩审核报告：{html.escape(result['course'])}", "", f"审核人数：{s.get('students', 0)}；已算总评：{s.get('complete', 0)}；需人工复核：{s.get('manual_review', 0)}；补救候选：{s.get('remediation_candidates', 0)}。", "", "## 问题清单", "| 学号 | 学生 | 总评 | 标记 | 问题 |", "|---|---|---:|---|---|"]
    for st in result["students"]:
        if st["issues"]:
            lines.append(f"| {clean(st['id'])} | {clean(st['name'])} | {st['total'] if st['total'] is not None else '-'} | {clean(', '.join(st['flags']))} | {clean('；'.join(st['issues']))} |")
    if not any(st["issues"] for st in result["students"]): lines.append("| - | - | - | 无 | 未发现规则问题 |")
    lines += ["", "## 人工确认", "- 核对课程成绩政策、补救/补考资格和考勤口径。", "- 确认上报总评与计算总评差异后，再执行教务系统提交。", "- 本报告使用离线输入，不代表正式成绩结论。"]
    return "\n".join(lines) + "\n"


def demo():
    return {"course": "数据库原理（模拟）", "rules": {"pass_mark": 60, "attendance_min": 70, "weights": {"平时": 0.3, "期末": 0.7}}, "students": [{"id": "S001", "name": "示例甲", "scores": {"平时": 78, "期末": 62}, "attendance": 92, "reported_total": 67}, {"id": "S002", "name": "示例乙", "scores": {"平时": 55, "期末": 57}, "attendance": 68}, {"id": "S003", "name": "示例丙", "scores": {"平时": 88}, "attendance": 95}]}


def main():
    ap = argparse.ArgumentParser(description="离线课程成绩审核")
    ap.add_argument("--input", help="JSON 输入文件，- 表示 stdin")
    ap.add_argument("--out-dir", default="output")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--json", action="store_true", dest="json_only")
    args = ap.parse_args()
    if not args.demo and not args.input:
        ap.error("请提供 --input 或 --demo")
    try:
        data = demo() if args.demo else load_data(args.input)
        result = audit(data, args.strict)
        if args.strict and (result["summary"].get("data_errors", 0) or result["issues"]):
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 2
        if args.json_only:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        out = Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)
        (out / "review.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "review.md").write_text(markdown(result), encoding="utf-8")
        print(f"已生成 {out / 'review.json'} 和 {out / 'review.md'}")
        return 0
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"输入错误：{exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
