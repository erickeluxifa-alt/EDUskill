from __future__ import annotations

import json
import math
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


BASELINE_KEYS = ("baseline", "previous", "prev", "上期", "基准值")
CURRENT_KEYS = ("current", "curr", "本期", "当前值")
RESERVED_KEYS = set(BASELINE_KEYS + CURRENT_KEYS + ("id", "evidence_id"))


@dataclass
class AnalysisReport:
    task_contract: dict[str, Any]
    evidence: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    conclusion: dict[str, Any]
    recommendations: list[dict[str, Any]]
    data_gaps: list[str]
    causal_boundary: str
    quality: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        lines = [
            "# 领域分析报告",
            "",
            "## 任务契约",
        ]
        for key, value in self.task_contract.items():
            display = ", ".join(map(str, value)) if isinstance(value, list) else value
            lines.append(f"- **{key}**：{display}")

        lines.extend(["", "## 证据"])
        for item in self.evidence:
            lines.append(f"- **{item['id']}** {item['statement']}")

        lines.extend(["", "## 发现"])
        for item in self.findings:
            lines.append(f"- {item['statement']}（证据：{', '.join(item['evidence_ids'])}）")

        lines.extend(
            [
                "",
                "## 结论",
                f"{self.conclusion['statement']}（证据：{', '.join(self.conclusion['evidence_ids'])}）",
                "",
                "## 实操建议",
            ]
        )
        for item in self.recommendations:
            lines.append(
                f"- **{item['owner']}**：{item['action']}；目标指标：{item['metric']}；"
                f"验证方式：{item['validation']}（证据：{', '.join(item['evidence_ids'])}）"
            )

        lines.extend(["", "## 数据缺口"])
        lines.extend(f"- {item}" for item in self.data_gaps)
        lines.extend(
            [
                "",
                "## 因果边界",
                self.causal_boundary,
                "",
                "## 质量状态",
                f"**{self.quality['status']}**：{self.quality['message']}",
            ]
        )
        return "\n".join(lines)


