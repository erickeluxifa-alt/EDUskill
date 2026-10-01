#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
教学进度计划生成器 teaching-progress-planner v1.0.0
按校历（教学周/考试周/节假日）将课程大纲章节自动编排为每周教学进度表。

输入  : JSON（或简化 TXT，见 README）
输出  : Markdown 周计划表 + 结构化 JSON + CSV（可导入 Excel）
退出码: 0=成功无警告; 1=成功但存在警告; 2=输入错误
零依赖: 仅使用 Python 标准库
"""

import argparse
import csv
import html
import io
import json
import os
import re
import sys
from datetime import date, datetime, timedelta

DATE_FMT = "%Y-%m-%d"
WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


# ---------------------------------------------------------------- 工具函数
def to_float(s, what="学时"):
    """把文本/数字转为 float，失败抛 ValueError。"""
    if isinstance(s, (int, float)):
        return float(s)
    try:
        return float(str(s).strip())
    except (ValueError, AttributeError):
        raise ValueError("%s必须是数字，收到: %r" % (what, s))


def to_week_list(v):
    """周次多种写法 → 排序去重 int 列表。支持 17 / "17,18" / [17,18] / "17-18" / [("1","3")] 等。"""
    if v is None or v == "":
        return []
    if isinstance(v, int):
        return [v]
    if isinstance(v, (list, tuple)):
        out = []
        for item in v:
            out.extend(to_week_list(item))
        return sorted(set(out))
    if isinstance(v, str):
        out = []
        for part in str(v).replace("，", ",").replace("、", ",").split(","):
            part = part.strip()
            if not part:
                continue
            m = re.match(r"^(\d+)\s*[-~]\s*(\d+)$", part)
            if m:
                out.extend(range(int(m.group(1)), int(m.group(2)) + 1))
            else:
                out.append(int(part))
        return sorted(set(out))
    return sorted(set(int(x) for x in v))


def md_escape(s):
    s = str(s or "").replace("|", "\\|").replace("\n", " ")
    s = html.escape(s)
    return s


def csv_cell(s):
    """CSV 单元格：公式注入防护 + 统一字符串化。"""
    s = str(s if s is not None else "")
    if s and s[0] in ("=", "+", "-", "@"):
        s = "'" + s
    return s


def parse_date(s, field="起始日期"):
    """解析 YYYY-MM-DD，失败抛 ValueError。"""
    try:
        return datetime.strptime(str(s), DATE_FMT).date()
    except (ValueError, TypeError):
        raise ValueError("%s格式错误（应为 YYYY-MM-DD）: %r" % (field, s))


# ---------------------------------------------------------------- 输入解析
def parse_json(data):
    """解析 JSON 输入，兼容中英文字段别名。"""
    if not isinstance(data, dict):
        raise ValueError("JSON 根节点必须是对象（或对象数组）")
    course = data.get("course") or data.get("课程") or {}
    sem = data.get("semester") or data.get("学期") or {}
    if not isinstance(course, dict) or not isinstance(sem, dict):
        raise ValueError("course/semester 必须是对象")
    # 扁平结构兜底：course 字段直接平铺在根
    if not course and ("name" in data or "课程名" in data):
        course = data
    cname = course.get("name") or course.get("课程名") or "（未命名课程）"
    code = course.get("code") or course.get("课程代码") or ""
    total_hours = to_float(course.get("total_hours", course.get("hours", course.get("总学时", 0))))
    weekly_hours = to_float(course.get("weekly_hours", course.get("weekly", course.get("周学时", 0))))
    start_date = sem.get("start_date") or sem.get("起始日期")
    total_weeks = to_week_list(sem.get("total_weeks", sem.get("weeks", sem.get("教学周数", 0))))
    total_weeks = total_weeks[-1] if total_weeks else 0
    exam_weeks = to_week_list(sem.get("exam_weeks", sem.get("exam", sem.get("考试周", []))))
    holidays = sem.get("holidays") or sem.get("holiday") or sem.get("节假日") or []
    if isinstance(holidays, dict):
        holidays = [holidays]
    teaching_days = sem.get("teaching_days") or sem.get("上课日") or None
    raw_units = data.get("units") or data.get("教学单元") or []
    units = []
    for i, u in enumerate(raw_units):
        if not isinstance(u, dict):
            raise ValueError("教学单元第 %d 项必须是对象（含 name/hours 字段），收到: %r" % (i + 1, u))
        units.append({
            "idx": i,
            "name": u.get("name") or u.get("单元名") or u.get("chapter") or u.get("章") or "（未命名单元）",
            "hours": to_float(u.get("hours", u.get("学时", 0))),
        })
    return {
        "course": {"name": cname, "code": code, "total_hours": total_hours, "weekly_hours": weekly_hours},
        "semester": {"start_date": start_date, "total_weeks": total_weeks,
                     "exam_weeks": exam_weeks, "holidays": holidays, "teaching_days": teaching_days},
        "units": units,
    }


def parse_txt(text):
    """解析简化 TXT：首行「课程名 [代码] 总学时 周学时」，# 开头为配置（key=value），其余行为「单元名 学时」。"""
    cfg = {"name": "", "code": "", "total_hours": 0.0, "weekly_hours": 0.0,
           "start_date": None, "total_weeks": 0, "exam_weeks": [], "holidays": [], "units": []}
    first_course = False
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            m = re.match(r"^#\s*([^=:]+)[=:]\s*(.*)$", line)
            if not m:
                continue
            k, v = m.group(1).strip(), m.group(2).strip()
            if k in ("start", "start_date", "起始日期"):
                cfg["start_date"] = v
            elif k in ("weeks", "total_weeks", "教学周数"):
                wl = to_week_list(v)
                cfg["total_weeks"] = wl[-1] if wl else 0
            elif k in ("exam", "exam_weeks", "考试周"):
                cfg["exam_weeks"] = to_week_list(v)
            elif k in ("holiday", "holidays", "节假日周"):
                wl = to_week_list(v)
                if wl:
                    cfg["holidays"].append({"weeks": wl, "note": "节假日"})
            elif k in ("weekly", "weekly_hours", "周学时"):
                cfg["weekly_hours"] = to_float(v)
            elif k in ("code", "课程代码"):
                cfg["code"] = v
            continue
        cells = re.split(r"[\s,，]+", line)
        if not first_course:
            cfg["name"] = cells[0]
            nums = []
            strs = []
            for cell in cells[1:]:
                try:
                    nums.append(float(cell))
                except ValueError:
                    strs.append(cell)
            if len(nums) >= 2:
                cfg["total_hours"], cfg["weekly_hours"] = nums[0], nums[1]
                if strs:
                    cfg["code"] = strs[0]
            elif len(nums) == 1:
                cfg["total_hours"] = nums[0]
            first_course = True
        else:
            if len(cells) < 2:
                raise ValueError("单元行格式错误（应为「单元名 学时」）: %s" % line)
            try:
                h = float(cells[-1])
            except ValueError:
                raise ValueError("单元行学时必须是数字: %s" % line)
            cfg["units"].append({"name": " ".join(cells[:-1]), "hours": h})
    return {
        "course": {"name": cfg["name"] or "（未命名课程）", "code": cfg["code"],
                   "total_hours": cfg["total_hours"], "weekly_hours": cfg["weekly_hours"]},
        "semester": {"start_date": cfg["start_date"], "total_weeks": cfg["total_weeks"],
                     "exam_weeks": cfg["exam_weeks"], "holidays": cfg["holidays"],
                     "teaching_days": None},
        "units": cfg["units"],
    }


