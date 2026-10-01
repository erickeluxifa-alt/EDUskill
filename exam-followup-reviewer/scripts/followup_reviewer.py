#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
exam-followup-reviewer —— 考后教学复盘助手 v1.0.0
================================================
输入：exam-score-analyzer 输出的 analysis.json
      （1 份 = 单班复盘；多份 = 班级横评 + 共性/班型差异/命题信号归因）
输出：
  followup_review.md    复盘报告（Markdown）
  followup_report.html  自包含可视化报告（零外部依赖、移动自适应、可打印）
  class_compare.csv     班级横向对比（Excel 直开）
  kp_matrix.csv         知识点掌握度矩阵（班级 x 知识点）
  help_list.csv         学生帮扶名单（预警/尾部学生 + 建议动作）
  blueprint_feedback.json  命题回流建议（供 exam-blueprint-generator 下一轮命题使用）

安全边界：纯标准库、零第三方依赖、无网络/无 shell 调用；
HTML 输出转义用户文本；CSV 对 = + - @ 开头单元格加引号防公式注入；结果确定性。
"""
import argparse
import csv
import json
import os
import re
import sys
import datetime

VERSION = "1.0.0"
AUTHOR = "ht"
TODAY = datetime.date.today().isoformat()


class RevErr(Exception):
    """输入错误（退出码 2）"""


# ---------------- 安全与工具 ----------------
def esc(s):
    """HTML 转义 + 截断，防 XSS。"""
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))[:300]


def strip_ctrl(s):
    if s is None:
        return ""
    return re.sub(r"[\x00-\x1f\x7f]", "", str(s))


def csv_safe(v):
    """防公式注入：以 =/+/−/@/tab 开头时前置单引号。"""
    s = str(v).strip()
    if s and s[0] in ("=", "+", "-", "@", "\t"):
        return "'" + s
    return s


def r2(x):
    try:
        return round(float(x), 2)
    except (TypeError, ValueError):
        return None


def pct(x):
    """0~1 → 0~100 一位小数。"""
    try:
        return round(float(x) * 100, 1)
    except (TypeError, ValueError):
        return None


def band_p(p):
    if p is None:
        return "数据不足"
    if p >= 0.80:
        return "已掌握"
    if p >= 0.60:
        return "掌握一般"
    if p >= 0.40:
        return "薄弱"
    return "严重薄弱"


def band_final(s):
    if s is None:
        return "数据不足"
    if s >= 0.85:
        return "优秀"
    if s >= 0.72:
        return "良好"
    if s >= 0.60:
        return "中等"
    if s >= 0.48:
        return "待提升"
    return "需重点改进"


# ---------------- 数据装载 ----------------
def load_analysis(path):
    if not os.path.isfile(path):
        raise RevErr("找不到分析文件: %s" % path)
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            d = json.load(f)
    except json.JSONDecodeError as e:
        raise RevErr("JSON 解析失败（%s）: %s" % (path, e))
    if not isinstance(d, dict):
        raise RevErr("输入必须是 JSON 对象（exam-score-analyzer 的 analysis.json）: %s" % path)
    meta = d.get("meta") or {}
    if not isinstance(meta, dict) or not isinstance(meta.get("questions"), list) or not meta["questions"]:
        raise RevErr("缺少 meta.questions，请使用 exam-score-analyzer 输出的 analysis.json: %s" % path)
    totals = d.get("totals") or {}
    if not isinstance(totals, dict):
        raise RevErr("totals 缺失或非法: %s" % path)
    return {
        "path": path,
        "meta": meta,
        "totals": totals,
        "questions": meta["questions"],
        "students": d.get("students") or [],
        "absent": d.get("absent_list") or [],
        "alpha": d.get("alpha"),
        "warns": d.get("warns") or [],
        "dist": totals.get("dist") or [],
    }


def t(rec, key, default=None):
    v = rec["totals"].get(key)
    return default if v is None else v


# ---------------- 班级画像 ----------------
def class_profile(rec):
    total = float(t(rec, "total_marks") or 100)
    mean = t(rec, "mean")
    pr = t(rec, "pass_rate")
    er = t(rec, "excel_rate")
    lr = t(rec, "low_rate")
    po = t(rec, "p_overall")
    if pr is None and mean is not None:
        pr = float(mean) / total
    if po is None and mean is not None:
        po = float(mean) / total
    if er is None:
        er = 0.0
    if lr is None:
        lr = 0.0
    s = 0.5 * (po or 0) + 0.3 * (pr or 0) + 0.2 * (1 - (lr or 0))
    return {
        "class_name": strip_ctrl(rec["meta"].get("class_name") or rec["meta"].get("className") or "未命名班级"),
        "course": strip_ctrl(rec["meta"].get("course") or ""),
        "exam": strip_ctrl(rec["meta"].get("exam") or ""),
        "date": strip_ctrl(rec["meta"].get("date") or ""),
        "total": total,
        "n": t(rec, "n_present"),
        "n_total": t(rec, "n_total"),
        "mean": r2(mean), "sd": r2(t(rec, "sd")), "median": r2(t(rec, "median")),
        "max": r2(t(rec, "max")), "min": r2(t(rec, "min")),
        "pass": pct(pr), "excel": pct(er), "low": pct(lr), "p_overall": pct(po),
        "alpha": r2(rec["alpha"]),
        "score": r2(s), "band": band_final(s),
        "absent_n": len(rec["absent"]),
        "dist": rec["dist"],
    }


# ---------------- 知识点聚合 ----------------
def kp_rows(rec):
    """按知识点聚合得分率（利用每题 mean/满分/实考人数）。"""
    acc = {}
    n_present = t(rec, "n_present") or 0
    for q in rec["questions"]:
        kp = strip_ctrl(q.get("kp") or "未分类").strip() or "未分类"
        acc.setdefault(kp, [0.0, 0.0])
        marks = float(q.get("marks") or 0)
        n = int(q.get("n") or n_present or 0)
        n = max(n, 1)
        acc[kp][0] += float(q.get("mean") or 0) * n
        acc[kp][1] += marks * n
    out = []
    for kp, (earned, mx) in acc.items():
        p = earned / mx if mx else 0.0
        out.append({"kp": kp, "p": r2(p), "pct": pct(p), "band": band_p(p)})
    out.sort(key=lambda r: r["p"] or 0)
    return out


# ---------------- 题目四象限 ----------------
def question_quads(rec):
    out = []
    for q in rec["questions"]:
        p = q.get("p")
        d = q.get("d")
        p = float(p) if p is not None else None
        d = float(d) if d is not None else None
        quad = "正常"
        if p is not None and d is not None:
            if p < 0.5 and d < 0.2:
                quad = "双低·疑议题"
            elif p < 0.5 and d >= 0.3:
                quad = "高区分·拉分题"
            elif p >= 0.8 and d < 0.2:
                quad = "送分·低效题"
        out.append({
            "id": strip_ctrl(q.get("id") or ""),
            "kp": strip_ctrl(q.get("kp") or "未分类"),
            "p": r2(p) if p is not None else None,
            "d": r2(d) if d is not None else None,
            "quad": quad,
        })
    return out


# ---------------- 帮扶名单 ----------------
def help_rows(rec):
    """帮扶名单：尾部 25% 或带预警标识的学生。"""
    st = rec["students"]
    if not st:
        return []
    scored = []
    for s in st:
        total = s.get("total")
        if isinstance(total, (int, float)):
            scored.append((s, float(total)))
    scored.sort(key=lambda x: x[1], reverse=True)
    n_all = len(scored)
    out = []
    for idx, (s, total) in enumerate(scored):
        pos = (idx + 1) / n_all if n_all else 1.0  # 名次位置：0~1，越小越靠前
        flags = []
        if pos > 0.75:
            flags.append("尾部25%")
        tier = s.get("tier") or ""
        if tier:
            flags.append(strip_ctrl(tier))
        pct_p = s.get("pct")
        if isinstance(pct_p, (int, float)) and pct_p <= 25:
            flags.append("百分位低")
        if flags:
            out.append({
                "class": strip_ctrl(s.get("class") or ""),
                "sid": strip_ctrl(s.get("sid") or s.get("id") or ""),
                "name": strip_ctrl(s.get("name") or ""),
                "total": r2(total),
                # 超越率：成绩好于的同学比例，值越大水平越高
                "percentile": round((n_all - 1 - idx) * 100 / n_all, 1),
                "flags": "、".join(dict.fromkeys(flags)),
            })
    out.sort(key=lambda h: (h["class"], -(h["total"] or 0)))
    return out


# ---------------- 复盘汇总 ----------------
def build_review(recs):
    """由多份 analysis 构建复盘数据（单班或横评），返回结构化结果。"""
    profs = [class_profile(r) for r in recs]
    kps = [kp_rows(r) for r in recs]
    quads = [question_quads(r) for r in recs]
    helps = [help_rows(r) for r in recs]

    # 知识点合并：平均 + 共性（>=2 班薄弱视为共性）
    kp_names = set()
    for rows in kps:
        for k in rows:
            kp_names.add(k["kp"])
    kp_matrix = {p["class_name"]: {k2["kp"]: k2 for k2 in rows}
                 for p, rows in zip(profs, kps)}
    merged = []
    for name in sorted(kp_names):
        ps = [kp_matrix[c].get(name) for c in kp_matrix]
        ps = [x for x in ps if x is not None]
        if not ps:
            continue
        avg = sum(x["p"] for x in ps) / len(ps)
        merged.append({
            "kp": name,
            "p": r2(avg),
            "pct": pct(avg),
            "band": band_p(avg),
            "common": sum(1 for x in ps if x["p"] < 0.6) >= 2,
        })
    merged.sort(key=lambda k: k["p"] or 0)

    # 命题反馈（回流蓝图）
    fb = []
    for k in merged:
        act, note = "维持", ""
        if k["p"] is not None:
            if k["p"] < 0.4:
                act, note = "下调难度", "得分率过低，建议降档为达标题或以多问拆分"
            elif k["p"] < 0.6:
                act, note = "控制难度", "得分率偏低，题目设计降低门槛或调整权重"
            elif k["p"] >= 0.8:
                act, note = "可加码", "得分率偏高，可提高难度或增加权重以提升区分度"
        fb.append({"kp": k["kp"], "p": k["pct"], "band": k["band"],
                   "suggest": act, "note": note})

    q_review = []
    for rec_i, qg in enumerate(quads):
        for q in qg:
            if q["quad"] in ("双低·疑议题", "高区分·拉分题"):
                row = dict(q)
                row["class"] = profs[rec_i]["class_name"]
                q_review.append(row)
    return profs, kps, quads, helps, merged, fb, q_review, kp_matrix


# ---------------- Markdown 报告 ----------------
def md_table(head, rows):
    sep = "|" + "|".join(["---"] * len(head)) + "|"
    body = ["|" + "|".join(head) + "|", sep]
    for r in rows:
        body.append("|" + "|".join(r) + "|")
    return "\n".join(body)


def render_md(recs, profs, kps, merged, quads, helps):
    L = []
    exam = profs[0]["exam"] or "考试"
    course = profs[0]["course"] or ""
    L.append("# 考后教学复盘报告\n")
    L.append("- 考试：%s" % esc(exam))
    L.append("- 课程：%s" % esc(course))
    L.append("- 纳入班级：%d 个（%s）" % (len(profs), "、".join(esc(p["class_name"]) for p in profs)))
    L.append("- 生成时间：%s ｜ 工具：exam-followup-reviewer v%s（作者 %s）" % (TODAY, VERSION, AUTHOR))
    L.append("")

    L.append("## 一、班级整体画像")
    rows = []
    for p in profs:
        rows.append([p["class_name"], str(p["n"]), str(p["mean"]), str(p["pass"]) + "%",
                     str(p["excel"]) + "%", str(p["low"]) + "%", str(p["p_overall"]) + "%",
                     p["band"]])
    L.append(build_table(["班级", "人数", "均分", "及格率", "优秀率", "低分率", "得分率", "画像"], rows))
    L.append("")
    for p in profs:
        tips = []
        if p["band"] in ("优秀", "良好"):
            tips.append("整体表现 %s，建议维持当前教学节奏，关注尖子生拓展。" % p["band"])
        elif p["band"] == "中等":
            tips.append("整体中等，及格率 %s%，最后 15%% 学生是提升空间最大的群体。" % p["pass"])
        else:
            tips.append("整体 %s（综合画像 %s 分），需优先攻克核心薄弱知识点，再谈难题突破。" % (
                p["band"], p["score"]))
        if p["alpha"] is not None and p["alpha"] < 0.7:
            tips.append("整卷信度 α=%s 偏低，建议复核题目质量（见命题回流建议）。" % p["alpha"])
        L.append("- **%s**：%s" % (esc(p["class_name"]), " ".join(tips)))
    L.append("")

    L.append("## 二、知识点掌握度与改进建议")
    if merged:
        rows = []
        for k in merged:
            rows.append([k["kp"], str(k["pct"]) + "%", k["band"],
                         "共性薄弱" if k["common"] else "班内情况"])
        L.append(build_table(["知识点", "平均得分率", "掌握度", "归因"], rows))
        L.append("")
        weak = [k for k in merged if k["p"] is not None and k["p"] < 0.6]
        if weak:
            L.append("**改进建议（按优先级）：**")
            for k in weak[:6]:
                if k["band"] == "严重薄弱":
                    act = "先从基础概念重讲（10 分钟回看 + 同源基础题 2 道），再安排变式作业"
                else:
                    act = "安排 1 次 15 分钟专项复习：概念梳理 + 限时训练 + 当堂对答案"
                L.append("- %s（%.1f%%）：%s。" % (k["kp"], k["pct"], act))
        else:
            L.append("本次考试各知识点整体掌握良好，未见低于 60% 的薄弱点。")
    else:
        L.append("（无知识点数据）")
    L.append("")

    L.append("## 三、命题质量与回流建议")
    q_rows = []
    for ci, g in enumerate(quads):
        for q in g:
            if q["quad"] != "正常":
                q_rows.append((profs[ci]["class_name"], q))
    if q_rows:
        L.append(build_table(["班级", "题号", "知识点", "得分率", "区分度", "判定"],
                             [[cv(c), cv(q["id"]), cv(q["kp"]),
                               (str(pct(q["p"])) + "%") if q["p"] is not None else "-",
                               str(q["d"]) if q["d"] is not None else "-", cv(q["quad"])]
                              for c, q in q_rows]))
        L.append("")
        L.append("""
