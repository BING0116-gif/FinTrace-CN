"""Regression coverage for read-only workbench peer valuation."""

from src.cn import workbench_service as service
import json


def test_peer_valuation_returns_real_peer_comparison_for_liquor_snapshot():
    result = service.research_peer_valuation("600519.SH_20260810_tushare_v1")

    assert result["available"] is True
    assert result["peer_count"] >= 4
    assert result["multiples"]["PE"]["median"] is not None
    assert result["validation"]["valid"] is True


def test_peer_valuation_refuses_to_compare_when_local_peer_coverage_is_missing():
    result = service.research_peer_valuation("688981.SH_20260813_tushare_v1")

    assert result["available"] is False
    assert result["industry_code"] == "L1_07"
    assert result["peer_count"] == 0


def test_readiness_makes_missing_historical_fields_and_peer_coverage_visible():
    readiness = service.research_readiness("688981.SH_20260813_tushare_v1")

    assert readiness["status"] == "limited"
    assert "annual_financial_coverage" in readiness["warnings"]
    assert "peer_coverage" in readiness["warnings"]
    assert readiness["checks"]["key_metrics"]["status"] == "pass"


def test_validation_exposes_real_ledger_and_non_blocking_readiness_checks():
    result = service.research_validation("600519.SH_20260810_tushare_v1")

    assert result["status"] in {"pass", "warning"}
    assert result["valid"] is True
    assert result["conclusion_allowed"] is True
    assert result["checks"][0]["code"] == "ledger"
    assert result["checks"][0]["status"] == "pass"
    assert all(check["remediation"] for check in result["checks"])


def test_evidence_exposes_kpi_calculation_dependencies_without_ui_calculation():
    summary = service.research_summary("600519.SH_20260810_tushare_v1")
    result = service.research_evidence("600519.SH_20260810_tushare_v1")
    records = {record["evidence_id"]: record for record in result["records"]}

    assert summary["key_metrics"]["pe_ttm"] == records["calc_pe_ttm"]["value"]
    assert records["calc_market_cap"]["operation"] == "multiply"
    assert len(records["calc_market_cap"]["input_ids"]) == 2
    assert records["calc_pe_ttm"]["operation"] == "divide"
    assert records["calc_pe_ttm"]["input_ids"] == ["calc_market_cap", "calc_ttm_net_profit_2026Q1"]
    assert records["calc_pe_ttm"]["unit"] == "multiple"


def test_market_chart_points_each_expose_evidence_basis_and_source():
    result = service.research_market("600519.SH_20260810_tushare_v1")

    assert result["bars"]
    assert all(point["evidence_id"].endswith("_RAW") for point in result["bars"])
    assert all(point["price_basis"] == "RAW" for point in result["bars"])
    assert all(point["provider"] == result["provider"] for point in result["bars"])
    assert all(point["trade_date"] <= result["research_as_of"][:10] for point in result["bars"])


def test_financial_chart_points_expose_period_disclosure_and_metric_evidence():
    result = service.research_financials("600519.SH_20260810_tushare_v1")
    annual = [item for item in result["statements"] if item["fiscal_period"].endswith("FY") and item["available_as_of"]]

    assert annual
    assert all(item["published_at"] <= result["research_as_of"] for item in annual)
    assert all(item["evidence_ids"].get("revenue") for item in annual if item["values"].get("revenue") is not None)


def test_dependency_graph_is_derived_from_real_record_input_ids():
    result = service.research_evidence("600519.SH_20260810_tushare_v1")
    expected = {
        (input_id, record["evidence_id"])
        for record in result["records"] for input_id in record.get("input_ids", [])
    }

    actual = {(edge["source"], edge["target"]) for edge in result["dependency_graph"]["edges"]}
    assert actual == expected
    assert ("calc_market_cap", "calc_pe_ttm") in actual