def try_parse(raw):
    raw = raw.strip()
    if not raw:
        raise ValueError("输入为空")
    if raw.startswith("{") or raw.startswith("["):
        data = json.loads(raw)
        if isinstance(data, list):
            return data[0]  # 兼容数组形式
        return parse_json(data)
    return parse_txt(raw)


# ---------------------------------------------------------------- 校验与周历
def validate(cfg):
    """返回 (errors, warnings)。errors 非空 → 退出码 2。"""
    errors, warnings = [], []
    course, sem, units = cfg["course"], cfg["semester"], cfg["units"]
    if course["total_hours"] <= 0:
        errors.append("总学时缺失或非正数（收到 %.1f）" % course["total_hours"])
    if course["weekly_hours"] <= 0:
        errors.append("周学时缺失或非正数（收到 %.1f）" % course["weekly_hours"])
    if not units:
        errors.append("教学单元列表为空")
    for u in units:
        if u["hours"] < 0:
            errors.append("单元「%s」学时为负 %.1f" % (u["name"], u["hours"]))
    if not sem["start_date"]:
        errors.append("缺少学期起始日期 start_date")
    else:
        try:
            parse_date(sem["start_date"])
        except ValueError as e:
            errors.append(str(e))
    if sem["total_weeks"] <= 0:
        errors.append("学期教学周数缺失或非正数")
    if sem["total_weeks"] > 60:
        errors.append("学期教学周数异常（%d > 60），疑似输入错误" % sem["total_weeks"])
    for w in sem["exam_weeks"]:
        if w < 1 or w > sem["total_weeks"]:
            errors.append("考试周 %d 超出学期周范围 1..%d" % (w, sem["total_weeks"]))
    if errors:
        return errors, warnings
    # 学时一致性
    raw_hours = sum(u["hours"] for u in units)
    if abs(raw_hours - course["total_hours"]) > 2:
        warnings.append("单元学时合计 %.1f 与课程总学时 %.1f 偏差超过 2 学时，以单元合计为准" % (raw_hours, course["total_hours"]))
    # 容量分析
    hw = compute_holiday_map(cfg["semester"])
    holiday_set = set(hw)
    exam_set = set(sem["exam_weeks"])
    dup = exam_set & holiday_set
    if dup:
        warnings.append("周次 %s 同时是节假日与考试周，按节假日处理（去重）" % ",".join(map(str, sorted(dup))))
    teach_weeks = [w for w in range(1, sem["total_weeks"] + 1) if w not in exam_set and w not in holiday_set]
    capacity = len(teach_weeks) * course["weekly_hours"]
    if raw_hours > capacity + 1e-9:
        warnings.append("教学学时 %.1f 超出排课容量 %.1f（%d 个可授课周 × 周 %g 学时），超出 %.1f 学时请人工压缩或加课" %
                        (raw_hours, capacity, len(teach_weeks), course["weekly_hours"], raw_hours - capacity))
    elif capacity - raw_hours > course["weekly_hours"] * 2 + 1e-9:
        warnings.append("计划提前结课：学时仅需约 %.1f 周（剩余周将标注为「机动/复习」）" % (raw_hours / course["weekly_hours"]))
    return errors, warnings