- 双低·疑议题：得分率与区分度双低，常见原因是题目歧义、超纲或讲解未覆盖，建议备课组复核并修正题库；
- 高区分·拉分题：区分度好但得分率低，是「提分杠杆」，建议在复习中作为重点变式素材；
- 送分·低效题：得分率很高且区分度低，对区分贡献有限，下一轮可考虑替换或降权。
- 完整回流建议见输出 `blueprint_feedback.json`，可直接供 exam-blueprint-generator 下一轮命题参考。
""")
    else:
        L.append("本卷未出现需要干预的问题题（所有题目区分度正常）。")
    L.append("")

    L.append("## 四、学生帮扶清单")
    total_help = sum(len(h) for h in helps)
    if total_help:
        for p, rows_ in zip(profs, helps):
            if not rows_:
                continue
            L.append("### %s（%d 人）" % (esc(p["class_name"]), len(rows_)))
            L.append(build_table(["学号", "姓名", "总分", "百分位", "标记"],
                                 [[csv_safe(h["sid"]), cv(h["name"]), str(h["total"]),
                                   str(h["percentile"]) + "%", cv(h["flags"])] for h in rows_]))
            L.append("")
        L.append("**帮扶建议：**按标记红黄分级，优先关注「尾部」学生，每人每周 1 次过关练习，与家长同步一次情况。")
    else:
        L.append("analysis.students 未提供学生明细（或无人落在帮扶区间），可先用 exam-score-analyzer 生成 students.csv 后重跑。")
    L.append("")

    L.append("---")
    L.append("说明：本报告由规则模板生成，用于辅助教学决策，不替代教师专业判断。")
    L.append("")
    return "\n".join(L)


def cv(s):
    """Markdown 表格单元格清洗：控制字符/竖线 + HTML 实体转义（防注入）。"""
    s = strip_ctrl(str(s))
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("|", "\\|"))


def build_table(headers, rows):
    sep = "|" + "|".join(["---"] * len(headers)) + "|"
    body = ["|" + "|".join(cv(h) for h in headers) + "|", sep]
    for r in rows:
        body.append("|" + "|".join(cv(c) for c in r) + "|")
    return "\n".join(body)


# ---------------- HTML 渲染（委托独立模块） ----------------
def render_html(recs, profs, kps, merged, quads, helps, q_review):
    try:
        from html_render import render_report
        return render_report(recs, profs, kps, merged, quads, helps, q_review)
    except ImportError:
        here = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, here)
        from html_render import render_report
        return render_report(recs, profs, kps, merged, quads, helps, q_review)


# ---------------- main ----------------
def main():
    ap = argparse.ArgumentParser(description="考后教学复盘助手（exam-followup-reviewer v%s）" % VERSION)
    ap.add_argument("--analysis", action="append", dest="analyses",
                    help="analysis.json 路径（可重复传多份做班级横评）")
    ap.add_argument("--dir", help="扫描目录下所有 *analysis*.json（跳过 demo_output）")
    ap.add_argument("--demo", action="store_true", help="使用内置示例数据（两班横评）")
    ap.add_argument("--out-dir", default="output", help="输出目录（默认 output/）")
    ap.add_argument("--no-html", action="store_true", help="跳过 HTML 报告")
    ap.add_argument("--no-md", action="store_true", help="跳过 Markdown 报告")
    ap.add_argument("--quiet", action="store_true", help="减少控制台输出")
    args = ap.parse_args()

    try:
        recs = []
        if args.demo:
            here = os.path.dirname(os.path.abspath(__file__))
            for name in ("classA_analysis.json", "classB_analysis.json"):
                p = os.path.join(here, "..", "examples", name)
                recs.append(load_analysis(p))
        elif args.analyses:
            for p in args.analyses:
                recs.append(load_analysis(p))
        elif args.dir:
            if not os.path.isdir(args.dir):
                raise RevErr("目录不存在: %s" % args.dir)
            found = []
            for root, _, files in os.walk(args.dir):
                if "demo_output" in root or "__MACOSX" in root or ".git" in root:
                    continue
                for fn in files:
                    if fn.endswith(".json") and "analysis" in fn.lower():
                        found.append(os.path.join(root, fn))
            found.sort()
            if not found:
                raise RevErr("目录中未找到 *analysis*.json: %s" % args.dir)
            recs = [load_analysis(p) for p in found]
        else:
            ap.print_help()
            raise SystemExit(2)
        if not recs:
            raise RevErr("未提供任何 analysis.json（请用 --analysis / --dir / --demo）")
    except RevErr as e:
        print("[复盘助手] 输入错误: %s" % e, file=sys.stderr)
        sys.exit(2)
    except SystemExit:
        raise

    profs, kps, quads, helps, merged, fb, q_review, kp_matrix = build_review(recs)
    os.makedirs(args.out_dir, exist_ok=True)
    written = []

    if not args.no_md:
        with open(os.path.join(args.out_dir, "followup_review.md"), "w", encoding="utf-8") as f:
            f.write(render_md(recs, profs, kps, merged, quads, helps))
        written.append("followup_review.md")

    if not args.no_html:
        with open(os.path.join(args.out_dir, "followup_report.html"), "w", encoding="utf-8") as f:
            f.write(render_html(recs, profs, kps, merged, quads, helps, q_review))
        written.append("followup_report.html")

    with open(os.path.join(args.out_dir, "class_compare.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["班级", "参考人数", "均分", "及格率%", "优秀率%", "低分率%", "得分率%", "综合分", "画像"])
        for p in profs:
            w.writerow([csv_safe(p["class_name"]), p["n"], p["mean"], p["pass"], p["excel"],
                        p["low"], p["p_overall"], p["score"], csv_safe(p["band"])])
    written.append("class_compare.csv")

    with open(os.path.join(args.out_dir, "kp_matrix.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        head = ["知识点", "平均得分率%", "掌握度"] + [p["class_name"] for p in profs]
        w.writerow([csv_safe(h) for h in head])
        for k in merged:
            row = [csv_safe(k["kp"]), k["pct"], k["band"]] + [
                pct(kp_matrix[p["class_name"]].get(k["kp"], {}).get("p")) for p in profs]
            w.writerow([csv_safe(x) for x in row])
    written.append("kp_matrix.csv")

    with open(os.path.join(args.out_dir, "help_list.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["班级", "学号", "姓名", "总分", "百分位%", "标记"])
        for h in helps:
            for r in h:
                w.writerow([csv_safe(r["class"]), csv_safe(r["sid"]), csv_safe(r["name"]),
                            r["total"], r["percentile"], csv_safe(r["flags"])])
    written.append("help_list.csv")

    blueprint = {
        "generated_by": "exam-followup-reviewer v%s" % VERSION,
        "generated_at": TODAY,
        "exam": recs[0]["meta"].get("exam") or "",
        "course": recs[0]["meta"].get("course") or "",
        "kp_feedback": fb,
        "question_review": q_review,
        "note": ("回流建议供 exam-blueprint-generator 下一轮命题参考：难度与权重调整为建议值，"
                 "请结合学科目标与教研组意见人工裁决。"),
    }
    with open(os.path.join(args.out_dir, "blueprint_feedback.json"), "w", encoding="utf-8") as f:
        json.dump(blueprint, f, ensure_ascii=False, indent=2)
    written.append("blueprint_feedback.json")

    summary = {
        "version": VERSION, "generated_at": TODAY,
        "classes": profs, "kp_overview": merged, "question_review": q_review,
        "help_by_class": [{"class": p["class_name"], "count": len(h), "rows": h}
                          for p, h in zip(profs, helps)],
        "blueprint_feedback": blueprint,
    }
    with open(os.path.join(args.out_dir, "followup_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    written.append("followup_summary.json")

    if not args.quiet:
        print("[复盘助手] 完成：%d 个班级，输出 %d 个文件 → %s/" % (len(profs), len(written), args.out_dir))
        for w_ in written:
            print("  ✓ %s" % w_)
    sys.exit(0)


if __name__ == "__main__":
    main()