#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 run_self_test.sh 所需的测试夹具（fixtures）。运行: python3 make_fixtures.py <输出目录>"""
import csv
import json
import os
import sys

OUT = sys.argv[1] if len(sys.argv) > 1 else "."

META_GOOD = {
    "exam": "2026年秋 Python 期中考试（模拟）", "course": "Python 程序设计基础",
    "date": "2026-08-26", "total_marks": 100, "className": "计科2401班",
    "questions": [
        {"id": "1", "marks": 8, "kp": "基础语法", "type": "单选", "difficulty": "易"},
        {"id": "2", "marks": 8, "kp": "基础语法", "type": "单选", "difficulty": "易"},
        {"id": "3", "marks": 10, "kp": "流程控制", "type": "单选", "difficulty": "中"},
        {"id": "4", "marks": 10, "kp": "流程控制", "type": "填空", "difficulty": "中"},
        {"id": "5", "marks": 15, "kp": "函数与模块", "type": "简答", "difficulty": "中"},
        {"id": "6", "marks": 15, "kp": "文件处理", "type": "简答", "difficulty": "难"},
        {"id": "7", "marks": 17, "kp": "综合应用", "type": "综合", "difficulty": "难"},
        {"id": "8", "marks": 17, "kp": "综合应用", "type": "综合", "difficulty": "难"},
    ],
}

STU = [  # 8 名学生（含边角）
    ("S001", "张伟", "计科2401班", ["8", "8", "10", "8", "12", "10", "14", "12"]),
    ("S002", "李娜", "计科2401班", ["6", "8", "8", "4", "8", "2", "6", "4"]),
    ("S003", "王强", "计科2401班", ["8", "8", "6", "4", "4", "4", "2", "4"]),
    ("S004", "赵敏", "计科2401班", ["8", "8", "10", "10", "13", "11", "15", "15"]),
    ("S005", "钱伟", "计科2401班", ["6", "4", "4", "2", "3", "2", "2", "0"]),
    ("S006", "孙静", "计科2401班", ["6", "8", "8", "4", "4", "2", "4", "8"]),
    ("S007", "周涛", "计科2401班", ["8", "8", "10", "8", "12", "8", "12", "10"]),
    ("S008", "吴丹", "计科2401班", ["6", "6", "4", "6", "5", "2", "3", "5"]),
]
HEAD_Q = ["student_id", "name", "class"] + [f"Q{i}" for i in range(1, 9)]


def wcsv(name, rows, header=None):
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        if header:
            w.writerow(header)
        w.writerows(rows)
    return path


# 常规班（8 人）
s_normal = [[sid, nm, cl, *sc] for sid, nm, cl, sc in STU]
wcsv("s_normal.csv", s_normal, HEAD_Q)

# 中文列名
wcsv("csv_cn.csv", [[nm, sid, cl, *sc] for sid, nm, cl, sc in STU],
     ["姓名", "学号", "班级"] + [f"Q{i}" for i in range(1, 9)])

# 题列 t1..t8
wcsv("csv_t.csv", [[sid, nm, cl, *sc] for sid, nm, cl, sc in STU],
     ["student_id", "name", "class"] + [f"t{i}" for i in range(1, 9)])

# 题列 题目1..题目8
wcsv("csv_cnq.csv", [[sid, nm, cl, *sc] for sid, nm, cl, sc in STU],
     ["学号", "姓名", "班级"] + [f"题目{i}" for i in range(1, 9)])

# 含非数字单元格
r = [[sid, nm, cl, *sc] for sid, nm, cl, sc in STU]
r[2][3] = "abc"
wcsv("bad_cell.csv", r, HEAD_Q)

# 含超出满分单元格
r2 = [[sid, nm, cl, *sc] for sid, nm, cl, sc in STU]
r2[0][3 + 0] = "99"  # S001 第1题 99 分 > 8 分
wcsv("over_cell.csv", r2, HEAD_Q)

# 包含 XSS 的学生姓名
r3 = [[sid, nm, cl, *sc] for sid, nm, cl, sc in STU]
r3[0][1] = '<script>alert(1)</script>'
wcsv("csv_xss.csv", r3, HEAD_Q)

# 公式注入学生姓名
r4 = [[sid, nm, cl, *sc] for sid, nm, cl, sc in STU]
r4[0][1] = '=SUM(A1)+1'
wcsv("csv_formula.csv", r4, HEAD_Q)

META_XSS = dict(META_GOOD)
META_XSS["exam"] = '<script>alert(1)</script>期中考试'
with open(os.path.join(OUT, "meta_xss.json"), "w", encoding="utf-8") as f:
    json.dump(META_XSS, f, ensure_ascii=False)

# 缺考: 整行留空
wcsv("all_absent.csv", [["S001", "张伟", "计科2401班", "", "", "", "", "", "", "", ""],
                        ["S002", "李娜", "计科2401班", "", "", "", "", "", "", "", ""]],
     HEAD_Q)

# 单个学生
wcsv("one_student.csv", [[sid, nm, cl, *sc] for sid, nm, cl, sc in STU[:1]], HEAD_Q)

# 全满分
full = [["S0%02d" % i, f"同学{i:02d}", "一班"] + ["8", "8", "10", "10", "15", "15", "17", "17"]
        for i in range(1, 7)]
wcsv("all_full.csv", full, HEAD_Q)

# 空表头
open(os.path.join(OUT, "empty_header.csv"), "w", encoding="utf-8").close()

# 错误 meta（合集不匹配）
META_MIS = dict(META_GOOD)
META_MIS["total_marks"] = 90
with open(os.path.join(OUT, "mismatch_meta.json"), "w", encoding="utf-8") as f:
    json.dump(META_MIS, f, ensure_ascii=False)

open(os.path.join(OUT, "empty_q_meta.json"), "w", encoding="utf-8").write(
    json.dumps({"exam": "x", "total_marks": 100, "questions": []}))
open(os.path.join(OUT, "bad_json.json"), "w", encoding="utf-8").write("{not json")

# copy_meta.json + copy.csv（与主体相同，用于可复现比对）
with open(os.path.join(OUT, "copy_meta.json"), "w", encoding="utf-8") as f:
    json.dump(META_GOOD, f, ensure_ascii=False)
wcsv("copy.csv", [[sid, nm, cl, *sc] for sid, nm, cl, sc in STU], HEAD_Q)

# 常规班副本（s_normal）
wcsv("s_normal.csv", [[sid, nm, cl, *sc] for sid, nm, cl, sc in STU], HEAD_Q)
print("fixtures done ->", OUT)