def compute_holiday_map(sem):
    """返回 {周次: 备注}。日期型节假日自动换算所在周。"""
    start = parse_date(sem["start_date"]) if sem["start_date"] else None
    hmap = {}
    for h in (sem["holidays"] or []):
        if not isinstance(h, dict):
            continue
        weeks = []
        if h.get("weeks"):
            weeks = to_week_list(h["weeks"])
        elif h.get("week") is not None:
            weeks = [int(h["week"])]
        elif h.get("date") and start:
            d = parse_date(h["date"], "节假日日期")
            days = max(1, int(h.get("days", 1)))
            for i in range(days):
                w = (d + timedelta(days=i) - start).days // 7 + 1
                weeks.append(w)
        note = h.get("note") or "节假日"
        for w in weeks:
            if 1 <= w and (not sem["total_weeks"] or w <= sem["total_weeks"]):
                hmap[w] = note
    return hmap


# ---------------------------------------------------------------- 分配
def allocate(cfg, teach_weeks):
    """贪心顺序分配。返回 (rows, overflow)。rows: {week: {"blocks":[...], "hours": x}}"""
    weekly = cfg["course"]["weekly_hours"]
    rows = {w: {"blocks": [], "hours": 0.0} for w in teach_weeks}
    wi = 0
    remain = weekly
    overflow = []
    for u in cfg["units"]:
        rem = u["hours"]
        if rem <= 0:
            continue
        first = True
        while rem > 1e-9:
            if remain <= 1e-9:
                wi += 1
                remain = weekly
            if wi >= len(teach_weeks):
                overflow.append({"name": u["name"], "hours": round(rem, 1)})
                break
            w = teach_weeks[wi]
            take = min(rem, remain)
            if take > 1e-9:
                rows[w]["blocks"].append({"name": u["name"], "hours": take, "cont": not first})
                rows[w]["hours"] += take
                rem -= take
                remain -= take
            first = False
    return rows, overflow


