#!/usr/bin/env python3
"""Offline research milestone risk radar."""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

STATUSES = {"planned", "in_progress", "blocked", "done", "cancelled"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def clean(value, limit=120):
    text = re.sub(r"[\x00-\x1f\x7f|]", " ", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()[:limit]

def load(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取 JSON: {exc}")
    rows = data.get("milestones") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError("JSON 须为数组或包含 milestones 数组")
    return rows

def analyse(rows, as_of, window_days):
    valid, errors = [], []
    ids = set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            errors.append(f"第{index}条不是对象")
            continue
        missing = [key for key in ("id", "project", "milestone", "owner", "due_date", "status") if not row.get(key)]
        if missing:
            errors.append(f"第{index}条缺少: {', '.join(missing)}")
            continue
        item = {key: clean(row.get(key)) for key in ("id", "project", "milestone", "owner", "due_date", "status", "last_update", "evidence")}
        item["blocked_by"] = [clean(x, 60) for x in row.get("blocked_by", [])] if isinstance(row.get("blocked_by", []), list) else []
        if item["status"] not in STATUSES:
            errors.append(f"第{index}条 status 无效: {item['status']}")
            continue
        if not DATE_RE.match(item["due_date"]):
            errors.append(f"第{index}条 due_date 无效: {item['due_date']}")
            continue
        try:
            item["due"] = date.fromisoformat(item["due_date"])
        except ValueError:
            errors.append(f"第{index}条 due_date 不存在: {item['due_date']}")
            continue
        progress = row.get("progress")
        if progress is not None:
            try:
                item["progress"] = max(0.0, min(1.0, float(progress)))
            except (TypeError, ValueError):
                errors.append(f"第{index}条 progress 非数字")
                continue
        else:
            item["progress"] = None
        if item["id"] in ids:
            errors.append(f"第{index}条 id 重复: {item['id']}")
            continue
        ids.add(item["id"])
        valid.append(item)

    by_id = {x["id"]: x for x in valid}
    risks = []
    for item in valid:
        if item["status"] in {"done", "cancelled"}:
            continue
        days = (item["due"] - as_of).days
        reasons, actions = [], []
        dependency_risk = False
        for dep_id in item["blocked_by"]:
            dep = by_id.get(dep_id)
            if not dep or dep["status"] != "done":
                dependency_risk = True
                reasons.append(f"依赖未完成: {dep_id}")
                actions.append("确认依赖节点负责人和解除条件")
                if dep and (dep["due"] - as_of).days < 0:
                    reasons.append(f"依赖已逾期: {dep_id}")
        progress = item["progress"]
        if days < 0:
            reasons.append(f"已逾期 {-days} 天")
            actions.append("本周内确认延期或拆分交付物")
        elif days <= 3 and (progress is None or progress < 0.8):
            reasons.append(f"距截止 {days} 天且进度不足 80%")
            actions.append("核对可交付证据并安排短周期跟进")
        elif days <= 7 and (progress is None or progress < 0.6):
            reasons.append(f"距截止 {days} 天且进度不足 60%")
            actions.append("确认剩余工作量与资源需求")
        elif days <= 14 and progress is not None and progress < 0.3:
            reasons.append(f"距截止 {days} 天且进度低于 30%")
            actions.append("拆分任务并重新估算节点日期")
        if dependency_risk and not actions:
            actions.append("协调依赖并更新阻塞记录")
        if not reasons:
            continue
        level = "high" if days < 0 or (days <= 3 and (progress is None or progress < 0.8)) else "medium"
        if dependency_risk and any("已逾期" in r for r in reasons):
            level = "high"
        if progress is None:
            reasons.append("未提供进度，判断存在不确定性")
            actions.append("补充最近进展、证据链接或预计完成日")
        risks.append({"id": item["id"], "project": item["project"], "milestone": item["milestone"], "owner": item["owner"], "due_date": item["due_date"], "status": item["status"], "progress": item["progress"], "level": level, "reasons": reasons, "actions": list(dict.fromkeys(actions))})

    congestion = []
    project_groups = defaultdict(list)
    owner_groups = defaultdict(list)
    for item in valid:
        if item["status"] in {"done", "cancelled"}:
            continue
        if 0 <= (item["due"] - as_of).days <= window_days:
            project_groups[item["project"]].append(item["id"])
        owner_groups[item["owner"]].append(item["id"])
    for project, ids_for_project in project_groups.items():
        if len(ids_for_project) >= 3:
            congestion.append({"dimension": "project", "name": project, "count": len(ids_for_project), "milestone_ids": ids_for_project, "message": f"未来 {window_days} 天项目节点集中"})
    for owner, owner_ids in owner_groups.items():
        if len(owner_ids) >= 4:
            congestion.append({"dimension": "owner", "name": owner, "count": len(owner_ids), "milestone_ids": owner_ids, "message": "未完成节点负荷集中"})
    return valid, errors, risks, congestion

def build_report(rows, input_count, errors, risks, congestion, as_of, window_days):
    counts = Counter(r["level"] for r in risks)
    return {"as_of": as_of.isoformat(), "window_days": window_days, "validation": {"input": input_count, "valid": len(rows), "errors": errors}, "summary": {"risk_count": len(risks), "high": counts["high"], "medium": counts["medium"], "by_project": dict(Counter(r["project"] for r in risks)), "by_owner": dict(Counter(r["owner"] for r in risks))}, "risks": sorted(risks, key=lambda r: (0 if r["level"] == "high" else 1, r["due_date"], r["owner"])), "congestion": congestion}

def main():
    parser = argparse.ArgumentParser(description="科研节点风险雷达")
    parser.add_argument("input")
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    if args.window_days < 1 or args.window_days > 60:
        parser.error("--window-days 必须在 1-60 之间")
    try:
        as_of = date.fromisoformat(args.as_of)
        raw = load(args.input)
        valid, errors, risks, congestion = analyse(raw, as_of, args.window_days)
        report = build_report(valid, len(raw), errors, risks, congestion, as_of, args.window_days)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        if args.preview:
            report["preview"] = {"requires_confirmation": True, "actions": [{"milestone_id": r["id"], "owner": r["owner"], "action": r["actions"][0]} for r in report["risks"]]}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print(f"科研节点风险雷达 | 分析日 {report['as_of']} | 有效节点 {len(valid)}")
    print(f"风险节点：高 {report['summary']['high']} / 中 {report['summary']['medium']}；输入问题 {len(errors)}")
    for risk in report["risks"]:
        print(f"[{risk['level'].upper()}] {risk['project']} / {risk['milestone']} / {risk['owner']} / 截止 {risk['due_date']}")
        print("  原因：" + "；".join(risk["reasons"]))
        print("  建议：" + "；".join(risk["actions"]))
    for item in congestion:
        print(f"[拥堵] {item['name']}：{item['message']}（{item['count']} 个节点）")
    if errors:
        print("数据问题：" + "；".join(errors))
    if args.preview:
        print("预览提示：以上建议仅供人工确认，未执行发送、写回或日期修改。")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
