#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 lab_reservation_scheduler 自测用例（28 个 JSON 文件）。"""
import json
import os

OUT = os.path.normpath(os.path.join(os.path.dirname(__file__), os.pardir, "examples", "selftest_cases"))


def W(name, obj):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def res(rid, tp="通用", cap=60, eq=None, dates=None):
    r = {"id": rid, "type": tp, "capacity": cap}
    if eq:
        r["equipment"] = eq
    if dates:
        r["open_dates"] = dates
    return r


os.makedirs(OUT, exist_ok=True)

# 1 全部解决主流程
W("resolved_ok.json", {
    "resources": [res("A", "通用", 60), res("B", "通用", 40), res("C", "机房", 30)],
    "requests": [
        {"id": "r1", "course": "物理实验", "students": 35, "teacher": "王", "date": "2026-09-09", "slot": "08:00-10:00"},
        {"id": "r2", "course": "化学实验", "students": 30, "teacher": "陈", "date": "2026-09-09", "slot": "10:10-12:00"},
        {"id": "r3", "course": "计算机实验", "students": "25", "teacher": "李", "date": "2026-09-09",
         "slot": "14:00-16:00", "res_type": "机房"},
    ]})

# 2 同义触发（中文键）
W("synonyms.json", {
    "实验室": [{"名称": "物理一", "类型": "物理", "工位数": 60}, {"名称": "机房一", "类型": "机房", "座位数": 60}],
    "预约申请": [
        {"名称": "s1", "实验课程": "光学实验", "专业班级": "物理2302", "预约人数": 40, "授课教师": "孟",
         "开课日期": "2026-09-09", "时间": "08:00-10:00", "需要类型": "物理"},
        {"name": "s2", "course": "上机", "group": "计2301", "students": 50, "teacher": "钱",
         "date": "2026-09-10", "periods": ["08:00-10:00", "14:00-16:00"], "lab_type": "机房"},
    ],
    "rules": {"teacher_conflict": True}})

# 3 日期形态
W("date_formats.json", {
    "resources": [{"id": "A", "capacity": 60}],
    "requests": [
        {"id": "1", "students": 10, "date": "2026/9/9"},
        {"id": "2", "students": 10, "date": "2026年9月9日"},
        {"id": "3", "students": 10, "date": "2026-09-11"},
    ]})

# 4 时段别名（序号/起始时间）
W("slot_alias.json", {
    "resources": [{"id": "A1", "capacity": 60}],
    "requests": [
        {"id": "1", "students": 10, "date": "2026-09-09", "时段": "08:00"},
        {"id": "2", "students": 10, "date": "2026-09-09", "时间": "3"},
        {"id": "3", "students": 10, "date": "2026-09-09", "slot": "16:10-18:00"},
    ]})

# 5 教师互斥可关闭（独占上限放开以允许多班同槽）
W("teacher_conflict_off.json", {
    "resources": [{"id": "X1", "capacity": 60}, {"id": "X2", "capacity": 60}],
    "requests": [
        {"id": "1", "students": 20, "teacher": "张伟", "date": "2026-09-09", "slot": "08:00-10:00"},
        {"id": "2", "students": 20, "teacher": "张伟", "date": "2026-09-09", "slot": "08:00-10:00"},
        {"id": "3", "students": 20, "teacher": "张伟", "date": "2026-09-09", "slot": "08:00-10:00"},
    ], "rules": {"teacher_conflict": False, "max_per_resource_slot": 3}})
# 5b 教师互斥默认开启 → 同槽同教师仅排第一单
W("teacher_conflict_on.json", {
    "resources": [{"id": "X1", "capacity": 60}, {"id": "X2", "capacity": 60}],
    "requests": [
        {"id": "1", "students": 20, "teacher": "张伟", "date": "2026-09-09", "slot": "08:00-10:00"},
        {"id": "2", "students": 20, "teacher": "张伟", "date": "2026-09-09", "slot": "08:00-10:00"},
    ]})

# 6 空输入
W("empty_input.json", {})
# 7 无预约申请
W("no_requests.json", {"resources": [{"id": "A", "capacity": 60}]})
# 8 缺日期
W("missing_date.json", {"resources": [{"id": "A", "capacity": 60}],
                        "requests": [{"id": "r", "students": 5}]})
# 9 缺人数
W("missing_students.json", {"resources": [{"id": "A", "capacity": 60}],
                            "requests": [{"id": "r", "date": "2026-09-09"}]})