class AnalysisPipeline:
    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)

    def execute(
        self,
        question: str,
        industry: str,
        data_path: Path,
        record_feedback: bool = True,
    ) -> AnalysisReport:
        raw_payload = json.loads(Path(data_path).read_text(encoding="utf-8"))
        if isinstance(raw_payload, list):
            payload = {"records": raw_payload}
        elif isinstance(raw_payload, dict):
            payload = raw_payload
        else:
            raise ValueError("数据文件顶层必须是 JSON 对象或记录数组")

        records = self._records(payload)
        if not records:
            return self._blocked_report(question, industry, payload)
        if not all(isinstance(record, dict) for record in records):
            raise ValueError("数据明细中的每条记录都必须是 JSON 对象")

        baseline_key = self._find_key(records[0], BASELINE_KEYS)
        current_key = self._find_key(records[0], CURRENT_KEYS)
        if not baseline_key or not current_key:
            raise ValueError("数据明细必须包含基准值和当前值字段")
        self._validate_records(records, baseline_key, current_key)

        dimensions = payload.get("dimensions") or [
            key
            for key, value in records[0].items()
            if key not in RESERVED_KEYS and not isinstance(value, (int, float))
        ]
        if not isinstance(dimensions, list) or not all(
            isinstance(dimension, str) and dimension for dimension in dimensions
        ):
            raise ValueError("dimensions 必须是非空字符串数组")
        unknown_dimensions = [
            dimension
            for dimension in dimensions
            if not any(dimension in record for record in records)
        ]
        if unknown_dimensions:
            raise ValueError(f"数据明细缺少维度字段：{', '.join(unknown_dimensions)}")

        baseline = sum(float(item[baseline_key]) for item in records)
        current = sum(float(item[current_key]) for item in records)
        delta = current - baseline
        rate = delta / baseline if baseline else None

        metric = payload.get("metric", {})
        metric_name = metric.get("name", payload.get("metric_name", "目标指标"))
        unit = metric.get("unit", payload.get("unit", "未提供"))
        period = payload.get("period", {})
        baseline_period = period.get("baseline", "基准期")
        current_period = period.get("current", "当前期")

        evidence = [
            {
                "id": "E001",
                "type": "overall",
                "baseline": baseline,
                "current": current,
                "delta": delta,
                "rate": rate,
                "statement": self._overall_statement(
                    metric_name, unit, baseline_period, current_period, baseline, current, delta, rate
                ),
            }
        ]
        findings: list[dict[str, Any]] = []
        all_segments: list[dict[str, Any]] = []
        evidence_index = 2

        for dimension in dimensions:
            segments = self._aggregate(records, dimension, baseline_key, current_key, delta)
            evidence_id = f"E{evidence_index:03d}"
            evidence_index += 1
            evidence.append(
                {
                    "id": evidence_id,
                    "type": "dimension",
                    "dimension": dimension,
                    "segments": segments,
                    "statement": self._dimension_statement(dimension, segments, unit),
                }
            )
            negative = [item for item in segments if item["delta"] < 0]
            if negative:
                top = min(negative, key=lambda item: item["delta"])
                all_segments.append({**top, "dimension": dimension, "evidence_id": evidence_id})
                findings.append(
                    {
                        "statement": (
                            f"按{dimension}拆解，{top['value']}减少{abs(top['delta']):g}{unit}，"
                            f"占整体变化的{top['contribution_pct']:.1f}%"
                        ),
                        "evidence_ids": [evidence_id],
                    }
                )

        top_factor = max(all_segments, key=lambda item: abs(item["delta"]), default=None)
        conclusion = self._conclusion(top_factor)
        recommendations = self._recommendations(all_segments, metric_name, unit, payload)
        data_gaps = payload.get("data_gaps") or [
            "缺少项目延期、终止、拨款节奏和政策变化等原因变量。",
            "当前结果是结构贡献分析，不能单独识别因果机制。",
        ]
        quality = self._quality(records, dimensions, evidence, delta, unit)

        report = AnalysisReport(
            task_contract={
                "行业": industry,
                "对象": payload.get("object", "待分析对象"),
                "指标": f"{metric_name}（单位：{unit}）",
                "周期": f"{baseline_period} vs {current_period}",
                "基准": baseline_period,
                "维度": dimensions,
                "目标": question,
                "输出类型": "归因拆解报告",
            },
            evidence=evidence,
            findings=findings,
            conclusion=conclusion,
            recommendations=recommendations,
            data_gaps=data_gaps,
            causal_boundary=(
                "贡献度描述各分组与整体变化的算术关系，不代表该分组已被证明是变化的因果来源；"
                "需要结合项目级过程变量或准实验设计进一步验证。"
            ),
            quality=quality,
        )
        if record_feedback:
            self._record_feedback(question, industry, report)
        return report

    @staticmethod
    def _records(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return payload
        for key in ("records", "rows", "data"):
            if isinstance(payload.get(key), list):
                return payload[key]
        return []

    @staticmethod
    def _find_key(record: dict[str, Any], candidates: tuple[str, ...]) -> str | None:
        return next((key for key in candidates if key in record), None)

    @staticmethod
    def _validate_records(
        records: list[dict[str, Any]], baseline_key: str, current_key: str
    ) -> None:
        for index, record in enumerate(records, start=1):
            if not isinstance(record, dict):
                raise ValueError(f"第{index}条记录不是 JSON 对象")
            for key in (baseline_key, current_key):
                if key not in record:
                    raise ValueError(f"第{index}条记录缺少字段：{key}")
                try:
                    value = float(record[key])
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"第{index}条记录的{key}不是有效数值") from exc
                if not math.isfinite(value):
                    raise ValueError(f"第{index}条记录的{key}必须是有限数值")

    @staticmethod
    def _aggregate(
        records: list[dict[str, Any]],
        dimension: str,
        baseline_key: str,
        current_key: str,
        total_delta: float,
    ) -> list[dict[str, Any]]:
        groups: dict[str, dict[str, float]] = {}
        for record in records:
            value = str(record.get(dimension, "未分类"))
            group = groups.setdefault(value, {"baseline": 0.0, "current": 0.0})
            group["baseline"] += float(record[baseline_key])
            group["current"] += float(record[current_key])

        result = []
        for value, group in groups.items():
            segment_delta = group["current"] - group["baseline"]
            result.append(
                {
                    "value": value,
                    "baseline": group["baseline"],
                    "current": group["current"],
                    "delta": segment_delta,
                    "contribution_pct": segment_delta / total_delta * 100 if total_delta else 0.0,
                }
            )
        return sorted(result, key=lambda item: item["delta"])

    @staticmethod
    def _overall_statement(
        metric: str,
        unit: str,
        baseline_period: str,
        current_period: str,
        baseline: float,
        current: float,
        delta: float,
        rate: float | None,
    ) -> str:
        rate_text = "无法计算" if rate is None else f"{rate * 100:.1f}%"
        return (
            f"{metric}从{baseline_period}的{baseline:g}{unit}变为{current_period}的{current:g}{unit}，"
            f"变化{delta:g}{unit}，变化率{rate_text}。"
        )

    @staticmethod
    def _dimension_statement(dimension: str, segments: list[dict[str, Any]], unit: str) -> str:
        parts = [
            f"{item['value']} {item['delta']:+g}{unit}（贡献{item['contribution_pct']:.1f}%）"
            for item in segments
        ]
        return f"按{dimension}拆解：" + "；".join(parts) + "。"

    @staticmethod
    def _conclusion(top_factor: dict[str, Any] | None) -> dict[str, Any]:
        if not top_factor:
            return {"statement": "现有数据未识别出负向贡献因素。", "evidence_ids": ["E001"]}
        return {
            "statement": (
                f"单一维度切片中，{top_factor['dimension']}={top_factor['value']}的负向贡献最大；"
                "不同维度存在重叠，不应跨维度累加贡献。"
            ),
            "evidence_ids": ["E001", top_factor["evidence_id"]],
        }

    @staticmethod
    def _recommendations(
        segments: list[dict[str, Any]], metric_name: str, unit: str, payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        owners = payload.get("owners", {})
        recommendations = []
        for item in sorted(segments, key=lambda value: value["delta"])[:2]:
            owner = owners.get(item["dimension"], "科研管理部门与相关责任单位")
            recommendations.append(
                {
                    "owner": owner,
                    "action": f"核查{item['dimension']}={item['value']}对应项目的延期、终止与拨款变化并建立恢复清单",
                    "metric": f"{metric_name}缺口、在途项目金额（{unit}）",
                    "validation": "按月复核项目级明细，并与未干预的同类项目或历史同期比较",
                    "evidence_ids": [item["evidence_id"]],
                }
            )
        return recommendations

    @staticmethod
    def _quality(
        records: list[dict[str, Any]],
        dimensions: list[str],
        evidence: list[dict[str, Any]],
        total_delta: float,
        unit: str,
    ) -> dict[str, Any]:
        mismatches = []
        for item in evidence[1:]:
            segment_sum = sum(segment["delta"] for segment in item["segments"])
            if not math.isclose(segment_sum, total_delta, rel_tol=1e-9, abs_tol=1e-9):
                mismatches.append(item["dimension"])
        if mismatches:
            return {
                "status": "blocked",
                "message": f"维度{', '.join(mismatches)}无法回算整体变化。",
            }
        warnings = []
        if unit == "未提供":
            warnings.append("指标单位缺失")
        if len(records) < 10:
            warnings.append("样本明细较少")
        if not dimensions:
            warnings.append("缺少拆解维度")
        if warnings:
            return {"status": "warning", "message": "；".join(warnings) + "，结论需结合数据缺口解释。"}
        return {"status": "passed", "message": "口径完整，各维度贡献可回算整体变化。"}

    @staticmethod
    def _record_feedback(question: str, industry: str, report: AnalysisReport) -> None:
        log_path = Path(tempfile.gettempdir()) / "domain-analysis-feedback.jsonl"
        record = {
            "question": question,
            "industry": industry,
            "quality_status": report.quality["status"],
        }
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    @staticmethod
    def _blocked_report(question: str, industry: str, payload: dict[str, Any]) -> AnalysisReport:
        return AnalysisReport(
            task_contract={
                "行业": industry,
                "对象": payload.get("object", "待分析对象"),
                "目标": question,
                "输出类型": "归因拆解报告",
            },
            evidence=[],
            findings=[],
            conclusion={"statement": "缺少可分析的数据明细，无法形成确定性结论。", "evidence_ids": []},
            recommendations=[],
            data_gaps=["需要提供包含基准值、当前值和拆解维度的数据明细。"],
            causal_boundary="无有效数据时不进行归因判断。",
            quality={"status": "blocked", "message": "未发现可分析的数据记录。"},
        )