def test_negative_ui_guardrails_cover_missing_future_and_validation_block(monkeypatch):
    monkeypatch.setattr(service, "research_financials", lambda _snapshot_id: {
        "issues": [
            {"code": "missing_value", "metric": "revenue"},
            {"code": "future_disclosure", "period": "2027FY"},
        ]
    })
    monkeypatch.setattr(service, "research_validation", lambda _snapshot_id: {
        "status": "blocked", "conclusion_allowed": False,
    })

    result = service.research_display_guardrails("synthetic")

    assert result["missing_data"] == {"visible": True, "count": 1, "action": "show_unavailable"}
    assert result["future_data"] == {"visible": True, "count": 1, "action": "exclude_from_charts"}
    assert result["validation_block"] == {
        "visible": True, "conclusion_allowed": False, "action": "hide_deterministic_conclusions",
    }


def test_market_contract_exposes_adjustment_coverage_and_volume_units():
    result = service.research_market("600519.SH_20260810_tushare_v1", "RAW")

    assert result["adjustment_coverage"] == {"RAW": True, "QFQ": False, "HFQ": False}
    assert result["unit"] == "CNY/share"
    assert result["volume_unit"] == "lot"
    assert all(point["volume"] is not None for point in result["bars"])


def test_financial_trends_support_disclosed_period_bases_without_ui_calculation():
    snapshot_id = "600519.SH_20260810_tushare_v1"
    for basis in ("FY", "Q1", "H1", "9M", "TTM"):
        result = service.research_financial_trends(snapshot_id, basis)
        assert result["period_basis"] == basis
        assert result["unit"]["net_margin"] == "percent"
        for point in result["points"]:
            assert point["published_at"] <= result["research_as_of"]
            if point["net_margin"] is not None:
                assert point["evidence_ids"]["net_margin"]


def test_ttm_trend_calculations_are_present_in_evidence_dependency_graph():
    snapshot_id = "600519.SH_20260810_tushare_v1"
    trends = service.research_financial_trends(snapshot_id, "TTM")
    evidence = service.research_evidence(snapshot_id)
    records = {item["evidence_id"]: item for item in evidence["records"]}

    calculated = [point for point in trends["points"] if point["evidence_ids"]["revenue"] and point["evidence_ids"]["revenue"].startswith("calc_")]
    assert calculated
    for point in calculated:
        record = records[point["evidence_ids"]["revenue"]]
        assert record["operation"] == "period_engine"
        assert record["input_ids"] == point["source_evidence_ids"]["revenue"]


def test_peer_page_values_are_computed_by_service_with_period_and_price_basis():
    result = service.research_peer_valuation("600519.SH_20260810_tushare_v1")

    assert result["target_multiples"]["PE"] is not None
    assert result["period_basis"] == "TTM_SNAPSHOT_AS_OF"
    assert result["price_basis"] == "RAW"


def test_overview_deltas_and_status_are_service_owned_and_validator_gated():
    result = service.research_overview_insights("600519.SH_20260810_tushare_v1")

    assert result["period_basis"] == "FY"
    assert result["latest_period"] is not None
    assert result["performance_status"] in {"improving", "under_pressure", "diverging"}
    assert result["revenue_change_percent"] is not None
    assert result["net_profit_change_percent"] is not None
    assert result["validation_status"] in {"pass", "warning"}
    assert result["conclusion_allowed"] is True


def test_peer_valuation_exposes_distribution_iqr_range_and_formula_evidence():
    result = service.research_peer_valuation("600519.SH_20260810_tushare_v1")
    evidence_ids = {item["evidence_id"] for item in service.research_evidence("600519.SH_20260810_tushare_v1")["records"]}

    assert result["distributions"]["PE"]
    assert all(row["snapshot_id"] and row["research_as_of"] for row in result["distributions"]["PE"])
    interval = result["valuation_ranges"]["PE"]
    assert interval["p25"] <= interval["median"] <= interval["p75"]
    assert interval["implied_price_low"] <= interval["implied_price_median"] <= interval["implied_price_high"]
    formula = result["formulas"]["PE"]
    assert formula["target_multiple"] == "market_cap / denominator"
    assert set(formula["target_input_evidence_ids"]).issubset(evidence_ids)
    assert set(formula["target_input_evidence_ids"]).issubset(result["evidence_ids"])


