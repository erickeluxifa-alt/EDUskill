#!/usr/bin/env python3
"""
人才培养方案政策合规检测器
输入：方案解析结果(JSON) + 政策要求(JSON或文本)
输出：结构化问题清单 + 合规评分
"""

import sys
import json
import re
from typing import Any


# ========== 内置通用政策规则 ==========
# 基于教育部职业教育、普通高等教育相关文件提炼的通用规则
# 用户可通过自定义政策文件覆盖

BUILT_IN_RULES = [
    # --- 基本信息完整性 ---
    {
        "id": "B001",
        "level": "必改",
        "module": "basic_info",
        "description": "专业名称必须符合教育部专业目录规范",
        "check": "major_name_exists",
        "policy_ref": "教育部《普通高等学校本科专业目录》/ 《职业教育专业目录》",
    },
    {
        "id": "B002",
        "level": "必改",
        "module": "basic_info",
        "description": "专业代码必须填写且格式正确（6-12位数字）",
        "check": "major_code_format",
        "policy_ref": "教育部专业目录编码规范",
    },
    {
        "id": "B003",
        "level": "必改",
        "module": "basic_info",
        "description": "学制年限必须明确填写",
        "check": "degree_length_exists",
        "policy_ref": "《普通高等学校学生管理规定》",
    },

    # --- 培养目标 ---
    {
        "id": "T001",
        "level": "必改",
        "module": "training_goals",
        "description": "培养目标缺失或过于简单（少于100字），应明确说明人才类型、服务面向、核心能力",
        "check": "training_goals_length",
        "min_length": 100,
        "policy_ref": "教育部《普通高等学校本科教育教学审核评估实施方案》",
    },
    {
        "id": "T002",
        "level": "建议改",
        "module": "training_goals",
        "description": "培养目标应体现德智体美劳全面发展的要求",
        "check": "training_goals_keywords",
        "required_keywords": ["德", "智", "体", "美", "劳"],
        "policy_ref": "《关于深化教育教学改革全面提高义务教育质量的意见》",
    },
    {
        "id": "T003",
        "level": "建议改",
        "module": "training_goals",
        "description": "职业院校培养目标应明确职业面向和岗位群",
        "check": "vocational_job_orientation",
        "vocational_keywords": ["岗位", "职业", "就业", "工作领域"],
        "policy_ref": "教育部《职业教育专业简介》编制要求",
    },

    # --- 毕业要求 ---
    {
        "id": "G001",
        "level": "必改",
        "module": "graduation_requirements",
        "description": "毕业要求缺失，方案中必须包含明确的毕业要求",
        "check": "section_exists",
        "module_key": "graduation_requirements",
        "policy_ref": "教育部《普通高等学校本科专业教学质量国家标准》",
    },
    {
        "id": "G002",
        "level": "建议改",
        "module": "graduation_requirements",
        "description": "毕业要求应涵盖知识、能力、素质三个维度",
        "check": "graduation_dimensions",
        "required_dimensions": ["知识", "能力", "素质"],
        "policy_ref": "工程教育认证标准 / 教育部本科教学质量标准",
    },

    # --- 课程体系 ---
    {
        "id": "C001",
        "level": "必改",
        "module": "curriculum",
        "description": "课程体系缺失，方案中必须包含完整的课程设置",
        "check": "section_exists",
        "module_key": "curriculum",
        "policy_ref": "教育部人才培养方案制定指导意见",
    },
    {
        "id": "C002",
        "level": "必改",
        "module": "curriculum",
        "description": "必须包含思想政治理论课（思政课），且不得减少课时",
        "check": "politics_course_exists",
        "required_courses": ["思想政治", "马克思主义", "习近平", "形势与政策", "中国近现代史"],
        "policy_ref": "教育部《高等学校思想政治理论课建设标准》",
    },
    {
        "id": "C003",
        "level": "必改",
        "module": "curriculum",
        "description": "必须包含大学英语或外语类课程",
        "check": "english_course_exists",
        "required_keywords": ["英语", "外语", "大学英语"],
        "policy_ref": "教育部《大学英语教学指南》",
    },
    {
        "id": "C004",
        "level": "必改",
        "module": "curriculum",
        "description": "必须包含体育课，且每学期应有安排",
        "check": "pe_course_exists",
        "required_keywords": ["体育", "体育课", "体能"],
        "policy_ref": "教育部《高等学校体育工作基本标准》",
    },
    {
        "id": "C005",
        "level": "建议改",
        "module": "curriculum",
        "description": "建议包含劳动教育课程",
        "check": "labor_course_exists",
        "required_keywords": ["劳动教育", "劳动课", "劳动实践"],
        "policy_ref": "《大中小学劳动教育指导纲要》",
    },
    {
        "id": "C006",
        "level": "建议改",
        "module": "curriculum",
        "description": "建议包含创新创业教育课程",
        "check": "innovation_course_exists",
        "required_keywords": ["创新创业", "创业", "双创"],
        "policy_ref": "国务院《关于深化高等学校创新创业教育改革的实施意见》",
    },

    # --- 学分学时 ---
    {
        "id": "H001",
        "level": "必改",
        "module": "credit_hours",
        "description": "总学分/总学时信息缺失，方案中必须明确标注",
        "check": "credit_hours_exists",
        "policy_ref": "教育部人才培养方案制定规范",
    },
    {
        "id": "H002",
        "level": "关注项",
        "module": "credit_hours",
        "description": "本科专业总学分一般在140-160学分之间，请核实是否在合理范围",
        "check": "credit_range_bachelor",
        "min_credits": 140,
        "max_credits": 180,
        "degree_filter": ["本科", "学士"],
        "policy_ref": "教育部《关于加快建设高水平本科教育的意见》",
    },
    {
        "id": "H003",
        "level": "关注项",
        "module": "credit_hours",
        "description": "专科/高职专业总学分一般在80-110学分之间，请核实",
        "check": "credit_range_associate",
        "min_credits": 80,
        "max_credits": 120,
        "degree_filter": ["专科", "高职", "大专"],
        "policy_ref": "教育部《高等职业学校专业教学标准》",
    },

    # --- 实践教学 ---
    {
        "id": "P001",
        "level": "必改",
        "module": "practice",
        "description": "实践教学环节缺失，方案中必须包含实践教学安排",
        "check": "section_exists",
        "module_key": "practice",
        "policy_ref": "教育部《关于加强高等学校实践育人工作的若干意见》",
    },
    {
        "id": "P002",
        "level": "必改",
        "module": "practice",
        "description": "工科/理科专业实践教学比例一般不低于25%，文科不低于15%，请核实",
        "check": "practice_ratio_check",
        "policy_ref": "教育部本科专业类教学质量国家标准",
    },
    {
        "id": "P003",
        "level": "必改",
        "module": "practice",
        "description": "高职/职业院校实践教学比例应达到50%以上",
        "check": "vocational_practice_ratio",
        "min_ratio": 50,
        "policy_ref": "教育部《职业院校教材管理办法》/ 高职质量标准",
    },
    {
        "id": "P004",
        "level": "建议改",
        "module": "practice",
        "description": "应包含毕业设计/毕业论文环节（本科）或顶岗实习（高职）",
        "check": "graduation_practice_exists",
        "bachelor_keywords": ["毕业设计", "毕业论文", "毕业作品"],
        "vocational_keywords": ["顶岗实习", "毕业实习", "综合实训"],
        "policy_ref": "教育部本科教学质量标准 / 高职教学标准",
    },

    # --- 质量保障 ---
    {
        "id": "Q001",
        "level": "建议改",
        "module": "quality_assurance",
        "description": "建议在方案中说明质量保障与持续改进机制",
        "check": "section_exists",
        "module_key": "quality_assurance",
        "policy_ref": "教育部本科教学审核评估指标",
    },
]


