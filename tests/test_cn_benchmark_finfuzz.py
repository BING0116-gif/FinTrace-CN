from src.cn.benchmark import build_v2_report

def test_v2_benchmark_can_carry_finfuzz_report_without_inventing_metrics():
    report = build_v2_report(finfuzz={"suite_id": "offline", "overall": {"precision": None}, "status": "measured fixture only"})
    assert report["finfuzz"]["overall"]["precision"] is None
