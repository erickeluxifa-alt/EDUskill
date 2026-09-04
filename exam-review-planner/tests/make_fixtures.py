#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 exam-review-planner 自测夹具（约定：与测试脚本同目录使用）。"""
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def w(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def wcsv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(header)
        for r in rows:
            wr.writerow(r)


def make_analysis(path, questions, students=None, meta=None):
    data = {"meta": {
        "exam": "初二数学月考", "course": "数学", "class_name": "初二(3)班",
        "date": "2026-08-25", "total_marks": 100, "pass_rate": 0.6,
        "excellent_rate": 0.85, "low_rate": 0.3, "version": "1.0.0",
        **(meta or {})},
        "questions": questions, "students": students or []}
    w(path, json.dumps(data, ensure_ascii=False, indent=2))


def main():
    here = HERE
    # 1) 标准 analysis.json（8题P分层分布 + 学生21人，同 demo 同构）
    make_analysis(
        os.path.join(here, "a1_std.json"),
        [
            {"id": "1", "marks": 8, "kp": "基础语法", "type": "单选", "p": 0.83, "d": 0.25},
            {"id": "2", "marks": 8, "kp": "基础语法", "type": "单选", "p": 0.90, "d": 0.25},
            {"id": "3", "marks": 10, "kp": "流程控制", "type": "单选", "p": 0.78, "d": 0.19},
            {"id": "4", "marks": 10, "kp": "流程控制", "type": "填空", "p": 0.67, "d": 0.27},
            {"id": "5", "marks": 15, "kp": "函数与模块", "type": "编程", "p": 0.54, "d": 0.31},
            {"id": "6", "marks": 15, "kp": "文件处理", "type": "编程", "p": 0.46, "d": 0.33},
            {"id": "7", "marks": 16, "kp": "综合应用", "type": "综合", "p": 0.40, "d": 0.37},
            {"id": "8", "marks": 20, "kp": "综合应用", "type": "综合", "p": 0.42, "d": 0.12,
             "text": "带示例文本的综合题"}],
        [{"sid": "S001", "name": "陈晨", "class": "初二3", "total": 88},
         {"sid": "S002", "name": "王强", "class": "初二3", "total": 60},
         {"sid": "S003", "name": "李娜", "class": "初二3", "total": 20}])

    # 2) 全员高分层（P 全 ≥0.85 → 无必讲/应讲 → 拔高引导）
    make_analysis(
        os.path.join(here, "a2_allpass.json"),
        [{"id": "1", "marks": 10, "kp": "概念", "p": 0.95, "d": 0.1},
         {"id": "2", "marks": 10, "kp": "运算", "p": 0.92, "d": 0.2},
         {"id": "3", "marks": 10, "kp": "概念", "p": 0.98, "d": 0.0}],
        None)

    # 3) 全错（P=0）与极端数据
    make_analysis(
        os.path.join(here, "a3_edge.json"),
        [{"id": "1", "marks": 10, "kp": "概念", "p": 0.0, "d": 0.0},
         {"id": "2", "marks": 10, "kp": "运算", "p": 1.0, "d": 0.8}] + [
            {"id": "x", "marks": 0, "kp": "无效满分", "p": 0.5}],
        None)

    # 4) 单题 + 单学生
    make_analysis(
        os.path.join(here, "a4_single.json"),
        [{"id": "1", "marks": 20, "kp": "单一知识点", "p": 0.45, "d": None}],
        [{"sid": "S1", "name": "赵一", "total": 30}])

    # 5) 少量数据 + 无 kp
    make_analysis(
        os.path.join(here, "a5_nokp.json"),
        [{"id": "1", "marks": 5, "p": 0.6}, {"id": "2", "marks": 5}] ,
        [])

    # 6) XSS / 注入样本（考试名、知识点、学生名、题干全部注入）
    make_analysis(
        os.path.join(here, "a6_xss.json"),
        [{"id": "1", "marks": 10, "kp": "<script>alert(1)</script>", "p": 0.3,
          "text": "<img src=x onerror=alert(2)>题干"}],
        [{"sid": "S9", "name": "<b>注入</b>", "total": 25}],
        {"exam": "<script>考试名</script>", "course": "<script>课程</script>"})

    # 7) 非法数值（p 越界 1.5、d 负数、marks 非数字、p=abc）
    wcsv(os.path.join(here, "q7_bad.csv"),
         ["id", "marks", "kp", "p", "d"],
         [["1", "10", "知识A", "1.5", "-0.2"],
          ["2", "10", "知识B", "abc", "2"],
          ["3", "abc", "知识C", "0.4", "0.3"]])
    wcsv(os.path.join(here, "s7_bad.csv"),
         ["学号", "姓名", "总分"],
         [["S1", "张三", "50"], ["S2", "李四", "x"], ["S3", "王五", "12"]])

    # 8) 中文别名表头 CSV（同义触发）
    wcsv(os.path.join(here, "q8_cn.csv"),
         ["题号", "知识点", "满分", "得分率", "区分度"],
         [["一", "代数", "10", "0.32", "0.35"], ["二", "几何", "10", "0.8", "0.1"]])
    wcsv(os.path.join(here, "s8_cn.csv"),
         ["学号", "姓名", "总分"],
         [["A1", "陈曦", 92], ["A2", "刘洋", 55]])

    # 9) 表头列缺失（缺 p / ms）→ 命中降级路径
    wcsv(os.path.join(here, "q9_missing.csv"),
         ["id", "marks", "kp"],
         [["1", 10, "概念"], ["2", 10, "概念2"]])  # 两题均缺 p/d

    # 10) JSON qstats 对象数组（同义输入格式）
    w(os.path.join(here, "q10_list.json"),
      json.dumps([{"id": "A", "marks": 5, "kp": "集合", "p": 0.58, "d": 0.22},
                  {"id": "B", "marks": 5, "kp": "函数", "p": 0.91, "d": 0.1}],
                 ensure_ascii=False))

    # 11) 恶意 CSV 公式注入: 学生名以 = 开头
    wcsv(os.path.join(here, "s11_formula.csv"),
         ["学号", "姓名", "总分"],
         [["S1", "=cmd|'/c calc'!A0", 60], ["S2", "@SUM(x)", 80], ["S3", "-2+3", 40], ["S4", "+1", 30]])

    # 12) 大写键 JSON（T12 别名识别：ID/P/Marks 大写键）
    w(os.path.join(here, "q12_upper.json"),
      json.dumps([{"ID": "一", "Marks": 5, "KP": "集合", "P": 0.58, "D": 0.22},
                  {"ID": "二", "Marks": 5, "KP": "函数", "P": 0.91, "D": 0.1}],
                 ensure_ascii=False))

    # 13) 非 JSON 内容、空 questions、缺 questions 字段
    w(os.path.join(here, "bad_json.json"), "{not json")
    w(os.path.join(here, "e1_empty.json"), json.dumps({"meta": {}, "questions": []}))
    w(os.path.join(here, "e2_nofield.json"), json.dumps({"meta": {}}))
    wcsv(os.path.join(here, "e3_emptyheader.csv"), [], [])

    print("fixtures ready:", here)


if __name__ == "__main__":
    main()