def run_check(rule: dict, plan: dict, full_text: str) -> dict | None:
    """
    执行单条规则检查，返回问题记录或 None（表示通过）
    """
    check_type = rule.get("check", "")
    key_data = plan.get("key_data", {})
    sections = plan.get("sections", [])

    def has_section_module(module_key):
        return any(s.get("module") == module_key for s in sections)

    def section_content(module_key) -> str:
        parts = [s.get("content", "") + " " + s.get("title", "")
                 for s in sections if s.get("module") == module_key]
        return " ".join(parts)

    # --- 执行各类检查 ---
    if check_type == "major_name_exists":
        if not key_data.get("major_name"):
            return _issue(rule, "未找到专业名称，请在方案首部明确填写专业名称")

    elif check_type == "major_code_format":
        code = key_data.get("major_code", "")
        if not code:
            return _issue(rule, "未找到专业代码，请填写教育部标准专业代码")
        if not re.match(r"^\d{6,12}$", code):
            return _issue(rule, f"专业代码格式异常（当前值: {code}），应为6-12位数字")

    elif check_type == "degree_length_exists":
        if not key_data.get("degree_length"):
            return _issue(rule, "未找到学制年限信息，请明确标注（如：4年、3年等）")

    elif check_type == "training_goals_length":
        content = section_content("training_goals")
        min_len = rule.get("min_length", 100)
        if not content:
            return _issue(rule, "方案中未找到培养目标章节，请补充")
        if len(content) < min_len:
            return _issue(rule, f"培养目标内容过于简短（当前约{len(content)}字，建议不少于{min_len}字），请详细描述人才类型、核心能力和服务面向")

    elif check_type == "training_goals_keywords":
        content = section_content("training_goals")
        required = rule.get("required_keywords", [])
        missing = [kw for kw in required if kw not in content]
        if len(missing) >= 3:  # 缺少3个及以上才提醒
            return _issue(rule, f"培养目标未体现以下素质要求：{', '.join(missing)}，建议补充德智体美劳全面发展的相关表述")

    elif check_type == "vocational_job_orientation":
        content = section_content("training_goals")
        vocational_kws = rule.get("vocational_keywords", [])
        if not any(kw in full_text for kw in ["高职", "职业院校", "专科", "大专"]):
            return None  # 非职业院校，跳过
        if not any(kw in content for kw in vocational_kws):
            return _issue(rule, "职业院校培养目标应明确职业面向、岗位群或就业方向，当前内容较为笼统")

    elif check_type == "section_exists":
        module_key = rule.get("module_key", rule.get("module", ""))
        if not has_section_module(module_key):
            # 尝试通过关键词在全文检测
            kw_map = {
                "graduation_requirements": ["毕业要求", "毕业条件"],
                "curriculum": ["课程设置", "课程体系", "教学计划"],
                "practice": ["实践教学", "实习", "实训"],
                "quality_assurance": ["质量保障", "质量监控"],
            }
            fallback_kws = kw_map.get(module_key, [])
            if not any(kw in full_text for kw in fallback_kws):
                return _issue(rule, f"方案中未找到对应章节内容，建议补充")

    elif check_type == "graduation_dimensions":
        content = section_content("graduation_requirements")
        if not content:
            return None  # 已有 G001 处理缺失情况
        dims = rule.get("required_dimensions", [])
        missing = [d for d in dims if d not in content]
        if missing:
            return _issue(rule, f"毕业要求缺少以下维度：{', '.join(missing)}，建议从知识、能力、素质三个维度系统描述")

    elif check_type == "politics_course_exists":
        required = rule.get("required_courses", [])
        if not any(kw in full_text for kw in required):
            return _issue(rule, "方案中未发现思想政治理论课程，必须按教育部规定开设思想政治理论课")

    elif check_type == "english_course_exists":
        kws = rule.get("required_keywords", [])
        if not any(kw in full_text for kw in kws):
            return _issue(rule, "方案中未发现外语/英语课程，高校应开设大学英语或外语类课程")

    elif check_type == "pe_course_exists":
        kws = rule.get("required_keywords", [])
        if not any(kw in full_text for kw in kws):
            return _issue(rule, "方案中未发现体育课程，高校必须开设体育课并满足最低学时要求")

    elif check_type == "labor_course_exists":
        kws = rule.get("required_keywords", [])
        if not any(kw in full_text for kw in kws):
            return _issue(rule, "方案中未发现劳动教育相关课程，建议按《大中小学劳动教育指导纲要》要求补充")

    elif check_type == "innovation_course_exists":
        kws = rule.get("required_keywords", [])
        if not any(kw in full_text for kw in kws):
            return _issue(rule, "方案中未发现创新创业教育内容，建议纳入课程体系")

    elif check_type == "credit_hours_exists":
        if not key_data.get("total_credits") and not key_data.get("total_hours"):
            return _issue(rule, "方案中未明确标注总学分或总学时，请补充")

    elif check_type == "credit_range_bachelor":
        total_credits_str = key_data.get("total_credits", "")
        degree_filter = rule.get("degree_filter", [])
        # 判断是否为本科
        if not any(kw in full_text for kw in degree_filter):
            return None
        if total_credits_str:
            try:
                total = float(total_credits_str)
                min_c = rule.get("min_credits", 140)
                max_c = rule.get("max_credits", 180)
                if total < min_c or total > max_c:
                    return _issue(rule, f"本科专业总学分为 {total} 分，建议在 {min_c}-{max_c} 学分之间，请核实是否符合专业类标准")
            except ValueError:
                pass

    elif check_type == "credit_range_associate":
        total_credits_str = key_data.get("total_credits", "")
        degree_filter = rule.get("degree_filter", [])
        if not any(kw in full_text for kw in degree_filter):
            return None
        if total_credits_str:
            try:
                total = float(total_credits_str)
                min_c = rule.get("min_credits", 80)
                max_c = rule.get("max_credits", 120)
                if total < min_c or total > max_c:
                    return _issue(rule, f"专科/高职总学分为 {total} 分，建议在 {min_c}-{max_c} 学分之间")
            except ValueError:
                pass

    elif check_type == "practice_ratio_check":
        ratio_str = key_data.get("practice_ratio", "")
        if ratio_str:
            ratio_num = re.search(r"(\d+\.?\d*)", ratio_str)
            if ratio_num:
                ratio = float(ratio_num.group(1))
                if ratio < 15:
                    return _issue(rule, f"实践教学比例为 {ratio_str}，低于最低要求（文科≥15%，理工科≥25%），请核查")

    elif check_type == "vocational_practice_ratio":
        if not any(kw in full_text for kw in ["高职", "职业院校", "专科"]):
            return None
        ratio_str = key_data.get("practice_ratio", "")
        min_r = rule.get("min_ratio", 50)
        if ratio_str:
            ratio_num = re.search(r"(\d+\.?\d*)", ratio_str)
            if ratio_num:
                ratio = float(ratio_num.group(1))
                if ratio < min_r:
                    return _issue(rule, f"高职院校实践教学比例为 {ratio_str}，应达到 {min_r}% 以上，请调整课程体系")
        else:
            # 无法提取，标注关注项
            return {
                "rule_id": rule["id"],
                "level": "关注项",
                "module": rule.get("module", ""),
                "description": rule["description"],
                "detail": "未能从方案中自动提取实践教学比例数据，请人工核实是否达到50%以上",
                "policy_ref": rule.get("policy_ref", ""),
                "suggestion": "明确标注实践教学总学时/总学分及其占比",
            }

    elif check_type == "graduation_practice_exists":
        bachelor_kws = rule.get("bachelor_keywords", [])
        vocational_kws = rule.get("vocational_keywords", [])
        is_vocational = any(kw in full_text for kw in ["高职", "职业院校", "专科"])
        target_kws = vocational_kws if is_vocational else bachelor_kws
        if not any(kw in full_text for kw in target_kws):
            kind = "顶岗实习/综合实训" if is_vocational else "毕业设计/毕业论文"
            return _issue(rule, f"方案中未发现{kind}环节，请补充")

    return None  # 检查通过


