from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from analysis_system import AnalysisPipeline  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="运行领域经营分析")
    parser.add_argument("--question", required=True)
    parser.add_argument("--industry", required=True)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = parser.parse_args()

    data_path = args.data if args.data.is_absolute() else PROJECT_ROOT / args.data
    report = AnalysisPipeline(PROJECT_ROOT).execute(args.question, args.industry, data_path, record_feedback=True)
    if args.format == "json":
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(report.to_markdown())


if __name__ == "__main__":
    main()
