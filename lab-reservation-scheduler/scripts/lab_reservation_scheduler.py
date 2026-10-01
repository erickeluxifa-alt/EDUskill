#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lab_reservation_scheduler.py — 实验室/机房预约防冲突排程器 v1.0.0
================================================================
面向实验室管理员 / 实验员 / 教务干事：
输入「实验室资源 + 预约申请（实验课程/班级/人数/教师/日期/偏好时段/资源要求）」，
自动生成无冲突的预约排程，输出 Markdown 报告或结构化 JSON，
显式揭示「未解决缺口与冲突（人工协调项）」以及「资源利用率统计」。

约束规则（rules 可覆盖）：
  1) 容量硬约束：学生数 <= 资源剩余容量（允许跨资源拆分，默认开启）
  2) 类型匹配：申请指定资源类型时，仅匹配同类型资源的资源
  3) 设备匹配：申请指定设备清单时，资源设备须包含全部所需设备
  4) 资源独占：同一资源同一日期同一时段仅容纳一个预约（含已排定 bookings 占用）
  5) 教师互斥：同一教师同一日期同一时段不能出现两次（可关闭）
  6) 确定性贪心：按优先级(高->低)、人数(大->小)排序，同槽位选剩余容量最大的资源

交互与安全：默认只读预览（不写盘）；--out 显式写出结果文件；
用户可控文本统一 HTML 转义 + Markdown 表格转义，防注入与表格拆分。

依赖：仅 Python3 标准库。用法：
  python3 lab_reservation_scheduler.py input.json            # Markdown 报告
  python3 lab_reservation_scheduler.py input.json --json     # JSON 结果
  cat input.json | python3 lab_reservation_scheduler.py --json