def _issue(rule: dict, detail: str) -> dict:
    """构造问题记录"""
    return {
        "rule_id": rule["id"],
        "level": rule["level"],
        "module": rule.get("module", ""),
        "description": rule["description"],
        "detail": detail,
        "policy_ref": rule.get("policy_ref", ""),
        "suggestion": f"请根据 {rule.get('policy_ref', '相关政策')} 要求进行修改",
    }


def calculate_score(issues: list) -> int:
    """根据问题清单计算合规评分"""
    deductions = {"必改": 10, "建议改": 4, "关注项": 1}
    total_deduction = sum(deductions.get(i["level"], 0) for i in issues)
    return max(0, 100 - total_deduction)


def compliance_check(plan: dict, custom_rules: list = None) -> dict:
    """
    主检测函数
    plan: parse_plan.py 的输出
    custom_rules: 用户自定义规则列表（格式同 BUILT_IN_RULES）
    """
    all_rules = BUILT_IN_RULES + (custom_rules or [])
    full_text = plan.get("raw_text", "")
    issues = []

    for rule in all_rules:
        try:
            issue = run_check(rule, plan, full_text)
            if issue:
                issues.append(issue)
        except Exception as e:
            # 规则执行错误，记录但不中断
            issues.append({
                "rule_id": rule.get("id", "UNKNOWN"),
                "level": "关注项",
                "module": rule.get("module", ""),
                "description": f"规则 {rule.get('id')} 执行异常",
                "detail": str(e),
                "policy_ref": "",
                "suggestion": "请人工核查此项",
            })

    # 按级别排序
    level_order = {"必改": 0, "建议改": 1, "关注项": 2}
    issues.sort(key=lambda x: level_order.get(x["level"], 3))

    score = calculate_score(issues)

    # 统计
    stats = {
        "total": len(issues),
        "critical": sum(1 for i in issues if i["level"] == "必改"),
        "suggested": sum(1 for i in issues if i["level"] == "建议改"),
        "attention": sum(1 for i in issues if i["level"] == "关注项"),
    }

    return {
        "score": score,
        "stats": stats,
        "issues": issues,
        "pass": score >= 60 and stats["critical"] == 0,
    }