def test_global_validator_gate_redacts_all_implied_price_outputs(monkeypatch):
    monkeypatch.setattr(service, "research_peer_valuation", lambda _snapshot_id: {
        "multiples": {"PE": {"implied_price": 12.0}},
        "valuation_ranges": {"PE": {"implied_price_low": 10.0, "implied_price_median": 12.0, "implied_price_high": 14.0}},
    })
    monkeypatch.setattr(service, "research_validation", lambda _snapshot_id: {
        "status": "blocked", "conclusion_allowed": False,
    })

    result = service.research_valuation("synthetic")

    assert result["multiples"]["PE"]["implied_price"] is None
    assert result["valuation_ranges"]["PE"] == {
        "implied_price_low": None, "implied_price_median": None, "implied_price_high": None,
    }
    assert result["gated_reason"] == "validator_blocked"


def test_research_task_is_queued_idempotently_and_can_be_safely_rerun(tmp_path, monkeypatch):
    submitted = []
    monkeypatch.setattr(service, "TASK_DIR", tmp_path)
    monkeypatch.setattr(service, "_submit_research_task", lambda task: submitted.append(task["id"]))

    first = service.start_research("600519.SH")
    duplicate = service.start_research("600519.SH")

    assert first["status"] == "queued"
    assert duplicate["id"] == first["id"]
    assert duplicate["idempotent_reuse"] is True
    assert submitted == [first["id"]]
    persisted = json.loads((tmp_path / f"{first['id']}.json").read_text(encoding="utf-8"))
    assert persisted["trace"][0]["event"] == "queued"

    persisted["status"] = "failed"
    (tmp_path / f"{first['id']}.json").write_text(json.dumps(persisted), encoding="utf-8")
    retry = service.rerun_task(first["id"])

    assert retry["status"] == "queued"
    assert retry["retry_of"] == first["id"]
    assert retry["retry_count"] == 1
    assert submitted == [first["id"], retry["id"]]


def test_research_worker_persists_failure_and_trace_without_masking_it(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "TASK_DIR", tmp_path)
    task = service._new_task("600519.SH", "offline_research")
    task.update({"snapshot_id": "snapshot-1", "status": "queued", "progress_percent": 0})
    service._save_task(task)
    monkeypatch.setattr(service, "load_snapshot", lambda _snapshot_id: {"research_as_of": "2026-08-10T23:00:00+08:00"})
    monkeypatch.setattr(service, "_snapshot_path", lambda _snapshot_id: tmp_path / "snapshot.json")
    monkeypatch.setattr(service, "SnapshotProvider", lambda _path: object())

    class BrokenBuilder:
        def __init__(self, _provider):
            pass

        def build(self, *_args, **_kwargs):
            raise RuntimeError("deterministic test failure")

    monkeypatch.setattr(service, "CnResearchReportBuilder", BrokenBuilder)
    service._execute_research_task(task["id"])

    completed = service.get_task(task["id"])
    assert completed["status"] == "failed"
    assert completed["error_type"] == "RuntimeError"
    assert [event["event"] for event in completed["trace"]] == ["load_snapshot", "build_report", "failed"]