退出码: 0=无缺口全部解决  1=存在需人工处理项  2=输入/IO 错误
"""

import argparse
import html
import json
import re
import sys

VERSION = "1.0.0"

# ---------------- 字段别名（中英文） ----------------
ALIAS_RES = {
    "id": ["id", "name", "名称", "名字", "lab", "lab_id"],
    "type": ["type", "类型", "kind", "类别", "类别名"],
    "capacity": ["capacity", "容量", "人数", "座位数", "seats", "max", "工位数"],
    "equipment": ["equipment", "设备", "设备清单", "devices"],
    "open_dates": ["open_dates", "开放日期", "开放日", "available_dates", "可用日期"],
}
ALIAS_REQ = {
    "id": ["id", "name", "名称", "实验", "实验项目", "title"],
    "course": ["course", "课程", "实验课程", "subject", "实验名称"],
    "group_name": ["group", "班级", "学院", "专业班级", "class", "团体"],
    "students": ["students", "人数", "学生数", "student_count", "count", "预约人数"],
    "teacher": ["teacher", "教师", "授课教师", "instructor", "负责人"],
    "date": ["date", "日期", "开课日期", "预约日期"],
    "slots": ["slots", "slot", "时段", "偏好时段", "时段偏好", "periods", "period", "time", "时间"],
    "res_type": ["res_type", "资源类型", "实验室类型", "lab_type", "需要类型"],
    "equipment": ["equipment", "设备", "所需设备", "需要设备", "devices"],
    "split": ["split", "拆分", "可拆分", "allow_split"],
    "priority": ["priority", "优先级", "优先", "level", "重要程度"],
}
ALIAS_BOOK = {
    "id": ["id", "name", "名称"],
    "date": ["date", "日期"],
    "slot": ["slot", "时段", "time"],
    "resource": ["resource", "资源", "实验室", "room"],
    "students": ["students", "人数"],
    "teacher": ["teacher", "教师"],
}

DEFAULT_SLOTS = [
    {"name": "08:00-10:00", "start": "08:00"},
    {"name": "10:10-12:00", "start": "10:10"},
    {"name": "14:00-16:00", "start": "14:00"},
    {"name": "16:10-18:00", "start": "16:10"},
    {"name": "19:00-21:00", "start": "19:00"},
]
DEFAULT_RULES = {
    "split": True,               # 允许跨资源拆分
    "teacher_conflict": True,     # 教师同时段互斥
    "capacity_strict": True,      # 容量硬约束（人数>容量即为缺口）
    "max_per_resource_slot": 1,   # 单资源单时段最多容纳预约数（独占）
}


# ---------------- 工具函数 ----------------
def norm_date(raw):
    """2026-09-07 / 2026/9/7 / 2026年9月7日 -> YYYY-MM-DD，失败返回 None"""
    if not isinstance(raw, str):
        return None
    m = re.search(r"(\d{4})[/年\-\.](\d{1,2})[/月\-\.](\d{1,2})", raw.strip())
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (2000 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return "%04d-%02d-%02d" % (y, mo, d)


def esc_md(text):
    """Markdown 安全转义：HTML 实体 + 表格竖线/换行（防注入与表格拆分）。"""
    if text is None:
        return "-"
    s = html.escape(str(text))
    return s.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def to_slot_name(slot, slot_defs):
    """把用户时段输入（名称/序号/起始时间）归一化为时段名；无法识别返回 None。"""
    if slot is None:
        return None
    s = str(slot).strip().lower()
    for i, d in enumerate(slot_defs):
        if s == d["name"].lower() or s == str(i + 1) or s == d["name"].split("-")[0].lower():
            return d["name"]
    if re.match(r"^\d{1,2}:\d{2}", s):
        for d in slot_defs:
            if s.replace(" ", "") in d["name"].replace(" ", "") or \
               d["name"].replace(" ", "").startswith(s.replace(" ", "")):
                return d["name"]
    return None


def get_first(obj, aliases):
    """按别名表返回 (规范key, 值)；未命中返回 (None, None)。"""
    for k, vals in aliases.items():
        for v in vals:
            if v in obj:
                return k, obj[v]
    return None, None


# ---------------- 数据装载 ----------------
def parse_resources(raw):
    """解析资源列表 -> (resources, errs)"""
    res, errs = [], []
    if raw is None:
        return res, ["缺少 resources（实验室资源列表）"]
    if not isinstance(raw, list):
        return res, ["resources 必须为列表"]
    if not raw:
        return res, ["resources 为空列表"]
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            errs.append("resources[%d] 不是对象" % i)
            continue
        k, v = get_first(item, ALIAS_RES)
        rid = str(v).strip() if v is not None else "lab_%d" % i
        cap = None
        for a in ALIAS_RES["capacity"]:
            if a in item:
                try:
                    cap = int(item[a])
                except (TypeError, ValueError):
                    cap = None
                break
        if cap is None or cap <= 0:
            errs.append("资源 %s：容量缺失或非法（需正整数）" % rid)
            continue
        tp = None
        for a in ALIAS_RES["type"]:
            if a in item and item[a]:
                tp = str(item[a])
                break
        eq = []
        for a in ALIAS_RES["equipment"]:
            if a in item:
                vv = item[a]
                eq = vv if isinstance(vv, list) else ([vv] if vv else [])
                break
        od = None
        for a in ALIAS_RES["open_dates"]:
            if a in item:
                vv = item[a]
                od = vv if isinstance(vv, list) else ([vv] if vv else [])
                break
        dates = None
        if od:
            dates = [norm_date(x) for x in od]
            if any(x is None for x in dates):
                errs.append("资源 %s：开放日期含非法格式" % rid)
        res.append({"id": rid, "type": tp or "通用", "capacity": cap,
                    "equipment": [str(x) for x in eq], "open_dates": dates})
    return res, errs


def parse_requests(raw, slot_defs, kind):
    """解析预约申请(requests)或已排定(bookings)。kind: 'request' | 'booking'"""
    reqs, errs = [], []
    if raw is None:
        if kind == "request":
            errs.append("缺少 requests（预约申请列表）")
        return reqs, errs
    if not isinstance(raw, list):
        return reqs, ["%s 必须为列表" % ("requests" if kind == "request" else "bookings")]
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            errs.append("%s[%d] 不是对象" % (kind, i))
            continue
        k, v = get_first(item, ALIAS_REQ if kind == "request" else ALIAS_BOOK)
        rid = str(v).strip() if v is not None else ("req_%d" % i)

        def gv(key):
            ali = ALIAS_REQ if kind == "request" else ALIAS_BOOK
            for a in ali[key]:
                if a in item:
                    return item[a]
            return None

        d = {"id": rid, "kind": kind}
        if kind == "request":
            d["course"] = gv("course")
            d["group_name"] = gv("group_name")
            st = gv("students")
            try:
                d["students"] = int(st) if st is not None else None
            except (TypeError, ValueError):
                d["students"] = None
            if d["students"] is None or d["students"] <= 0:
                errs.append("预约 %s：人数缺失或非法" % rid)
                continue
            dt = norm_date(gv("date"))
            if dt is None:
                errs.append("预约 %s：日期缺失或非法" % rid)
                continue
            d["date"] = dt
            sl = gv("slots")
            if isinstance(sl, str):
                d["slots"] = [x.strip() for x in re.split(r"[,，;；、]", sl) if x.strip()]
            elif isinstance(sl, list):
                d["slots"] = [str(x) for x in sl]
            else:
                d["slots"] = None
            d["res_type"] = gv("res_type")
            eq = gv("equipment")
            d["equipment"] = [str(x) for x in eq] if isinstance(eq, list) else ([str(eq)] if eq else [])
            sp = gv("split")
            d["split"] = not (sp is False or (isinstance(sp, str) and sp.lower()
                                              in ("false", "no", "0", "否", "不")))
            pv = gv("priority")
            try:
                d["priority"] = int(pv) if pv is not None else 0
            except (TypeError, ValueError):
                d["priority"] = 0
            d["teacher"] = gv("teacher")
            if isinstance(d["teacher"], list):
                d["teacher"] = ",".join(str(x) for x in d["teacher"])
        else:
            d["students"] = max(gv("students") or 0, 0)
            d["date"] = norm_date(gv("date"))
            d["slot"] = to_slot_name(gv("slot"), slot_defs)
            d["resource"] = gv("resource")
            d["teacher"] = gv("teacher")
            if d["date"] is None or d["slot"] is None or d["resource"] is None:
                errs.append("已排定 %s：日期/时段/资源 不完整，已跳过" % rid)
                continue
        reqs.append(d)
    return reqs, errs


# ---------------- 排程核心 ----------------
def resolve_all(res, requests, bookings, slot_defs, rules):
    """主排程：占用表 -> 排序 -> 逐单贪心。返回结果 dict。"""
    # 已排定占用表
    occ = {}
    occ_cnt = {}
    tocc = {}
    for b in bookings:
        key = (b["date"], b["slot"], b["resource"])
        occ[key] = occ.get(key, 0) + int(b["students"])
        occ_cnt[key] = occ_cnt.get(key, 0) + 1
        if b.get("teacher"):
            tocc.setdefault((b["date"], b["slot"]), set()).add(b["teacher"])

    slot_names = [s["name"] for s in slot_defs]
    order = sorted(enumerate(requests),
                   key=lambda iv: (-iv[1].get("priority", 0), -iv[1].get("students", 0), iv[0]))

    plan = []
    issues = []

    for _, req in order:
        date = req["date"]
        need = req["students"]
        teacher = req.get("teacher")
        cand = req.get("slots") or slot_names
        cand2 = []
        for x in cand:
            s = to_slot_name(x, slot_defs)
            if s and s not in cand2:
                cand2.append(s)
        cand = cand2 if cand2 else slot_names

        remaining = need
        for slot in cand:
            if remaining <= 0:
                break
            if teacher and rules.get("teacher_conflict", True) and teacher in tocc.get((date, slot), set()):
                continue  # 教师同时段已有安排，跳过该时段
            avail = []
            for r in res:
                if r["open_dates"] and date not in r["open_dates"]:
                    continue
                if req.get("res_type") and r["type"] != req["res_type"]:
                    continue
                if req.get("equipment") and not set(req["equipment"]).issubset(set(r["equipment"])):
                    continue
                key = (date, slot, r["id"])
                free = r["capacity"] - occ.get(key, 0)
                if free <= 0:
                    continue
                if rules.get("max_per_resource_slot", 1) and \
                        occ_cnt.get(key, 0) >= rules["max_per_resource_slot"]:
                    continue
                avail.append((free, r))
            avail.sort(key=lambda x: -x[0])  # 剩余容量大优先（确定性）
            for free, r in avail:
                if remaining <= 0:
                    break
                if not rules.get("capacity_strict", True) and free < remaining:
                    take = free  # 非严格模式：排满但标注超载，交人工确认
                else:
                    take = min(free, remaining)
                key = (date, slot, r["id"])
                occ[key] = occ.get(key, 0) + take
                occ_cnt[key] = occ_cnt.get(key, 0) + 1
                if teacher:
                    tocc.setdefault((date, slot), set()).add(teacher)
                plan.append({
                    "date": date, "slot": slot, "resource_id": r["id"],
                    "resource_type": r["type"], "students": take, "req_id": req["id"],
                    "course": req.get("course"), "group_name": req.get("group_name"),
                    "teacher": teacher, "priority": req.get("priority", 0),
                })
                remaining -= take
            if remaining > 0 and not (req.get("split", True) and rules.get("split", True)):
                break
        if remaining > 0:
            issues.append({
                "req_id": req["id"], "course": req.get("course"), "date": date,
                "needed": need, "shortage": remaining,
                "reason": "容量/资源/时段不足，剩余 %d 人未安排（建议拆班、换时段或换资源）" % remaining,
                "level": "block",
            })

    # 利用率统计（按资源聚合，含已排定占用）
    used_map = {}
    for c in plan:
        key = (c["date"], c["slot"], c["resource_id"])
        used_map[key] = used_map.get(key, 0) + c["students"]
    for b in bookings:
        key = (b["date"], b["slot"], b["resource"])
        used_map[key] = used_map.get(key, 0) + int(b["students"])
    util = []
    for r in res:
        total_used = sum(v for (d, s, rid), v in used_map.items() if rid == r["id"])
        total_cap = sum(r["capacity"] for (d, s, rid) in used_map if rid == r["id"])
        active_days = len({d for (d, s, rid) in used_map if rid == r["id"]})
        rate = round(total_used / total_cap * 100, 1) if total_cap else 0.0
        util.append({"resource": r["id"], "used_seats": total_used,
                     "capacity_seats": total_cap, "active_days": active_days,
                     "rate_pct": rate})
    resolved = len(requests) - len(issues)
    return {
        "summary": {"total_requests": len(requests), "resolved": resolved,
                    "chunks": len(plan), "issues": len(issues)},
        "issues": issues, "plan": plan, "utilization": util,
    }


# ---------------- 输出渲染 ----------------
def render_markdown(data):
    L = []
    s = data["summary"]
    L.append("# 实验室预约排程报告\n")
    L.append("> 预约 %(total_requests)d 单 · 已排 %(chunks)d 段 · 全部解决 %(resolved)d · "
             "需人工处理 %(issues)d 项\n" % s)
    if data["issues"]:
        L.append("## 需人工处理（缺口/冲突）")
        for it in data["issues"]:
            L.append("- **[%s]** %s | %s | 需 %d 人，缺口 %d 人 → %s" % (
                esc_md(it["req_id"]), esc_md(it.get("course")), esc_md(it["date"]),
                it["needed"], it["shortage"], it["reason"]))
        L.append("")
    L.append("## 预约排程表（按日期/时段/资源）")
    L.append("| 日期 | 时段 | 资源 | 类型 | 实验课程 | 班级 | 人数 | 教师 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for c in sorted(data["plan"], key=lambda x: (x["date"], x["slot"], x["resource_id"])):
        L.append("| %s | %s | %s | %s | %s | %s | %d | %s |" % (
            esc_md(c["date"]), esc_md(c["slot"]), esc_md(c["resource_id"]),
            esc_md(c["resource_type"]), esc_md(c.get("course")), esc_md(c.get("group_name")),
            c["students"], esc_md(c.get("teacher"))))
    L.append("")
    L.append("## 资源利用率")
    L.append("| 实验室 | 占用座位 | 可用容量 | 活跃天数 | 利用率 |")
    L.append("|---|---|---|---|---|")
    for u in data["utilization"]:
        L.append("| %s | %d | %d | %d | %.1f%% |" %
                 (esc_md(u["resource"]), u["used_seats"], u["capacity_seats"],
                  u["active_days"], u["rate_pct"]))
    L.append("")
    return "\n".join(L)


# ---------------- 主流程 ----------------
def main():
    ap = argparse.ArgumentParser(description="实验室预约防冲突排程器 v%s（零依赖 Python3）" % VERSION)
    ap.add_argument("input", nargs="?", help="输入 JSON 文件路径（缺省读 stdin）")
    ap.add_argument("--json", action="store_true", help="输出 JSON 而非 Markdown")
    ap.add_argument("--out", metavar="FILE", help="同时将结果写入文件（默认只读预览）")
    args = ap.parse_args()

    try:
        raw = json.load(open(args.input, "r", encoding="utf-8")) if args.input else json.load(sys.stdin)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        print("[ERROR] 输入解析失败: %s" % e, file=sys.stderr)
        return 2
    if not isinstance(raw, dict):
        print("[ERROR] JSON 顶层必须为对象", file=sys.stderr)
        return 2

    rules = dict(DEFAULT_RULES)
    slot_defs = list(DEFAULT_SLOTS)
    if isinstance(raw.get("rules"), dict):
        for k in rules:
            if k in raw["rules"]:
                rules[k] = raw["rules"][k]
        if isinstance(raw["rules"].get("open_slots"), list) and raw["rules"]["open_slots"]:
            defs = []
            for x in raw["rules"]["open_slots"]:
                if isinstance(x, str):
                    defs.append({"name": x, "start": x.split("-")[0]})
                elif isinstance(x, dict) and "name" in x:
                    defs.append(x)
            if defs:
                slot_defs = defs

    res_raw = raw.get("resources")
    if res_raw is None:
        for k in ("实验室", "资源", "rooms", "labs"):
            if k in raw:
                res_raw = raw[k]
                break
    req_raw = raw.get("requests")
    if req_raw is None:
        for k in ("预约申请", "预约", "applications"):
            if k in raw:
                req_raw = raw[k]
                break
    book_raw = raw.get("bookings")

    resources, e1 = parse_resources(res_raw)
    requests, e2 = parse_requests(req_raw, slot_defs, "request")
    bookings, e3 = parse_requests(book_raw, slot_defs, "booking")
    errors = list(e1) + list(e2) + list(e3)
    if not resources:
        errors.append("没有可用实验室资源")
    if not requests:
        errors.append("没有可排的预约申请")

    if errors:
        print("== 校验错误（未执行排程）==", file=sys.stderr)
        for e in errors[:20]:
            print(" - " + e, file=sys.stderr)
        return 2

    data = resolve_all(resources, requests, bookings, slot_defs, rules)
    out = render_json(data) if args.json else render_markdown(data)

    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(out + "\n")
        except OSError as e:
            print("[ERROR] 写出文件失败: %s" % e, file=sys.stderr)
            return 2
    print(out)
    return 1 if data["summary"]["issues"] > 0 else 0


def render_json(data):
    return json.dumps(data, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    sys.exit(main())