def format_report(check_result: dict, plan: dict) -> str:
    """格式化输出审核报告（Markdown）"""
    score = check_result["score"]
    stats = check_result["stats"]
    issues = check_result["issues"]
    passed = check_result["pass"]
    key_data = plan.get("key_data", {})

    # 评级
    if score >= 90:
        grade = "优秀 ✓"
    elif score >= 75:
        grade = "良好"
    elif score >= 60:
        grade = "基本合规"
    else:
        grade = "不合格 ✗"

    lines = [
        "# 人才培养方案政策合规审核报告",
        "",
        "## 基本信息",
        f"- 专业名称：{key_data.get('major_name', '未识别')}",
        f"- 专业代码：{key_data.get('major_code', '未识别')}",
        f"- 学制：{key_data.get('degree_length', '未识别')}年",
        f"- 总学分：{key_data.get('total_credits', '未识别')}",
        "",
        "## 审核结果摘要",
        f"| 项目 | 结果 |",
        f"|------|------|",
        f"| 合规评分 | **{score}分** ({grade}) |",
        f"| 必改问题 | {stats['critical']} 项 |",
        f"| 建议改进 | {stats['suggested']} 项 |",
        f"| 关注事项 | {stats['attention']} 项 |",
        f"| 整体判断 | {'✅ 基本通过' if passed else '❌ 需要修改后重审'} |",
        "",
    ]

    if not issues:
        lines.append("✅ 未发现明显不合规问题，方案整体符合通用政策要求。")
    else:
        lines.append("## 问题清单")
        lines.append("")

        # 按级别分组
        for level in ["必改", "建议改", "关注项"]:
            level_issues = [i for i in issues if i["level"] == level]
            if not level_issues:
                continue

            emoji = {"必改": "🔴", "建议改": "🟡", "关注项": "🔵"}.get(level, "⚪")
            lines.append(f"### {emoji} {level}项（{len(level_issues)}条）")
            lines.append("")

            for idx, issue in enumerate(level_issues, 1):
                lines.append(f"**{idx}. [{issue['rule_id']}] {issue['description']}**")
                lines.append(f"> 问题详情：{issue['detail']}")
                lines.append(f"> 政策依据：{issue['policy_ref']}")
                lines.append(f"> 修改建议：{issue['suggestion']}")
                lines.append("")

    lines.append("---")
    lines.append("*本报告基于通用政策框架自动生成，仅供参考。最终以教务主管部门审定为准。*")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "用法: compliance_check.py <plan_json_file> [custom_rules_json_file]"}, ensure_ascii=False))
        sys.exit(1)

    plan_file = sys.argv[1]
    custom_rules_file = sys.argv[2] if len(sys.argv) > 2 else None

    if plan_file == "stdin" or plan_file == "-":
        plan = json.loads(sys.stdin.read())
    else:
        with open(plan_file, "r", encoding="utf-8") as f:
            plan = json.load(f)

    custom_rules = None
    if custom_rules_file:
        with open(custom_rules_file, "r", encoding="utf-8") as f:
            custom_rules = json.load(f)

    result = compliance_check(plan, custom_rules)
    report_md = format_report(result, plan)

    # 输出 JSON（供程序调用）和 Markdown 报告（供人阅读）
    output = {
        "check_result": result,
        "report_markdown": report_md,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
