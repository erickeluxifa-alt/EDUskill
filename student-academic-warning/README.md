# 学生学业预警分析工具 (Student Academic Early Warning Analyzer)

## 核心场景
高校教务处/院系负责人每学期末对学生学业数据进行批量风险筛查，自动识别需要干预的学生并生成分级预警建议。

## 目标角色
- 教务处教学管理者（统筹全校学业预警工作）
- 院系教学副主任 / 教学秘书（本院系学生学情分析）
- 辅导员 / 班主任（本班学生重点关注名单）
- 学工部心理辅导对接人

## 行业属性与可复用范围
- **行业**: 高等教育、职业教育、继续教育
- **场景**: 期末成绩汇总后风险筛查、学期初补考重修计划制定、毕业资格审查前置检查、退学边缘学生识别
- **适用规模**: 单班到全校均可，无人数上限限制

## 核心增益
1. **专家经验 SOP 化**：将教育部《普通高等学校学生管理规定》中关于学业预警的要求转化为七维度量化评分规则，避免人工判断的主观性和遗漏。
2. **专业数据资产能力**：支持 GPA、挂科门数、学分占比、出勤率、违纪记录等多维度的结构化输入和阈值自定义配置。
3. **分析与评价工具能力**：输出包含分级标识、详细归因、优先级排序的完整报告；为每个被标记学生生成个性化干预建议清单。

## 输入说明

### 必填字段（每个学生）
| 字段名 | 类型 | 说明 |
|--------|------|------|
| student_id | string | 学生唯一编号 |
| gpa | float | 当前GPA（4.0制） |

### 推荐字段（影响评分精度）
| 字段名 | 类型 | 说明 |
|--------|------|------|
| name, grade, major | string | 基本信息（用于报告显示）|
| fail_courses | int | 累计挂科课程数 |
| required_credits | int | 专业培养方案要求的总学分 |
| completed_credits | int | 已获得学分总数 |
| failed_credits | int | 挂科涉及的学分总和 |
| total_class_sessions | int | 本学期应出席课时数 |
| absent_sessions | int | 实际缺课次数 |
| discipline_violations | int | 违纪处分次数 |
| psychological_flag | bool | 是否有心理辅导中心跟进 |

### 可选字段
- `config_overrides`：对象级别的阈值覆盖参数，键名需匹配 DEFAULT_CONFIG 中定义的字段。

## 输出格式
JSON 格式报告，主要字段：
```
{
  "report_title": "...",
  "total_students_analyzed": N,
  "statistics": {
    "total_students": N,
    "valid_records": N,
    "by_level": {"正常": N, "关注": N, "预警": N, "严重预警": N},
    "flagged_ids": [...],
    "severe_count": N,
    ...
  },
  "validation_warnings": ["..."],
  "students_detail": [
    {
      "profile": {...},
      "_original_field_names": [...],
      "analysis_result": {
        "risk_score": N,
        "risk_level": {"name": "...", ...},
        "factor_breakdown": [...],
        "top_risk_factors": [...],
        "intervention_suggestions": [...],
        "summary_line": "..."
      }
    }
  ],
  "recommendation_priority_order": [
    {"student_id":"...","name":"...","level":"...","score":N}
  ]
}
```

## 风险等级判定标准
| 总分区间 | 等级 | 默认处置动作 |
|---------|------|------------|
| ≤10 分 | 正常 (#52c41a) | 维持常规学期检查频率即可 |
| 11~29 分 | 关注 (#faad14) | 辅导员谈话了解原因 |
| 30~49 分 | 预警 (#ff7a45) | 正式书面预警通知 + 制定帮扶计划 |
| ≥50 分 | 严重预警 (#f5222d) | 院系领导介入+家长沟通+休学评估 |

## 使用示例

### 基础用法 — 文件输入并直接打印结果
```bash
python3 scripts/academic_warning_analyzer.py --input examples/sample_students.json
```

### 高级用法 — 自定义阈值进行更严格筛选
```json
{"students":[...],"config_overrides":{"gpa_warn_threshold":2.5,"fail_course_penalty_per":20}}
```

## 依赖
* Python >= 3.6 （仅使用标准库 sys/json/re/os/getopt）

## 配置文件位置
脚本顶部的 `DEFAULT_CONFIG` 字典定义了所有默认阈值参数。用户可通过输入 JSON 的 `config_overrides` 节点在不修改代码的情况下调整任意阈值。

## 示例数据集
`examples/sample_students.json` 提供了一个含5名学生的小型样例：
- 张明(严重预警)、李华(正常)、王芳(关注→实际可能更高)、赵磊(最严重)、陈静(正常)
该样例展示了不同类型学生的典型评分路径，可用于快速验证功能完整性。

## 物料清单
1. `scripts/academic_warning_analyzer.py` - 主程序 (~430行 Python)
2. `examples/sample_students.json` - 标准示例数据集
3. `examples/selftest_cases/*.json` - 自测用例集合 (9个边界测试)
4. `SKILL.md` - Skill 元信息描述文档
5. `README.md` - 本文档
6. `SELF_TEST.md` - 自测执行日志和分析结论

## 已知限制
1. 当前版本仅接受 JSON 文件作为输入源，不直接读取 Excel 或数据库连接串；
2. 心理健康标记仅做布尔判断，未考虑不同等级的心理问题严重度差异；
3. 未内置历史趋势对比逻辑——同一学生在不同学期的分数变化轨迹需要通过外部比较两次运行结果实现；
4. 干预建议库是静态预设的，尚未基于真实学校政策模板动态适配；
5. 不写入任何持久化存储或发送通知给相关方——所有输出仅以 JSON 文本形式呈现于 stdout 或指定文件中。

## 版本变更摘要
v1.0.0 · 2026-08-18: 初版发布，提供7维度评分引擎和四级分类体系