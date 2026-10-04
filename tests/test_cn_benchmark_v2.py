import json

import pytest

from src.cn.benchmark import (
    V2_METRICS, build_v2_report, compute_v2_metrics, environment_fingerprint,
    load_v2_cases, precision_recall_f1, write_v2_report,
)


def test_v2_scorecard_has_24_metrics_and_exact_prf():
    assert len(V2_METRICS) == 24
    assert precision_recall_f1(8, 2, 2) == {"precision": .8, "recall": .8, "f1": .8}
    result = compute_v2_metrics({"extraction": {"tp": 8, "fp": 2, "fn": 2}, "latency": 1.25})
    assert result["extraction_f1"] == .8
    assert result["latency"] == 1.25


def test_v2_report_preserves_na_and_fingerprint(tmp_path):
    report = build_v2_report(metrics={"checker": {"tp": 1, "fp": 1, "fn": 0, "negative_total": 2}}, metadata={"model": "offline"})
    assert len(report["metrics"]) == 24
    assert any(row["status"] == "N/A" for row in report["metrics"])
    assert report["environment"]["fingerprint"] == environment_fingerprint(suite="cn_agent_v2", dataset="synthetic", config={"model": "offline"})["fingerprint"]
    write_v2_report(tmp_path, report)
    assert json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))["schema_version"] == "cn-agent-v2-benchmark-1.0.0"


def test_v2_split_loader_and_isolation(tmp_path):
    source = "tests/fixtures/cn/benchmark_v2"
    assert len(load_v2_cases(source, "synthetic")) == 2
    bad = tmp_path / "real.json"
    bad.write_text(json.dumps({"split": "synthetic", "offline_fixture": True, "cases": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="split mismatch"):
        load_v2_cases(bad, "real")