# ---------------------------------------------------------------- 渲染
def week_range(start, w):
    d0 = start + timedelta(weeks=w - 1)
    return d0, d0 + timedelta(days=6)


def render_md(cfg, teach_weeks, rows, overflow, hmap, warnings):
    c, sem = cfg["course"], cfg["semester"]
    start = parse_date(sem["start_date"])
    exam_set = set(sem["exam_weeks"])
    L = ["# 教学进度计划表", "",
         "- 课程：**%s**（%s）" % (md_escape(c["name"]), md_escape(c["code"]) or "无课程代码"),
         "- 总学时：%.1f　周课时：%.1f" % (c["total_hours"], c["weekly_hours"]),
         "- 学期：%s 起，共 %d 周；考试周：%s；节假日周：%s" % (
             sem["start_date"], sem["total_weeks"],
             ",".join(map(str, sorted(exam_set))) or "无",
             ",".join(map(str, sorted(hmap))) or "无"),
         "- 期末学时合计：%.1f" % sum(u["hours"] for u in cfg["units"]), "",
         "| 周次 | 日期区间 | 教学内容（学时） | 备注 |",
         "|------|----------|------------------|------|"]
    for w in range(1, sem["total_weeks"] + 1):
        d0, d1 = week_range(start, w)
        ds = "%s ~ %s" % (d0.strftime("%m-%d"), d1.strftime("%m-%d"))
        if w in hmap:
            L.append("| {w} | {d} | — | {note} |".format(w=w, d=ds, note=md_escape(hmap[w] or "节假日")))
            continue
        if w in exam_set:
            L.append("| {w} | {d} | — | 考试周（不排课） |".format(w=w, d=ds))
            continue
        if w in rows and rows[w]["blocks"]:
            parts = []
            for b in rows[w]["blocks"]:
                label = "%s（续）" % b["name"] if b["cont"] else b["name"]
                parts.append("%s×%.1f" % (label, b["hours"]))
            L.append("| {w} | {d} | {content} | {h} 学时 |".format(
                w=w, d=ds, content=md_escape("；".join(parts)), h=rows[w]["hours"]))
        else:
            L.append("| %d | %s | — | 机动/复习 |" % (w, ds))
    L.append("")
    if overflow:
        L.append("### 溢出学时（超出排课容量，需人工调整）")
        for x in overflow:
            L.append("- %s：%.1f 学时" % (md_escape(x["name"]), x["hours"]))
        L.append("")
    if warnings:
        L.append("### 检查提示")
        for wg in warnings:
            L.append("- ⚠ %s" % md_escape(wg))
        L.append("")
    return "\n".join(L)


def render_json(cfg, teach_weeks, rows, overflow, hmap, warnings):
    c, sem = cfg["course"], cfg["semester"]
    start = parse_date(sem["start_date"])
    exam_set = set(sem["exam_weeks"])
    weeks_out = []
    for w in range(1, sem["total_weeks"] + 1):
        d0, d1 = week_range(start, w)
        e = {"week": w, "start": d0.isoformat(), "end": d1.isoformat()}
        if w in hmap:
            e["note"] = hmap[w] or "节假日"
        elif w in exam_set:
            e["note"] = "考试周"
        elif w in rows and rows[w]["blocks"]:
            e["blocks"] = [{"unit": b["name"], "hours": b["hours"], "continuation": b["cont"]}
                           for b in rows[w]["blocks"]]
            e["hours"] = rows[w]["hours"]
        else:
            e["note"] = "机动/复习"
        weeks_out.append(e)
    return {
        "course": {"code": c["code"], "name": c["name"], "total_hours": c["total_hours"],
                   "weekly_hours": c["weekly_hours"]},
        "semester": {"start_date": sem["start_date"], "total_weeks": sem["total_weeks"],
                     "exam_weeks": sorted(exam_set), "holiday_weeks": sorted(hmap)},
        "total_unit_hours": sum(u["hours"] for u in cfg["units"]),
        "weeks": weeks_out,
        "overflow": overflow,
        "warnings": warnings,
    }


