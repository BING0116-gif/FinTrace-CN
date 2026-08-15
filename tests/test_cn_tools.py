import asyncio
import json
from pathlib import Path

from src.agents.tools.cn_tools import build_cn_snapshot_tools


FIXTURE = Path(__file__).parent / "fixtures" / "cn" / "600519.SH_illustrative_v1.json"


def test_cn_tools_resolve_and_return_offline_snapshot_data():
    tools = {tool.name: tool for tool in build_cn_snapshot_tools(FIXTURE)}
    resolved = json.loads(asyncio.run(tools["resolve_cn_symbol"].execute(query="贵州茅台")))
    prices = json.loads(asyncio.run(tools["get_cn_prices"].execute(ticker="600519.SH")))
    financials = json.loads(asyncio.run(tools["get_cn_financials"].execute(
        ticker="600519.SH", research_as_of="2025-04-01T00:00:00+08:00"
    )))
    report = json.loads(asyncio.run(tools["generate_cn_research_report"].execute(ticker=resolved["symbol"])))
    plan = json.loads(asyncio.run(tools["create_cn_research_plan"].execute(query="生成贵州茅台研究报告", ticker=resolved["symbol"], research_as_of="2025-04-01T00:00:00+08:00")))
    peer_input = {"symbol": "TARGET", "raw_price": 10, "total_shares": 10, "net_profit": 20, "book_equity": 100, "revenue": 200, "period_basis": "2025FY", "industry_code": "TEST", "evidence_ids": {"price": "p", "shares": "s", "profit": "n", "equity": "e", "revenue": "r"}}
    peer = {**peer_input, "symbol": "PEER", "net_profit": 10}
    valuation = json.loads(asyncio.run(tools["value_with_peers"].execute(target=peer_input, peers=[peer])))

    assert resolved["symbol"] == "600519.SH"
    assert prices["status"] == "ok"
    assert prices["adjustment"] == "RAW"
    assert len(financials["statements"]) == 1
    assert financials["evidence_ids"] == ["fact_600519_SH_revenue_2024FY", "fact_600519_SH_net_profit_2024FY"]
    assert report["status"] == "ok"
    assert "研究报告" in report["report_markdown"]
    assert report["validation"]["valid"]
    assert report["research_state"]["tool_trace"][0]["provider"] == "snapshot"
    assert plan["research_state"]["plan"]["symbol"] == "600519.SH"
    assert valuation["status"] == "ok"
    assert valuation["multiples"]["PE"]["implied_price"] == 20


def test_peer_valuation_rejects_array_target_with_a_tool_error_envelope():
    tool = {tool.name: tool for tool in build_cn_snapshot_tools(FIXTURE)}["value_with_peers"]

    result = json.loads(asyncio.run(tool.execute(target=[], peers=[])))

    assert result["status"] == "error"
    assert "must be JSON objects" in result["error"]
