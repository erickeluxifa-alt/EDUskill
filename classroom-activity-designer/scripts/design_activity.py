#!/usr/bin/env python3
"""Generate an offline classroom activity design package."""
import argparse
import json
import sys
from pathlib import Path


def validate(data):
    errors = []
    for field in ("course", "topic", "objectives"):
        if not data.get(field):
            errors.append(f"缺少必填字段: {field}")
    duration = data.get("duration_minutes")
    count = data.get("student_count")
    if not isinstance(duration, int) or duration <= 0:
        errors.append("duration_minutes 必须是正整数")
    if not isinstance(count, int) or count <= 0:
        errors.append("student_count 必须是正整数")
    if not isinstance(data.get("objectives"), list) or not data.get("objectives"):
        errors.append("objectives 必须是非空数组")
    return errors


def choose_mode(objectives, preferred):
    if preferred and preferred != "auto":
        return preferred
    text = " ".join(objectives)
    if any(x in text for x in ("设计", "创造", "方案", "提出")):
        return "方案工作坊"
    if any(x in text for x in ("分析", "比较", "评价", "论证")):
        return "证据辩论"
    if any(x in text for x in ("应用", "计算", "操作", "解决")):
        return "情境案例"
    return "概念排序"


def build(data):
    duration = data["duration_minutes"]
    count = data["student_count"]
    constraints = data.get("constraints") or {}
    mode = choose_mode(data["objectives"], data.get("preferred_mode", "auto"))
    group_size = 3 if count < 4 else 4
    groups = max(1, (count + group_size - 1) // group_size)
    if duration < 20:
        timeline = [("个人思考", max(3, duration // 5)), ("同桌互评", max(4, duration // 4)), ("全班收束", duration - max(3, duration // 5) - max(4, duration // 4))]
    else:
        intro = max(3, round(duration * 0.1))
        understand = max(3, round(duration * 0.15))
        work = max(5, round(duration * 0.45))
        share = max(4, round(duration * 0.2))
        timeline = [("导入与目标", intro), ("任务理解", understand), ("小组工作", work), ("展示与互评", share), ("教师收束", duration - intro - understand - work - share)]
    roles = ["主持", "记录", "证据核验", "汇报"] if group_size == 4 else ["主持/记录", "证据核验/汇报"]
    assumptions = []
    if not constraints:
        assumptions.append("未提供课堂限制，按普通教室、可使用纸笔、学生基础差异中等处理")
    if duration < 20:
        assumptions.append("课时较短，压缩为个人思考和同桌互评，不安排复杂移动")
    if constraints.get("devices") in ("无", "不可用"):
        assumptions.append("设备不可用，全部产出改为纸笔或口头记录")
    teacher_prompts = [
        f"请用一句话说明你们对“{data['topic']}”的判断，并指出依据。",
        "组内先让每位成员发言，再由记录者汇总，不用抢答代替证据。",
        "如果结论不确定，请标出假设、缺口和下一步验证方式。",
    ]
    outputs = ["小组一页结论卡：主张、依据、反例或限制、下一步行动", "每名学生提交一句个人迁移或反思"]
    rubric = [
        {"criterion": "目标达成", "4": "完整回应目标并能迁移", "3": "基本回应目标", "2": "回应部分目标", "1": "与目标无关"},
        {"criterion": "证据或方法", "4": "依据具体且能解释", "3": "有依据但解释不完整", "2": "依据模糊", "1": "无依据"},
        {"criterion": "协作过程", "4": "角色清晰且每人有可见贡献", "3": "多数成员参与", "2": "参与不均", "1": "单人完成"},
        {"criterion": "表达与迁移", "4": "表达清楚并提出新情境应用", "3": "表达清楚", "2": "表达有缺口", "1": "无法说明"},
    ]
    contingencies = [
        {"case": "学生缺少预备知识", "action": "发放三条最小提示或一个已完成示例，只要求完成核心判断"},
        {"case": "设备不可用", "action": "切换为纸笔结论卡，展示由教师随机抽取小组口头汇报"},
        {"case": "讨论沉默或单人主导", "action": "先个人写 60 秒，再按角色轮流发言，主持人记录未解决问题"},
        {"case": "剩余时间不足", "action": "取消全组长展示，改为两组互评和教师口头收束"},
    ]
    if constraints.get("room") == "固定座位":
        contingencies.append({"case": "教室固定座位", "action": "按同桌或前后排组成小组，不移动桌椅"})
    return {
        "mode": mode, "group_count": groups, "group_size": group_size,
        "timeline": [{"stage": s, "minutes": m} for s, m in timeline],
        "groups": {"count": groups, "size": group_size, "roles": roles},
        "teacher_prompts": teacher_prompts, "student_outputs": outputs,
        "rubric": rubric, "contingencies": contingencies,
        "confirmation": ["请教师确认活动模式、分组方式和时间轴", "确认后再复制到 LMS、群聊或打印，不由本地脚本自动发送"]
    }, assumptions


def render(data, activity, assumptions):
    timeline = "\n".join(f"- {x['stage']}：{x['minutes']} 分钟" for x in activity["timeline"])
    rubric = "\n".join(f"- {x['criterion']}：4分{x['4']}；3分{x['3']}；2分{x['2']}；1分{x['1']}" for x in activity["rubric"])
    contingencies = "\n".join(f"- {x['case']}：{x['action']}" for x in activity["contingencies"])
    assumptions_text = "；".join(assumptions) if assumptions else "无"
    return f"""# {data['course']}｜{data['topic']}课堂活动设计包

## 定位
- 活动模式：{activity['mode']}
- 适用人数：{data['student_count']} 人，建议 {activity['group_count']} 组，每组 {activity['group_size']} 人
- 教学目标：{'；'.join(data['objectives'])}
- 假设：{assumptions_text}

## 时间轴
{timeline}

## 分组与角色
角色：{'、'.join(activity['groups']['roles'])}。每组产出一页结论卡，个人再提交一句迁移或反思。

## 教师提示语
{chr(10).join('- ' + x for x in activity['teacher_prompts'])}

## 学生产出
{chr(10).join('- ' + x for x in activity['student_outputs'])}

## 评价量规
{rubric}

## 异常分支
{contingencies}

## 预览确认
{chr(10).join('- [ ] ' + x for x in activity['confirmation'])}
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="JSON input path, or - for stdin")
    parser.add_argument("--output", default="-", help="JSON output path")
    args = parser.parse_args()
    try:
        raw = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        result = {"status": "error", "errors": [f"输入文件不可读取或不是合法 JSON: {exc}"]}
    else:
        errors = validate(data)
        if errors:
            result = {"status": "error", "errors": errors}
        else:
            activity, assumptions = build(data)
            result = {"status": "ok", "assumptions": assumptions, "activity": activity, "markdown": render(data, activity, assumptions)}
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output == "-":
        print(output)
    else:
        Path(args.output).write_text(output, encoding="utf-8")


if __name__ == "__main__":
    main()
