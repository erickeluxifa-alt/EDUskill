#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 exam-followup-reviewer 的示例数据（与 exam-score-analyzer 输出格式一致）。"""

import json
import os

OUT = os.path.dirname(os.path.abspath(__file__))


def mk_students(prefix, cls, pairs):
    return [{"name": nm, "sid": "%s%02d" % (prefix, 100 + i + 1), "class": cls,
             "total": tt, "pct": pc, "tier": tr}
            for i, (nm, tt, pc, tr) in enumerate(pairs)]


def build(cls, exam, per_q, totals_d, students, absent_lst=None):
    n = int(totals_d.get("n_present", 0))
    absent_lst = absent_lst or []

    def q(id_, kp, tp, marks, diff, mean, d):
        return {"id": id_, "marks": marks, "kp": kp, "type": tp, "difficulty": diff,
                "n": n, "mean": round(mean, 2), "p": round(mean / marks, 4),
                "full_rate": round(0.55 if diff == "易" else (0.28 if diff == "中" else 0.12), 3),
                "d": d}

    questions = [
        q("1", "基础语法", "单选", 8, "易", per_q["q1"], 0.25),
        q("2", "基础语法", "单选", 8, "易", per_q["q2"], 0.18),
        q("3", "流程控制", "单选", 10, "中", per_q["q3"], 0.32),
        q("4", "流程控制", "填空", 10, "中", per_q["q4"], 0.30),
        q("5", "函数与模块", "简答", 15, "中", per_q["q5"], 0.42),
        q("6", "文件处理", "简答", 15, "难", per_q["q6"], 0.38),
        q("7", "综合应用", "综合", 17, "难", per_q["q7"], 0.15),
        q("8", "综合应用", "综合", 17, "难", per_q["q8"], 0.12),
    ]
    totals = dict(totals_d)
    totals["n_present"] = n
    totals.setdefault("alpha", None)
    return {"meta": {"exam": exam, "course": "Python 程序设计基础", "date": "2026-08-26",
                     "total_marks": 100, "class_name": cls, "className": cls,
                     "pass_rate": 0.60, "excellent_rate": 0.85, "low_rate": 0.30,
                     "group_fraction": 0.27, "questions": questions,
                     "kps": ["基础语法", "流程控制", "函数与模块", "文件处理", "综合应用"],
                     "sum_marks": 100.0, "version": "1.0.0"},
            "n_total": n + len(absent_lst), "n_present": n, "n_absent": len(absent_lst),
            "absent_list": absent_lst, "totals": totals, "students": students,
            "alpha": totals["alpha"], "warns": []}


def mk_dist(labels, counts, denom):
    return [{"label": l, "count": c, "ratio": round(c / denom, 3)}
            for l, c in zip(labels, counts)]


def main():
    labels = ["0~10", "10~20", "20~30", "30~40", "40~50", "50~60",
              "60~70", "70~80", "80~90", "90~100"]

    # ---- 班级 A：计科2401（整体中等，函数/文件薄弱）----
    perA = {"q1": 7.44, "q2": 7.60, "q3": 7.50, "q4": 7.20, "q5": 8.25, "q6": 7.50, "q7": 10.03, "q8": 9.69}
    tA = {"mean": 68.8, "sd": 12.6, "median": 70.0, "mode": 72.0, "max": 96.0, "min": 34.0,
          "n_pass": 17, "n_excl": 0, "n_low": 0, "pass_rate": 0.64, "excel_rate": 0.21,
          "low_rate": 0.04, "p_overall": 0.71, "n_present": 24, "alpha": 0.81,
          "dist": mk_dist(labels, [0, 0, 0, 1, 3, 5, 6, 5, 3, 1], 24)}
    stA = mk_students("201", "计科2401", [
        ("王雅静", 96, 100, ""), ("李梓睿", 91, 95, ""), ("张明宇", 86, 90, ""), ("陈思彤", 82, 84, ""),
        ("赵天乐", 78, 76, ""), ("刘俊豪", 75, 68, ""), ("孙雨欣", 72, 62, ""), ("周浩宇", 69, 57, ""),
        ("吴梓萌", 67, 52, ""), ("郑一鸣", 65, 45, ""), ("冯嘉豪", 63, 38, ""), ("蒋晓桐", 61, 32, ""),
        ("孙亦可", 59, 26, "尾部"), ("吴振宇", 55, 19, "尾部"), ("朱雨晨", 51, 12, "预警"),
        ("沈皓轩", 48, 6, "预警"), ("韩佳怡", 42, 3, "高危"), ("顾一凡", 37, 1, "高危"), ("钱文博", 34, 0, "高危")])
    docA = build("计科2401", "Python 程序设计 期中考试（模拟）", perA, tA, stA)
    with open(os.path.join(OUT, "classA_analysis.json"), "w", encoding="utf-8") as f:
        json.dump(docA, f, ensure_ascii=False, indent=1)

    # ---- 班级 B：计科2402（整体偏弱，函数/文件/综合弱）----
    perB = {"q1": 6.40, "q2": 6.40, "q3": 7.00, "q4": 6.40, "q5": 7.50, "q6": 6.30, "q7": 7.00, "q8": 6.50}
    tB = {
        "mean": 53.1, "sd": 21.6, "median": 52.5, "mode": 48.0, "max": 88.0, "min": 22.0,
        "n_pass": 9, "n_excl": 0, "n_low": 0, "pass_rate": 0.41, "excel_rate": 0.09,
        "low_rate": 0.0, "p_overall": 0.53, "n_present": 24, "alpha": 0.78,
        "dist": mk_dist(labels, [0, 0, 0, 2, 6, 6, 4, 3, 2, 1], 24)}
    stB = mk_students("202", "计科2402", [
        ("高俊宇", 88, 100, ""), ("罗欣然", 82, 94, ""), ("谢光旭", 75, 88, ""), ("许乐怡", 70, 81, ""),
        ("何睿哲", 66, 73, ""), ("林柳青", 63, 65, ""), ("马腾飞", 60, 59, ""), ("郑雅雯", 58, 53, ""),
        ("侯志恒", 56, 46, ""), ("田静姝", 54, 39, ""), ("彭劲松", 52, 33, ""), ("秦雨菲", 49, 26, "尾部"),
        ("袁熙晨", 46, 18, "尾部"), ("任雪琪", 43, 11, "预警"), ("曹俊杰", 40, 7, "预警"),
        ("石家铭", 36, 2, "高危"), ("魏安琪", 33, 1, "高危"), ("陆嘉欣", 28, 0, "高危"), ("胡志远", 22, 0, "高危")])
    docB = build("计科2402班", "Python 程序设计 期中考试（2402班模拟）", perB, tB, stB)
    with open(os.path.join(OUT, "classB_analysis.json"), "w", encoding="utf-8") as f:
        json.dump(docB, f, ensure_ascii=False, indent=1)

    print("examples written:", os.listdir(OUT))


if __name__ == "__main__":
    main()