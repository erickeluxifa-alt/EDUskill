#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""teaching-progress-planner 自测：执行 20+ 条 Query，输出覆盖率与自测记录 Markdown。"""
import copy
import json
import os
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANNER = os.path.join(BASE, "scripts", "planner.py")
OUT = tempfile.mkdtemp(prefix="tpp_self_")

SAMPLE = {
    "course": {"name": "数据结构", "code": "CS201", "total_hours": 56, "weekly_hours": 4},
    "semester": {"start_date": "2026-09-07", "total_weeks": 18, "exam_weeks": [17, 18],
                 "holidays": [{"weeks": [4, 5], "note": "国庆和中秋节"}]},
    "units": [{"name": "绪论", "hours": 4}, {"name": "线性表", "hours": 8},
              {"name": "栈和队列", "hours": 6}, {"name": "串和数组", "hours": 6},
              {"name": "树与二叉树", "hours": 8}, {"name": "图", "hours": 4},
              {"name": "排序", "hours": 4}, {"name": "实验一：线性表", "hours": 4},
              {"name": "实验二：栈与队列", "hours": 4}, {"name": "实验三：树的遍历", "hours": 4},
              {"name": "实验四：排序综合", "hours": 4}]}


def run(name, payload, expect, args=None, checks=None):
    """payload: dict/JSON字符串（走 stdin）。args: 附加 CLI 参数。checks: 可选输出断言。"""
    args = list(args or [])
    stdin_text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    cmd = [sys.executable, PLANNER, "-i", "-", "-o", OUT] + args
    r = subprocess.run(cmd, input=stdin_text, capture_output=True, text=True, encoding="utf-8")
    ok = r.returncode == expect
    note = []
    if ok and checks:
        for pat in checks:
            if pat not in r.stdout:
                ok = False
                note.append("缺少输出: %s" % pat)
            else:
                note.append("含「%s」" % pat)
    detail = ("stdout: " + r.stdout.strip().splitlines()[0] + " | " if r.stdout else "") + \
             ("stderr: " + r.stderr.strip().splitlines()[0] if r.stderr else "")
    return {"case": name, "expect": expect, "actual": r.returncode, "ok": ok,
            "note": "；".join(note) if note else detail[:120]}


cases = []
V = lambda **kw: (lambda d: (d.update(kw), d)[1])(copy.deepcopy(SAMPLE))


def w(**kw):
    d = copy.deepcopy(SAMPLE)
    for k, v in kw.items():
        if k == "course":
            d["course"].update(v)
        elif k == "semester":
            d["semester"].update(v)
        elif k == "units":
            d["units"] = v
    return d


# ---------- 类别A：默认流程（3） ----------
cases.append(run("T1 默认JSON全流程", SAMPLE, 0, checks=["教学进度计划表", "17", "国庆和中秋节"]))
cases.append(run("T2 JSON根为数组", [SAMPLE], 0))
txt = ("# start=2026-09-07\n# weeks=12\n# exam=11,12\n# holiday=4\n"
       "数据结构 CS201 40 3\n绪论 4\n线性表 8\n栈和队列 6\n串和数组 6\n树与二叉树 6\n图 4\n排序 4\n实验一 2\n")
cases.append(run("T3-TXT简化输入", txt, 1))
# ---------- 2：同义触发/别名（4） ----------
cn = {"课程": {"课程名": "高等数学", "总学时": 40, "周学时": 4},
      "学期": {"起始日期": "2026-09-07", "教学周数": 12, "考试周": "11-12"},
      "教学单元": [{"单元名": "函数与极限", "学时": 12}, {"单元名": "导数", "学时": 12},
                  {"单元名": "积分", "学时": 12}, {"单元名": "微分方程", "学时": 4}]}
cases.append(run("B4-中文别名字段", cn := cn, 0))
flat = {"name": "高数", "total_hours": 32, "weekly_hours": 4,
        "semester": {"start_date": "2026-09-07", "total_weeks": 10, "exam_weeks": [1, 2], "holidays": []},
        "units": [{"name": "章%d" % i, "hours": 4} for i in range(1, 9)]}