def render_csv(cfg, teach_weeks, rows, overflow, hmap, warnings):
    buf = io.StringIO()
    wr = csv.writer(buf)
    wr.writerow(["周次", "起始日期", "结束日期", "教学内容", "学时", "备注"])
    start = parse_date(cfg["semester"]["start_date"])
    exam_set = set(cfg["semester"]["exam_weeks"])
    for w in range(1, cfg["semester"]["total_weeks"] + 1):
        d0, d1 = week_range(start, w)
        if w in hmap:
            wr.writerow([w, d0.isoformat(), d1.isoformat(), "", "", csv_cell(hmap[w] or "节假日")])
        elif w in exam_set:
            wr.writerow([w, d0.isoformat(), d1.isoformat(), "", "", "考试周"])
        elif w in rows and rows[w]["blocks"]:
            content = "；".join(("%s（续）" % b["name"] if b["cont"] else b["name"]) + "×%.1f" % b["hours"]
                                for b in rows[w]["blocks"])
            wr.writerow([w, d0.isoformat(), d1.isoformat(), csv_cell(content), rows[w]["hours"], ""])
        else:
            wr.writerow([w, d0.isoformat(), d1.isoformat(), "", "", "机动/复习"])
    return buf.getvalue()


# ---------------------------------------------------------------- 主流程
def main(argv=None):
    ap = argparse.ArgumentParser(description="教学进度计划生成器：按校历把课程章节编排为每周教学进度表")
    ap.add_argument("--input", "-i", default="-", help="输入文件（JSON 或 TXT），默认标准输入")
    ap.add_argument("--format", "-f", default="all", choices=["all", "md", "json", "csv"])
    ap.add_argument("--outdir", "-o", default=".", help="输出目录（默认当前目录）")
    ap.add_argument("--strict", action="store_true", help="严格模式：学时偏差/容量溢出时返回退出码 2")
    ap.add_argument("--quiet", "-q", action="store_true", help="只输出摘要，不打印完整 Markdown")
    args = ap.parse_args(argv)

    try:
        raw = load_text(args.input)
        cfg = try_parse(raw)
    except (ValueError, json.JSONDecodeError) as e:
        sys.stderr.write("ERR 输入解析失败: %s\n" % e)
        return 2

    errors, warnings = validate(cfg)
    if errors:
        for e in errors:
            sys.stderr.write("ERR %s\n" % e)
        return 2

    hmap = compute_holiday_map(cfg["semester"])
    exam_set = set(cfg["semester"]["exam_weeks"])
    teach_weeks = [w for w in range(1, cfg["semester"]["total_weeks"] + 1)
                    if w not in exam_set and w not in hmap]
    rows, overflow = allocate(cfg, teach_weeks)

    os.makedirs(args.outdir, exist_ok=True)
    if args.format in ("all", "md"):
        with io.open(os.path.join(args.outdir, "教学进度计划.md"), "w", encoding="utf-8") as f:
            f.write(render_md(cfg, teach_weeks, rows, overflow, hmap, warnings))
    if args.format in ("all", "json"):
        with io.open(os.path.join(args.outdir, "教学进度计划.json"), "w", encoding="utf-8") as f:
            json.dump(render_json(cfg, teach_weeks, rows, overflow, hmap, warnings), f,
                      ensure_ascii=False, indent=2)
    if args.format in ("all", "csv"):
        with io.open(os.path.join(args.outdir, "教学进度计划.csv"), "w", encoding="utf-8-sig", newline="") as f:
            f.write(render_csv(cfg, teach_weeks, rows, overflow, hmap, warnings))

    if not args.quiet:
        print(render_md(cfg, teach_weeks, rows, overflow, hmap, warnings))
    else:
        print("已生成教学进度计划（%d 个教学周）；警告 %d 条；溢出学时 %d 条" %
              (len(teach_weeks), len(warnings), len(overflow)))
    if args.strict and (warnings or overflow):
        return 2
    return 1 if (warnings or overflow) else 0


def load_text(path):
    if path == "-":
        return sys.stdin.read()
    with io.open(path, "r", encoding="utf-8-sig") as f:
        return f.read()


if __name__ == "__main__":
    sys.exit(main())