def test_snapshot_acquisition_is_queued_idempotently_and_can_be_safely_rerun(tmp_path, monkeypatch):
    submitted = []
    monkeypatch.setattr(service, "TASK_DIR", tmp_path)
    monkeypatch.setattr(service, "_submit_snapshot_task", lambda task, runner: submitted.append(task["id"]))

    first = service.collect_snapshot("600519.SH", start_date="20260801", end_date="20260810")
    duplicate = service.collect_snapshot("600519.SH", start_date="20260801", end_date="20260810")

    assert first["status"] == "queued"
    assert duplicate["id"] == first["id"]
    assert duplicate["idempotent_reuse"] is True
    assert submitted == [first["id"]]

    persisted = service.get_task(first["id"])
    persisted["status"] = "failed"
    service._save_task(persisted)
    retry = service.rerun_task(first["id"])

    assert retry["status"] == "queued"
    assert retry["retry_of"] == first["id"]
    assert retry["retry_count"] == 1
    assert submitted == [first["id"], retry["id"]]


def test_task_cancellation_is_immediate_for_queued_and_cooperative_for_running(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "TASK_DIR", tmp_path)
    queued = service._new_task("600519.SH", "offline_research")
    queued.update({"status": "queued", "progress_percent": 0})
    service._save_task(queued)

    cancelled = service.cancel_task(queued["id"])
    assert cancelled["status"] == "cancelled"
    assert service.get_task_progress(queued["id"])["progress_percent"] == 100

    running = service._new_task("600519.SH", "snapshot_acquisition")
    running.update({"status": "running", "progress_percent": 55})
    service._save_task(running)
    requested = service.cancel_task(running["id"])

    assert requested["status"] == "running"
    assert requested["cancellation_requested"] is True
    assert requested["trace"][-1]["event"] == "cancellation_requested"


def test_task_diagnostics_are_bounded_and_do_not_expose_server_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "TASK_DIR", tmp_path)
    task = service._new_task("600519.SH", "snapshot_acquisition")
    task.update({"status": "failed", "current_step": "probe", "error_type": "RuntimeError",
                 "error": f"failed under {service.PROJECT_ROOT}\\private", "call_budget": 6})
    service._save_task(task)

    result = service.task_diagnostics(task["id"])

    assert result["error_type"] == "RuntimeError"
    assert "<project>" in result["error_summary"]
    assert "report_path" not in result
    assert "snapshot_path" not in result


def test_evaluation_inventory_reads_measured_artifacts_and_preserves_missing_variants(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "EVALUATION_DIR", tmp_path)
    ablation = tmp_path / "ablation" / "run-1"
    ablation.mkdir(parents=True)
    (ablation / "ablation.json").write_text(json.dumps({
        "variants": [{"variant": "direct_llm", "tool_f1": 0.5}],
        "metadata": {"benchmark_version": "v1"},
        "missing_variants": ["agent_tools"],
    }), encoding="utf-8")

    items = service.list_evaluations()
    detail = service.evaluation_detail("ablation/run-1/ablation.json")

    assert items == [{"id": "ablation/run-1/ablation.json", "kind": "ablation", "filename": "ablation.json",
                      "benchmark_version": "v1", "run_at": None, "available": True}]
    assert detail["missing_variants"] == ["agent_tools"]


def test_agent_ablation_artifact_keeps_measured_operational_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "EVALUATION_DIR", tmp_path)
    directory = tmp_path / "agent_ablation"
    directory.mkdir()
    (directory / "ablation_results.json").write_text(json.dumps({
        "benchmark_version": "v3", "model": "mock", "dry_run": True,
        "metrics": {"agent_tools_evidence_validator": {
            "cases": 2, "validator_intercept_rate": 1.0,
            "error_conclusion_leakage": 0.0, "avg_latency_seconds": 0.2, "total_cost_usd": 0.0,
        }},
        "detailed_results": {"agent_tools_evidence_validator": [{"case_id": "case-1", "passed": True}]},
    }), encoding="utf-8")

    detail = service.evaluation_detail("agent_ablation/ablation_results.json")

    assert detail["kind"] == "ablation"
    assert detail["variants"][0]["validator_intercept_rate"] == 1.0
    assert detail["missing_variants"] == ["direct_llm", "agent_tools", "agent_tools_evidence"]
