"""Render a reproducible FinTrace-CN report from a local snapshot only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.cn.providers.snapshot import SnapshotProvider
from src.cn.report import CnResearchReportBuilder
from src.cn.symbols import normalize_cn_symbol


def render_report(snapshot_path: Path, symbol_text: str, output_path: Path, research_as_of: str | None = None) -> dict:
    """Write Markdown plus provenance metadata; never calls an online provider."""
    provider = SnapshotProvider(snapshot_path)
    report = CnResearchReportBuilder(provider).build(
        normalize_cn_symbol(symbol_text), research_as_of=research_as_of,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.markdown, encoding="utf-8")
    metadata = {
        "snapshot_id": provider._payload["snapshot_id"],
        "research_as_of": research_as_of or provider._payload["research_as_of"],
        "symbol": symbol_text,
        "validation": {"valid": report.validation.valid, "errors": report.validation.errors},
        "report_path": str(output_path),
    }
    output_path.with_suffix(".metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an offline, traceable A-share snapshot report.")
    parser.add_argument("--snapshot", type=Path, required=True, help="Versioned local snapshot JSON.")
    parser.add_argument("--symbol", default="600519.SH", help="Canonical A-share symbol.")
    parser.add_argument("--output", type=Path, required=True, help="Markdown output path.")
    parser.add_argument("--research-as-of", default=None, help="Optional ISO-8601 cutoff.")
    args = parser.parse_args()
    metadata = render_report(args.snapshot, args.symbol, args.output, args.research_as_of)
    print(json.dumps(metadata, ensure_ascii=False))
    return 0 if metadata["validation"]["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