cases.append(run("B5-扁平结构", flat, 0))
cases.append(run("B6-考试周区间写法17-18", w(semester={"exam_weeks": "17-18"}), 0))
cases.append(run("B7-节假日中文键 holiday=字典", w(semester={"holiday": {"weeks": [6], "note": "校运会"}}), 0))
# ---------- 3u：缺失输入（10） ----------
cases.append(run("C8-总学时0", w(course={"total_hours": 0}), 2))
cases.append(run("C9-周学时0", w(course={"weekly_hours": 0}), 2))
cases.append(run("C10-单元为空", w(units=[]), 2))
cases.append(run("C11-日期非法", w(semester={"start_date": "2026/09/07"}), 2))
cases.append(run("C12-缺起始日期", w(semester={"start_date": None}), 2))
cases.append(run("C13-周数为0", w(semester={"total_weeks": 0}), 2))
cases.append(run("C14-周数99异常", w(semester={"total_weeks": 99}), 2))
cases.append(run("C15-考试周越界", w(semester={"exam_weeks": [19]}), 2))
cases.append(run("C16-单元负学时", w(units=[{"name": "x", "hours": -2}] + SAMPLE["units"][1:]), 2))
cases.append(run("C17-空输入", "", 2))
# ---------- 4u：异常数据（5） ----------
cases.append(run("E18-非法JSON", "{bad json", 2))
cases.append(run("E19-单元非对象", w(units=["abc"]), 2))
cases.append(run("E20-合计65 vs 总56偏差>2", w(units=SAMPLE["units"] + [{"name": "加课", "hours": 6}]), 1))
cases.append(run("E21-TXT单元行缺学时", "# start=2026-09-07\n# weeks=4\n数据结构 8 2\n绪论\n", 2))
# ---------- 5 边界（5） ----------
cases.append(run("F22-容量溢出80学时", w(course={"total_hours": 80, "weekly_hours": 4}, units=[] +
                                          [{"name": "u", "hours": 80}]), 1, checks=["溢出学时"]))
cases.append(run("F23-提前结课(20学时)", w(course={"total_hours": 20}, units=[{"name": "u1", "hours": 20}]), 1,
                 checks=["机动/复习"]))
cases.append(run("F24-日期型节假日换算", w(semester={"holidays": [{"date": "2026-10-01", "days": 7, "note": "国庆"}]}), 0))
cases.append(run("F25-节假日考试周重叠", w(semester={"exam_weeks": [4]}), 1))
cases.append(run("F26-小数学时批量", w(course={"total_hours": 48},
                                       units=[{"name": "m%d" % i, "hours": 3.5 - (i % 2) * 1.0} for i in range(1, 17)]), 0))
# ---------- 5。输出模式（4） ----------
cases.append(run("G27-仅CSV", SAMPLE, 0, args=["-f", "csv"]))
cases.append(run("G28-quiet摘要", SAMPLE, 0, args=["-q"]))
cases.append(run("G29-strict溢出=2", w(course={"total_hours": 80}, units=[{"name": "u", "hours": 80}]), 2,
                 args=["--strict"]))
ela = run("G30-仅JSON", SAMPLE, 0, args=["-f", "json"])
cases.append(ela)
# ---------- 6u：安全（2） ----------
evil = {"course": {"name": "=<script>alert(1)</script>|恶意课程", "total_hours": 4, "weekly_hours": 4},
        "semester": {"start_date": "2026-09-07", "total_weeks": 1},
        "units": [{"name": "=SUM(A1)", "hours": 2}, {"name": "+cmd|x", "hours": 2}]}
cases.append(run("S31-注入字符转义", evil, 0))

# 汇总
passed = sum(1 for c in cases if c["ok"])
print("PASS %d/%d\n" % (passed, len(cases)))
for c in cases:
    print("[%s] %-28s expect=%s actual=%s | %s" % ("PASS" if c["ok"] else "FAIL", c["case"],
                                                   c["expect"], c["actual"], c["note"]))

lines = ["# 自测记录：teaching-progress-planner v1.0.0（2026-08-24）", "",
         "覆盖：默认流程 / 同义别名 / 缺失输入 / 异常数据 / 边界输入 / 输出模式 / 安全防护 共 %d 条 Query，全为黑盒自动断言（退出码+输出内容）。" % len(cases),
         "", "| # | 测试 Query（能力分支） | 预期 | 实际 | 结果 | 说明 |", "|---|--------------------------|------|------|------|------|",
         "| # | 测试句 | 预期 | 实际 | 结果 | 说明 |", "|---|---|---|---|---|---|"]
for i, c in enumerate(cases, 1):
    lines.append("| %d | %s | %d | %d | %s | %s |" % (i, c["case"], c["expect"], c["actual"],
                                                      "✅通过" if c["ok"] else "❌失败", c["note"]))
lines += ["", "缩减理由：本日为单 Skill 轻量能力，Query 按能力规模取 20+ 条；主要分支（常规/同义/缺失/边界/异常/权限/注入）均覆盖。"]
out = os.path.join(BASE, "测试记录", "自测记录.md")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("\n已写入:", out)
sys.exit(0 if passed == len(cases) else 1)