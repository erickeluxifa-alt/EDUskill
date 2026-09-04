#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
exam_scheduler.py - 考场编排与监考调度生成器 (v1.0.0, 零依赖)

场景：教务处/院系教学秘书在期末/期中考前输入考试场次、考场容量、
监考教师信息，自动生成考场编排表 + 监考调度表，并给出缺口告警。

输入(JSON)：
{
  "exams": [
    {"course": "高等数学A", "date": "2026-06-29", "slot": "上午",
     "classes": [{"name": "计算机2401", "count": 42}]}
  ],
  "rooms": [{"id": "教1-101", "capacity": 90}],
  "invigilators": [
    {"name": "张明", "teach_classes": ["计算机2401"], "max_per_day": 2,
     "unavailable": [{"date": "2026-06-30", "slot": "上午"}]}
  ],
  "rules": {"avoid_own_class": true, "min_invigilators_per_room": 1}
}

输出: Markdown 报告（缺口/编排表/监考日程/汇总）或 --json 结构化结果。

安全: 用户文本 HTML 转义 + 长度截断（防 XSS）；纯内存计算、无网络；
仅 --out 显式指定时才写文件；错误与缺口明示，不静默编造。
"""
import sys
import json
import html
import argparse
from collections import defaultdict

MAX_LEN = 60

# ---------------- 工具 ----------------
def esc(s, maxlen=MAX_LEN):
    if s is None:
        return ""
    s = str(s)
    if len(s) > maxlen:
        s = s[:maxlen] + "…"
    return html.escape(s, quote=True)


def is_int(v):
    try:
        int(v)
        return True
    except (TypeError, ValueError):
        return False


def norm_date(d):
    """归一化为 YYYY-MM-DD；支持 2026-06-08 / 2026/6/8 / 2026年6月8日。"""
    if d is None:
        return None
    d = str(d).strip()
    for sep in ("-", "/", "."):
        if sep in d:
            parts = [p.strip() for p in d.split(sep)]
            if len(parts) == 3 and all(p.isdigit() for p in parts):
                y, m, day = (int(x) for x in parts)
                if 1 <= m <= 12 and 1 <= day <= 31:
                    return "%04d-%02d-%02d" % (y, m, day)
            return None
    if "年" in d and "月" in d:
        try:
            y = int(d.split("年")[0].strip())
            m = int(d.split("年")[1].split("月")[0].strip())
            rest = d.split("月")[1].replace("日", "").strip()
            day = int(rest) if rest else 1
            return "%04d-%02d-%02d" % (y, m, day)
        except Exception:
            return None
    return None


class Report:
    def __init__(self):
        self.issues = []          # [(severity, msg)]
        self.plan = []            # [exam_plan]
        self.teacher_sched = []   # [{name,date,slot,room}]
        self.stats = {"exams": 0, "seats": 0, "capacity": 0,
                      "rooms": 0, "teachers": 0}

    def add(self, sev, msg):
        self.issues.append((sev, msg))

    def has(self, *sevs):
        return any(s in sevs for s, _ in self.issues)


# ---------------- 解析 ----------------

def parse_top(data):
    """顶层解包（兼容中英文别名），返回 (exams, rooms, teachers, rules, issues)。"""
    iss = []
    if not isinstance(data, dict):
        return [], [], [], {}, [("fatal", "JSON 根节点必须为对象")]
    exams = data.get("exams") or data.get("exam_slots") or data.get("考试") or []
    rooms = data.get("rooms") or data.get("classrooms") or data.get("考场") or []
    teachers = data.get("invigilators") or data.get("teachers") or data.get("监考教师") or []
    rules = data.get("rules") or {}
    if not isinstance(exams, list):
        iss.append(("fatal", "'exams' 必须为数组")); exams = []
    if not isinstance(rooms, list):
        iss.append(("fatal", "'rooms' 必须为数组")); rooms = []
    if not isinstance(teachers, list):
        iss.append(("fatal", "'invigilators' 必须为数组")); teachers = []
    if not isinstance(rules, dict):
        iss.append(("warn", "'rules' 应为对象，已忽略")); rules = {}
    return exams, rooms, teachers, rules, iss


def parse_rules(rules):
    spi = _r_int(rules, "students_per_invigilator", 50)
    return {
        "min_invigilators_per_room": max(1, _r_int(rules, "min_invigilators_per_room", 1)),
        "students_per_invigilator": spi,
        # 每 N 名学生加 1 名监考；未显式配置时默认与 students_per_invigilator 一致
        "extra_invigilator_after": max(0, _r_int(rules, "extra_invigilator_after", spi)),
        "max_invigilators_per_room": max(1, _r_int(rules, "max_invigilators_per_room", 4)),
        "default_max_per_day": max(1, _r_int(rules, "default_max_per_day", 2)),
        "avoid_own_class": bool(rules.get("avoid_own_class", True)),
    }


def _r_int(rules, k, d):
    v = rules.get(k)
    return int(v) if is_int(v) else d


def parse_exams(exams, rep):
    out = []
    for i, e in enumerate(exams):
        if not isinstance(e, dict):
            rep.add("warn", "第 %d 个考试条目不是对象，已跳过" % (i + 1))
            continue
        course = e.get("course") or e.get("科目") or e.get("name")
        if not course:
            rep.add("error", "第 %d 个考试条目缺少 course，已跳过" % (i + 1))
            continue
        date = norm_date(e.get("date") or e.get("日期"))
        if not date:
            rep.add("error", "考试《%s》日期无效（需 YYYY-MM-DD 或 2026年6月8日形态）" % esc(course))
            continue
        slot = str(e.get("slot") or e.get("time_slot") or e.get("时段") or "上午")
        cls_raw = e.get("classes") or e.get("班级") or []
        classes = []
        if isinstance(cls_raw, list):
            for c in cls_raw:
                if isinstance(c, dict):
                    cn, cnt = c.get("name") or c.get("class") or c.get("班级"), \
                        c.get("count") or c.get("人数")
                else:
                    cn, cnt = c, None
                if not cn:
                    rep.add("warn", "考试《%s》存在无名字的班级条目，已跳过" % esc(course))
                    continue
                if not is_int(cnt) or int(cnt) <= 0:
                    rep.add("warn", "考试《%s》班级《%s》人数无效，按 1 人处理" % (esc(course), esc(cn)))
                    cnt = 1
                classes.append([esc(cn), int(cnt)])
        total = sum(c[1] for c in classes)
        if total <= 0:
            rep.add("warn", "考试《%s》无有效人数，已跳过" % esc(course))
            continue
        out.append({"course": esc(course), "date": date, "slot": slot,
                    "classes": classes, "total": total})
    seen = set()
    for e in out:
        k = (e["course"], e["date"], e["slot"])
        if k in seen:
            rep.add("warn", "《%s》在 %s %s 重复出现，请核对是否为真实多场" % (e["course"], e["date"], e["slot"]))
        seen.add(k)
    return out


def parse_rooms(rooms, rep):
    out = []
    for i, r in enumerate(rooms):
        if not isinstance(r, dict):
            rep.add("warn", "第 %d 个考场条目不是对象，已跳过" % (i + 1))
            continue
        rid = r.get("id") or r.get("room") or r.get("name") or r.get("教室")
        if not rid:
            rep.add("error", "第 %d 个考场缺少 id，已跳过" % (i + 1))
            continue
        cap = r.get("capacity") or r.get("cap") or r.get("容量")
        if not is_int(cap) or int(cap) <= 0:
            rep.add("error", "考场《%s》容量无效，已跳过" % esc(rid))
            continue
        out.append({"id": esc(rid), "capacity": int(cap)})
    return out


def parse_teachers(teachers, rep, default_max_per_day=2):
    out, seen = [], {}
    for i, t in enumerate(teachers):
        if not isinstance(t, dict):
            rep.add("warn", "第 %d 个监考条目不是对象，已跳过" % (i + 1))
            continue
        name = t.get("name") or t.get("姓名") or t.get("teacher")
        if not name:
            rep.add("error", "第 %d 个监考条目缺少姓名，已跳过" % (i + 1))
            continue
        name = esc(name)
        cls_raw = t.get("teach_classes") or t.get("teach_class") or t.get("任课班级") or []
        if isinstance(cls_raw, str):
            cls_raw = [cls_raw]
        teach = {esc(str(c)) for c in cls_raw if str(c).strip()}
        mpd = t.get("max_per_day")
        mpd = int(mpd) if is_int(mpd) and int(mpd) > 0 else default_max_per_day
        off = []
        for o in (t.get("unavailable") or t.get("off") or []):
            if isinstance(o, dict):
                od = norm_date(o.get("date") or o.get("日期"))
                osl = o.get("slot") or o.get("time_slot") or o.get("时段")
                if od:
                    off.append((od, str(osl) if osl else "*"))
        if name in seen:
            rep.add("warn", "监考教师《%s》重复出现，约束已合并" % name)
            seen[name]["teach"] |= teach
            seen[name]["off"] += off
            continue
        seen[name] = {"name": name, "teach": teach, "max_per_day": mpd,
                      "off": off, "assigned": []}  # assigned: [(date, slot, room)]
        out.append(seen[name])
    return out


# ---------------- 编排核心 ----------------

def needed_invigilators(seat, rules):
    n = rules["min_invigilators_per_room"]
    if rules["extra_invigilator_after"] > 0:
        n += seat // rules["extra_invigilator_after"]
    return min(n, rules["max_invigilators_per_room"])


def teacher_free(t, date, slot, class_names, rules):
    for od, osl in t["off"]:
        if od == date and (osl == "*" or osl == slot):
            return False
    if t["max_per_day"] is not None:
        today = sum(1 for a in t["assigned"] if a[0] == date)
        if today >= t["max_per_day"]:
            return False
    for a in t["assigned"]:
        if a[0] == date and a[1] == slot:
            return False
    if rules.get("avoid_own_class", True) and any(cn in t["teach"] for cn in class_names):
        return False
    return True


def pick_teachers(tlist, date, slot, room_id, class_names, need, rep):
    """贪心选监考：当日已排少者优先，姓名稳序。返回 (names, missing)。"""
    cand = [t for t in tlist if teacher_free(t, date, slot, class_names, rules_now)]
    cand.sort(key=lambda t: (sum(1 for a in t["assigned"] if a[0] == date), t["name"]))
    names = []
    for t in cand:
        if len(names) >= need:
            break
        t["assigned"].append((date, slot, room_id))
        names.append(t["name"])
    missing = need - len(names)
    if missing > 0:
        rep.add("fix", "考场《%s》%s %s 缺 %d 名监考教师，请人工协调" %
                (room_id, date, slot, missing))
    return names, missing


def build_exam_plan(exams, rooms, teachers, rules, rep):
    """贪心装座（大教室优先）+ 每考场配监考。"""
    rooms_sorted = sorted(rooms, key=lambda r: -r["capacity"])
    plan, total_seats = [], 0
    for ex in exams:
        remaining = [list(c) for c in ex["classes"]]
        need = ex["total"]
        room_plans = []
        for r in rooms_sorted:
            if need <= 0:
                break
            take = min(r["capacity"], need)
            used, left = [], take
            while left > 0 and remaining:
                cn, cnt = remaining[0]
                use = min(cnt, left)
                used.append([cn, use])
                remaining[0][1] -= use
                if remaining[0][1] <= 0:
                    remaining.pop(0)
                left -= use
            need -= take
            total_seats += take
            n_need = needed_invigilators(take, rules)
            inv, miss = pick_teachers(teachers, ex["date"], ex["slot"], r["id"],
                                      [c[0] for c in used], n_need, rep)
            room_plans.append({"room": r["id"], "seat": take, "classes": used,
                               "invigilators": inv, "missing": miss})
        if need > 0:
            rep.add("error", "考试《%s》%s %s 缺 %d 个考位（教室容量不足），请增补考场" %
                    (ex["course"], ex["date"], ex["slot"], need))
        plan.append({"course": ex["course"], "date": ex["date"], "slot": ex["slot"],
                     "rooms": room_plans})
    rep.plan = plan
    rep.stats["exams"] = len(plan)
    rep.stats["seats"] = total_seats
    return plan


def build_teacher_sched(teachers):
    rows = []
    for t in teachers:
        for date, slot, room in t["assigned"]:
            rows.append({"name": t["name"], "date": date, "slot": slot, "room": room})
    rows.sort(key=lambda r: (r["date"], r["slot"], r["name"]))
    return rows


# ---------------- 渲染 ----------------

def render_markdown(rep, rules):
    L = []
    L.append("# 考场编排与监考调度报告")
    L.append("")
    L.append("## 一、输入与规则")
    L.append("- 考试场次 %d · 考场 %d 个 · 监考教师 %d 人" % (
        rep.stats["exams"], rep.stats["rooms"], rep.stats["teachers"]))
    L.append("- 监考规则：每考场 ≥%d 人，每 %d 名学生加 1 人（封顶 %d）；单日默认上限 %d 场；%s" % (
        rules["min_invigilators_per_room"], rules["students_per_invigilator"],
        rules["max_invigilators_per_room"], rules["default_max_per_day"],
        "回避任课班级" if rules["avoid_own_class"] else "不回避任课班级"))
    L.append("")
    errs = [m for s, m in rep.issues if s in ("error", "fix")]
    warns = [m for s, m in rep.issues if s == "warn"]
    L.append("## 二、缺口与异常（%d 项）" % len(errs))
    if errs:
        for m in errs:
            L.append("- ⚠ %s" % m)
    else:
        L.append("- 无缺口，全部场次可完整编排 ✅")
    L.append("")
    if warns:
        L.append("## 二补、提示（%d 项）" % len(warns))
        for m in warns:
            L.append("- · %s" % m)
        L.append("")
    L.append("## 三、考场编排表")
    if not rep.plan:
        L.append("- （无编排结果，请检查输入）")
    for p in rep.plan:
        L.append("")
        L.append("### %s　%s %s" % (p["course"], p["date"], p["slot"]))
        L.append("| 考场 | 座位 | 班级分配 | 监考教师 | 缺口 |")
        L.append("|---|---|---|---|---|")
        for rp in p["rooms"]:
            cls_s = ", ".join("%s×%d" % (c[0], c[1]) for c in rp["classes"])
            inv_s = "、".join(rp["invigilators"]) if rp["invigilators"] else "—"
            L.append("| %s | %d | %s | %s | %s |" % (
                rp["room"], rp["seat"], cls_s, inv_s, rp["missing"] or ""))
    L.append("")
    L.append("## 四、监考日程（按教师）")
    if not rep.teacher_sched:
        L.append("- 暂无已分配监考教师")
    by = defaultdict(list)
    for r in rep.teacher_sched:
        by[r["name"]].append(r)
    for name in sorted(by):
        items = by[name]
        L.append("- **%s**（%d 场）：%s" % (
            name, len(items),
            "；".join("%s %s → %s" % (i["date"], i["slot"], i["room"]) for i in items)))
    L.append("")
    L.append("## 五、汇总")
    cap = rep.stats["capacity"]
    # 峰值利用率：单场最大座位需求 / 总容量（教室可跨场次复用）
    peak = max((sum(rp["seat"] for rp in p["rooms"]) or 0) for p in rep.plan) if rep.plan else 0
    util = (100.0 * peak / cap) if cap else 0.0
    L.append("- 编排场次 %d · 累计座位 %d · 单场峰值座位 %d / 总容量 %d（峰值利用率 %.1f%%）" % (
        rep.stats["exams"], rep.stats["seats"], peak, cap, util))
    L.append("- 缺口项 %d（见第二节）" % len(errs))
    L.append("")
    L.append("> 本报告由算法自动生成，发布前请人工核对考场与班级名单。")
    return "\n".join(L) + "\n"


def to_json(rep):
    return {
        "summary": {"exams": rep.stats["exams"], "seats": rep.stats["seats"],
                    "capacity": rep.stats["capacity"], "teachers": rep.stats["teachers"],
                    "issue_count": len(rep.issues)},
        "issues": [{"severity": s, "message": m} for s, m in rep.issues],
        "plan": [
            {"course": p["course"], "date": p["date"], "slot": p["slot"],
             "rooms": [{"room": r["room"], "seat": r["seat"],
                        "classes": [[c[0], c[1]] for c in r["classes"]],
                        "invigilators": r["invigilators"], "missing": r["missing"]}
                       for r in p["rooms"]]}
            for p in rep.plan
        ],
        "invigilator_schedule": rep.teacher_sched,
    }


# ---------------- 主流程 ----------------

rules_now = {}


def run(input_text):
    """解析 + 编排，返回 Report。"""
    global rules_now
    rep = Report()
    try:
        data = json.loads(input_text)
    except json.JSONDecodeError as e:
        rep.add("fatal", "JSON 解析失败: %s" % e)
        return rep
    exams_raw, rooms_raw, teachers_raw, rules_raw, iss = parse_top(data)
    for sev, m in iss:
        rep.add(sev, m)
    if rep.has("fatal"):
        return rep
    rules_now = parse_rules(rules_raw)
    exams = parse_exams(exams_raw, rep)
    rooms = parse_rooms(rooms_raw, rep)
    teachers = parse_teachers(teachers_raw, rep, rules_now["default_max_per_day"])
    if not exams:
        rep.add("error", "无有效考试场次可编排，请检查 exams 字段")
    if not rooms:
        rep.add("error", "无有效考场（rooms 为空或全部无效），全部场次无法排座位")
    rep.stats["rooms"] = len(rooms)
    rep.stats["teachers"] = len(teachers)
    rep.stats["capacity"] = sum(r["capacity"] for r in rooms)
    build_exam_plan(exams, rooms, teachers, rules_now, rep)
    rep.teacher_sched = build_teacher_sched(teachers)
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="考场编排与监考调度生成器（零依赖，离线可用）",
        epilog="示例:\n"
               "  python3 exam_scheduler.py input.json\n"
               "  python3 exam_scheduler.py input.json --json\n"
               "  cat input.json | python3 exam_scheduler.py --json\n"
               "  python3 exam_scheduler.py input.json --out result.json")
    ap.add_argument("input", nargs="?", help="输入 JSON 文件路径（缺省从 stdin 读取）")
    ap.add_argument("--json", action="store_true", help="输出结构化 JSON")
    ap.add_argument("--out", metavar="FILE", help="把 JSON 结果写入文件")
    args = ap.parse_args(argv)

    if args.input:
        try:
            with open(args.input, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            print("错误: 无法读取输入文件 %s: %s" % (args.input, e))
            return 2
    else:
        text = sys.stdin.read()

    rep = run(text)
    if args.json or args.out:
        payload = json.dumps(to_json(rep), ensure_ascii=False, indent=2)
        if args.out:
            try:
                with open(args.out, "w", encoding="utf-8") as f:
                    f.write(payload)
                print("已写出 JSON 结果到 %s" % args.out)
            except OSError as e:
                print("错误: 写入 %s 失败: %s" % (args.out, e))
                return 2
        else:
            print(payload)
    else:
        print(render_markdown(rep, rules_now))
    return 0 if not rep.has("error", "fix", "fatal") else 1


if __name__ == "__main__":
    sys.exit(main())