# 10 缺资源
W("missing_resources.json", {"requests": [{"id": "r", "students": 5, "date": "2026-09-09"}]})
# 11 坏条目
W("bad_resources.json", {"resources": ["AA"], "requests": [{"id": "r", "students": 5, "date": "2026-09-09"}]})
# 12 容量精确匹配
W("exact_capacity.json", {"resources": [{"id": "A", "capacity": 40}],
                          "requests": [{"id": "r", "students": 40, "date": "2026-09-09"}]})
# 13 同槽跨资源拆分
W("split_two_labs.json", {"resources": [{"id": "A", "capacity": 60}, {"id": "B", "capacity": 30}],
                          "requests": [{"id": "r", "students": 90, "date": "2026-09-09"}]})
# 14 禁止拆分 → 缺口
W("split_disabled.json", {"resources": [{"id": "A", "capacity": 50}, {"id": "B", "capacity": 30}],
                          "requests": [{"id": "r", "students": 90, "date": "2026-09-09", "split": False}]})
# 15 大班 100 人可拆
W("big_class.json", {"resources": [{"id": "A", "capacity": 60}, {"id": "B", "capacity": 40}],
                     "requests": [{"id": "r", "students": 100, "date": "2026-09-09"}]})
# 16 超大班 2000 人 → 缺口
W("huge_class.json", {"resources": [{"id": "A", "capacity": 60}, {"id": "B", "capacity": 40},
                                    {"id": "C", "capacity": 30}],
                      "requests": [{"id": "r", "students": 2000, "date": "2026-09-09"}]})
# 17 人数为0
W("zero_students.json", {"resources": [{"id": "A", "capacity": 60}],
                         "requests": [{"id": "r", "students": 0, "date": "2026-09-09"},
                                      {"id": "r2", "students": 10, "date": "2026-09-09"}]})
# 18 负人数
W("negative_students.json", {"resources": [{"id": "A", "capacity": 60}],
                             "requests": [{"id": "r", "students": -5, "date": "2026-09-09"}]})
# 19 空资源列表
W("empty_resources.json", {"resources": [], "requests": [{"id": "r", "students": 5, "date": "2026-09-09"}]})
# 20 非开放日 → 缺口
W("closed_date.json", {"resources": [{"id": "A", "capacity": 60, "open_dates": ["2026-09-10"]}],
                       "requests": [{"id": "r", "students": 5, "date": "2026-09-09"}]})
# 21 设备不满足 → 缺口
W("missing_equipment.json", {"resources": [{"id": "A", "capacity": 60, "equipment": ["离心机"]}],
                             "requests": [{"id": "r", "students": 5, "date": "2026-09-09",
                                           "equipment": ["电子显微镜"]}]})
# 22 类型不匹配 → 缺口
W("no_matching_type.json", {"resources": [{"id": "A", "type": "物理", "capacity": 60}],
                            "requests": [{"id": "r", "students": 5, "date": "2026-09-09",
                                          "res_type": "化工"}]})
# 23 坏 JSON
W("bad.json", "{{{")
# 24 requests 非列表
W("requests_not_list.json", {"resources": [{"id": "A", "capacity": 60}],
                             "requests": {"a": 1}})
# 25 自定义时段
W("custom_slots.json", {
    "resources": [{"id": "A", "capacity": 60}],
    "requests": [{"id": "1", "students": 10, "date": "2026-09-09", "slot": "15:00-17:00"},
                 {"id": "2", "students": 10, "date": "2026-09-09", "slot": "09:00-12:30"}],
    "rules": {"open_slots": ["09:00-12:00", "13:00-15:00", "15:00-17:00"]}})
# 26 优先级优先
W("priority_first.json", {"resources": [{"id": "A", "capacity": 60}, {"id": "B", "capacity": 40}],
                          "rules": {"max_per_resource_slot": 3},
                          "requests": [
                              {"id": "p0", "course": "低优先课", "students": 20, "date": "2026-09-09",
                               "slot": "08:00-10:00", "priority": 0},
                              {"id": "p1", "course": "高优先课", "students": 40, "date": "2026-09-09",
                               "slot": "08:00-10:00", "priority": 3}]})
# 27 XSS 注入
W("xss.json", {"resources": [{"id": "A", "capacity": 60}],
               "requests": [{"id": "r",
                             "course": "<script>alert(1)</script>光学实验",
                             "group_name": "物理|2301班",
                             "students": 5, "teacher": "<img src=x onerror=alert(1)>",
                             "date": "2026-09-09"}]})

print("generated OK:", len(os.listdir(OUT)))