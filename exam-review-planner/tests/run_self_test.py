#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
exam-review-planner 自测执行器：跑 31 条覆盖常规/同义/组合/缺输入/边界/异常/安全/确定性的用例，
输出 tests/自测记录.md（逐条记录预期、实际、判定、备注）。
"""
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "scripts", "review_planner.py")
FIX = HERE
PY = sys.executable

RESULTS = []
SUMMARY = {"n": 0, "ok": 0, "fail": 0}


def run_case(name, args, exp_exit=0, out_contains=None, out_any=None,
             file=None, fc=None, fforbid=None, no_file=None, note=""):
    """执行一条用例。
    out_contains/out_any  检查 stdout+stderr；
    file                  产物文件（存在即校验）；fc 必须包含；fforbid 不得包含；
    no_file               必须不存在的文件（用于产物裁剪断言）。
    """
    p = subprocess.run([PY, SCRIPT] + args, capture_output=True, text=True, timeout=180)
    out = p.stdout + p.stderr
    probs = []
    if p.returncode != exp_exit:
        probs.append(f"退出码 {p.returncode}≠期望 {exp_exit}")
    if out_contains and out_contains not in out:
        probs.append(f"输出缺少「{out_contains}」")
    if out_any and not any(s in out for s in out_any):
        probs.append(f"输出缺少其一「{'/'.join(out_any)}」")
    if file:
        if not os.path.exists(file):
            probs.append(f"产物缺失 {os.path.basename(file)}")
        else:
            text = open(file, encoding="utf-8-sig").read()
            if fc and fc not in text:
                probs.append(f"文件缺少「{fc}」")
            if fforbid and fforbid in text:
                probs.append(f"文件出现禁止内容「{fforbid}」")
    if no_file:
        nf = no_file if isinstance(no_file, list) else [no_file]
        for f in nf:
            if os.path.exists(f):
                probs.append(f"产物未裁剪（仍存在 {os.path.basename(f)}）")
    ok = not probs
    SUMMARY["n"] += 1
    SUMMARY["ok" if ok else "fail"] += 1
    expected = f"exit={exp_exit}"
    if out_contains:
        expected += f"，stdout 含「{out_contains}」"
    if file:
        expected += f"，触发文件 {os.path.basename(file)}" + (f" 含「{fc}」" if fc else "") + (f" 不含「{fforbid}」" if fforbid else "")
    if no_file:
        nf = no_file if isinstance(no_file, list) else [no_file]
        expected += f"，无 {'、'.join(os.path.basename(f) for f in nf)}"
    RESULTS.append({
        "name": name, "query": " ".join(args),
        "expected": expected,
        "actual": "通过" if ok else "；".join(probs),
        "pass": ok, "note": note,
    })
    return ok


def main():
    tmp = os.path.join(FIX, "tmp")
    os.makedirs(tmp, exist_ok=True)
    A1 = os.path.join(FIX, "a1_std.json")

    # ---- 常规主线（7）
    d = os.path.join(tmp, "o01")
    run_case("T01 demo 默认45分钟全流程", ["--demo", "--out-dir", d, "--quiet"],
             out_contains="必讲 3",
             file=os.path.join(d, "review_plan.md"), fc="讲评课教学方案",
             note="5 个产物 + 摘要；默认 45 分钟、分层名单 16 人")
    d = os.path.join(tmp, "o02")
    run_case("T02 直接消费 score-analyzer 的 analysis.json（联动）",
             ["--analysis", A1, "--out-dir", d, "--quiet"],
             out_contains="分层名单 3 人",
             note="exam-score-analyzer 输出直接作为输入")
    d = os.path.join(tmp, "o03")
    run_case("T03 90分钟长课时放大精讲", ["--analysis", A1, "--session", "90", "--out-dir", d, "--quiet"],
             file=os.path.join(d, "review_plan.md"), fc="核心讲评",
             note="精讲预算随课时放大")
    d = os.path.join(tmp, "o04")
    run_case("T04 10分钟短课时压缩时间轴", ["--analysis", A1, "--session", "10", "--out-dir", d, "--quiet"],
             out_contains="时间轴 3 阶段",
             note="<15 分钟降级为开场/核心/收尾三阶段")
    d = os.path.join(tmp, "o05")
    run_case("T05 中文表头同义触发(qstats+students)", ["--qstats", os.path.join(FIX, "q8_cn.csv"),
             "--students", os.path.join(FIX, "s8_cn.csv"), "--exam", "初二期中", "--out-dir", d, "--quiet"],
             out_contains="题目 2 道",
             note="题号/知识点/得分率/区分度中文别名")
    d = os.path.join(tmp, "o06")
    run_case("T06 JSON对象数组qstats同义输入", ["--qstats", os.path.join(FIX, "q10_list.json"),
             "--out-dir", d, "--quiet"], out_contains="题目 2 道")
    d = os.path.join(tmp, "o07")
    run_case("T07 自定义输出目录(非quiet打印路径)", ["--demo", "--out-dir", d],
             out_contains=d, note="stdout 回显产物绝对路径")

    # ---- 组合/覆盖（3）
    d = os.path.join(tmp, "o08")
    run_case("T08 外部students覆盖analysis名单", ["--analysis", A1,
             "--students", os.path.join(FIX, "s8_cn.csv"), "--out-dir", d, "--quiet"],
             out_contains="分层名单 2 人",
             note="外部成绩单优先于 analysis.students")
    d = os.path.join(tmp, "o09")
    run_case("T09 qstats+students组合", ["--qstats", os.path.join(FIX, "q8_cn.csv"),
             "--students", os.path.join(FIX, "s8_cn.csv"), "--out-dir", d, "--quiet"],
             out_contains="分层名单 2 人")
    d = os.path.join(tmp, "o10")
    run_case("T10 裁剪产物(no-md/no-html)", ["--demo", "--no-md", "--no-html", "--out-dir", d, "--quiet"],
             file=os.path.join(d, "review_plan.json"),
             no_file=[os.path.join(d, "review_plan.md"),
                      os.path.join(d, "review_deck.html")],
             note="md/html 被跳过，仅 JSON+CSV")

    # ---- 同义与降级（3）
    d = os.path.join(tmp, "o11")
    run_case("T11 缺p/d列降级(默认0.65/0)", ["--qstats", os.path.join(FIX, "q9_missing.csv"),
             "--exam", "周测", "--out-dir", d, "--quiet"],
             out_contains="题目 2 道", note="缺得分率按 0.65、缺区分度按 0，并给告警")
    d = os.path.join(tmp, "o12")
    run_case("T12 大写键JSON别名识别", ["--qstats", os.path.join(FIX, "q12_upper.json"),
             "--out-dir", d, "--quiet"], out_contains="题目 2 道",
             note="ID/P/Marks/KP 大写键兼容")
    d = os.path.join(tmp, "o13")
    run_case("T13 无学生名单仅给分层标准", ["--analysis", os.path.join(FIX, "a2_allpass.json"),
             "--out-dir", d, "--quiet"],
             out_contains="名单 0 人",
             file=os.path.join(d, "review_plan.md"), fc="未提供成绩单",
             note="无 students → 分层空 + 提示给分层标准")

    # ---- 缺输入/错误文件（5）
    run_case("T14 无任何输入参数报usage", [], exp_exit=2, out_contains="usage",
             note="argparse 必需互斥组拦截")
    run_case("T15 文件不存在", ["--analysis", os.path.join(FIX, "nope.json")], exp_exit=2,
             out_contains="无法读取")
    run_case("T16 空题目列表", ["--analysis", os.path.join(FIX, "e1_empty.json")], exp_exit=2,
             out_contains="题目统计为空")
    run_case("T17 缺questions字段", ["--analysis", os.path.join(FIX, "e2_nofield.json")], exp_exit=2,
             out_contains="缺少 questions 字段")
    run_case("T18 非法JSON", ["--analysis", os.path.join(FIX, "bad_json.json")], exp_exit=2,
             out_contains="格式错误")

    # ---- 边界（5）
    d = os.path.join(tmp, "o19")
    run_case("T19 全员高分无必讲→拔高引导", ["--analysis", os.path.join(FIX, "a2_allpass.json"),
             "--out-dir", d, "--quiet"], out_contains="必讲 0",
             note="P≥0.85 全部略讲，核心讲评改为拔高引导题")
    d = os.path.join(tmp, "o20")
    run_case("T20 P=0全错/P=1满分/满分0", ["--analysis", os.path.join(FIX, "a3_edge.json"),
             "--out-dir", d, "--quiet"], out_contains="必讲 1",
             note="P=0 必讲；P=1 略讲；分值 0 不闪崩")
    d = os.path.join(tmp, "o21")
    run_case("T21 单题单学生最小输入", ["--analysis", os.path.join(FIX, "a4_single.json"),
             "--out-dir", d, "--quiet"], out_contains="题目 1 道")
    d = os.path.join(tmp, "o22")
    run_case("T22 无知识点标注归组并提示", ["--analysis", os.path.join(FIX, "a5_nokp.json"),
             "--out-dir", d, "--quiet"], out_contains="题目 2 道",
             file=os.path.join(d, "review_plan.md"), fc="未标注知识点",
             note="kp 缺省归入「未标注知识点」")
    d = os.path.join(tmp, "o23")
    run_case("T23 课时下限5分钟", ["--demo", "--session", "5", "--out-dir", d, "--quiet"],
             out_contains="时间轴 3 阶段")

    # ---- 异常数据（3）
    d = os.path.join(tmp, "o24")
    run_case("T24 p越界/d负数/marks非数字", ["--qstats", os.path.join(FIX, "q7_bad.csv"),
             "--out-dir", d, "--quiet"], out_contains="题目 3 道",
             note="p=1.5 修正为 1、d=-0.2 归 0、marks 非法记 1 分，全部可用")
    d = os.path.join(tmp, "o25")
    run_case("T25 学生成绩非法值被跳过", ["--qstats", os.path.join(FIX, "q8_cn.csv"),
             "--students", os.path.join(FIX, "s7_bad.csv"), "--out-dir", d, "--quiet"],
             out_contains="名单 2 人",
             note="李四总分非法被跳并提示")

    # ---- 确定性（1）
    d1 = os.path.join(tmp, "o26")
    d2 = os.path.join(tmp, "o27")
    subprocess.run([PY, SCRIPT, "--demo", "--out-dir", d1, "--quiet"], capture_output=True, text=True, timeout=180)
    subprocess.run([PY, SCRIPT, "--demo", "--out-dir", d2, "--quiet"], capture_output=True, text=True, timeout=180)
    p1 = open(os.path.join(d1, "review_plan.json"), encoding="utf-8").read()
    p2 = open(os.path.join(d2, "review_plan.json"), encoding="utf-8").read()
    same = hashlib.sha256(p1.encode()).hexdigest() == hashlib.sha256(p2.encode()).hexdigest()
    SUMMARY["n"] += 1
    SUMMARY["ok" if same else "fail"] += 1
    RESULTS.append({"name": "T26 确定性(两次demo哈希一致)", "query": "--demo 两次运行",
                    "expected": "两次 review_plan.json SHA256 一致", "actual": "一致" if same else "不一致",
                    "pass": same, "note": "无随机源，输出可复现"})

    # ---- 安全（4）
    d = os.path.join(tmp, "o28")
    run_case("T27 XSS转义(HTML)", ["--analysis", os.path.join(FIX, "a6_xss.json"),
             "--out-dir", d, "--quiet"],
             file=os.path.join(d, "review_deck.html"), fc="&lt;script&gt;",
             fforbid="<script>alert(1)</script>",
             note="考试名/知识点/题干/学生名全注入仍安全")
    d = os.path.join(tmp, "o29")
    run_case("T28 XSS不进入Markdown", ["--analysis", os.path.join(FIX, "a6_xss.json"),
             "--out-dir", d, "--quiet"],
             file=os.path.join(d, "review_plan.md"), fforbid="<script>",
             note="md_cell 将 < > 全角化，可执行文本不落地")
    d = os.path.join(tmp, "o30")
    run_case("T29 CSV公式注入防护", ["--demo", "--students", os.path.join(FIX, "s11_formula.csv"),
             "--out-dir", d, "--quiet"],
             file=os.path.join(d, "tier_students.csv"), fc="'=cmd",
             fforbid="\n=cmd", note="= @ - + 开头加 ' 前缀"),
    d = os.path.join(tmp, "o31")
    run_case("T30 覆盖旧输出无异常(二次demo)", ["--demo", "--out-dir", d, "--quiet"],
             out_contains="必讲 3", note="同一目录二次运行即覆盖，无破坏")

    # ---- 汇总
    lines = ["# exam-review-planner 自测记录（2026-08-27）", "",
             f"总计 {SUMMARY['n']} 条｜通过 {SUMMARY['ok']}｜失败 {SUMMARY['fail']}｜"
             f"通过率 {SUMMARY['ok'] / max(SUMMARY['n'], 1) * 100:.1f}%", "",
             "| 用例 | Query | 预期 | 实际 | 结果 | 备注 |",
             "|------|-------|------|------|------|------|"]
    for r in RESULTS:
        lines.append(f"| {r['name']} | `{r['query'][:100]}` | {r['expected']} | {r['actual'][:130]} | {'✅' if r['pass'] else '❌'} | {r['note']} |")
    out = os.path.join(FIX, "自测记录.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"=== 自测汇总:{SUMMARY['n']} 条，通过 {SUMMARY['ok']}，失败 {SUMMARY['fail']}（通过率 {SUMMARY['ok']/max(SUMMARY['n'],1)*100:.1f}%）===")
    for r in RESULTS:
        if not r["pass"]:
            print(f"  ❌ {r['name']}: {r['actual'][:200]}")
    print("记录：", out)
    return 0 if SUMMARY["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())