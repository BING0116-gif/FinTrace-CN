"""Offline Chinese Markdown research-report skeleton for A-share snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .evidence import EvidenceLedger, EvidenceRecord, LedgerValidation
from .periods import FinancialPeriodEngine
from .providers.snapshot import SnapshotProvider
from .symbols import CanonicalSymbol


@dataclass(frozen=True)
class CnResearchReport:
    """Rendered report together with its deterministic validation result."""

    markdown: str
    validation: LedgerValidation


def _number(value: Optional[float], digits: int = 2) -> str:
    return "—" if value is None else f"{value:,.{digits}f}"


def _period_label(period: str) -> str:
    return period.replace("FY", "全年").replace("H1", "上半年").replace("9M", "前三季度")


class CnResearchReportBuilder:
    """Build a traceable report solely from an already saved snapshot.

    No provider client is called here: passing a :class:`SnapshotProvider` keeps
    report rendering reproducible and avoids Tushare/API consumption.
    """

    def __init__(self, snapshot: SnapshotProvider):
        self.snapshot = snapshot

    def build(self, symbol: CanonicalSymbol, *, research_as_of: Optional[str] = None) -> CnResearchReport:
        cutoff = research_as_of or self.snapshot._payload["research_as_of"]
        profile = self.snapshot.get_profile(symbol)
        bars = self.snapshot.get_daily_bars(symbol)
        statements = self.snapshot.get_financial_statements(symbol, research_as_of=cutoff)
        ledger = EvidenceLedger(snapshot_id=self.snapshot._payload["snapshot_id"])

        latest_bar = max(bars, key=lambda item: item.trade_date) if bars else None
        if latest_bar:
            ledger.add_market_bar_facts(symbol=str(symbol), bar=latest_bar, provider="snapshot")
        for statement in statements:
            ledger.add_statement_facts(symbol=str(symbol), statement=statement, provider="snapshot")

        ttm = self._latest_ttm(statements)
        shares = self._latest_value(statements, "total_shares")
        valuation = self._valuation(symbol, latest_bar.close if latest_bar else None, shares, ttm, ledger)
        validation = ledger.validate(research_as_of=cutoff)
        return CnResearchReport(
            self._render(
                profile.name if profile else str(symbol), symbol, cutoff, latest_bar, ttm,
                valuation, ledger.records(), validation,
                profile.entity_type if profile else "operating_company",
            ),
            validation,
        )

    @staticmethod
    def _latest_ttm(statements):
        candidates = FinancialPeriodEngine.derive_ttm(statements, "income")
        return max(candidates, key=lambda item: item.fiscal_period) if candidates else None

    @staticmethod
    def _latest_value(statements, metric: str) -> Optional[float]:
        values = [item for item in statements if item.values.get(metric) is not None]
        if not values:
            return None
        return max(values, key=lambda item: item.fiscal_period).values[metric]

    @staticmethod
    def _valuation(symbol, price, shares, ttm, ledger: EvidenceLedger) -> Dict[str, Optional[float]]:
        market_cap = pe_ttm = None
        if price is not None and shares is not None:
            price_id = next(record.evidence_id for record in ledger.records() if record.metric == "close")
            share_id = next((record.evidence_id for record in ledger.records() if record.metric == "total_shares"), None)
            if share_id:
                market_cap = price * shares
                ledger.add_calculation(evidence_id="calc_market_cap", symbol=str(symbol), metric="market_cap", value=market_cap, currency="CNY", unit="CNY", operation="multiply", input_ids=[price_id, share_id])
        if market_cap is not None and ttm and ttm.values.get("net_profit") and ttm.values["net_profit"] > 0:
            profit = ttm.values["net_profit"]
            profit_id = f"calc_ttm_net_profit_{ttm.fiscal_period}"
            # TTM is derived from published statement facts; its source periods remain explicit.
            source_ids = [f"fact_{str(symbol).replace('.', '_')}_net_profit_{period}" for period in ttm.source_periods]
            if len(source_ids) == 2:
                ledger.add_calculation(evidence_id=profit_id, symbol=str(symbol), metric="net_profit_ttm", value=profit, currency="CNY", unit="CNY", operation="add", input_ids=source_ids, fiscal_period=ttm.fiscal_period, period_basis="TTM")
            # The ledger's subtract operation is left minus the remaining inputs,
            # so materialise the first addition before applying the final subtraction.
            if len(source_ids) == 3:
                subtotal_id = f"calc_ttm_net_profit_subtotal_{ttm.fiscal_period}"
                subtotal = ledger.get(source_ids[0]).value + ledger.get(source_ids[1]).value
                ledger.add_calculation(evidence_id=subtotal_id, symbol=str(symbol), metric="net_profit_ttm_subtotal", value=subtotal, currency="CNY", unit="CNY", operation="add", input_ids=source_ids[:2], fiscal_period=ttm.fiscal_period, period_basis="TTM")
                ledger.add_calculation(evidence_id=profit_id, symbol=str(symbol), metric="net_profit_ttm", value=profit, currency="CNY", unit="CNY", operation="subtract", input_ids=[subtotal_id, source_ids[2]], fiscal_period=ttm.fiscal_period, period_basis="TTM")
            pe_ttm = market_cap / profit
        return {"market_cap": market_cap, "pe_ttm": pe_ttm}

    @staticmethod
    def _render(name, symbol, cutoff, bar, ttm, valuation, records: List[EvidenceRecord], validation, entity_type: str) -> str:
        price = bar.close if bar else None
        lines = [
            f"# {name}（{symbol}）研究报告",
            "", "## 研究口径", "",
            "- 数据来源：本地版本化快照。",
            f"- 研究截止时间：{cutoff}",
            "- 数据性质：本地已验证快照；不代表实时行情，生成过程不调用 Tushare。", "",
            "## 市场价格", "", "| 项目 | 数值 | Evidence ID |", "|---|---:|---|",
            f"| RAW 收盘价（{bar.trade_date if bar else '—'}） | {_number(price)} CNY/股 | `{next((r.evidence_id for r in records if r.metric == 'close'), '—')}` |", "",
            "## TTM 财务表现", "", "| 指标 | TTM 数值（CNY） | 期间 | Evidence ID |", "|---|---:|---|---|",
        ]
        if entity_type == "financial_institution":
            lines += [
                "", "## Financial-institution valuation boundary", "",
                "- Classification: financial institution (from snapshot `entity_type`, not model inference).",
                "- This report shows only recomputable market-cap and P/E (TTM) facts; it does not present PS, EV/EBITDA, or generic DCF as a bank valuation conclusion.",
                "- Peer valuation requires bank peers, an aligned period, and evidence-covered PE/PB inputs.",
            ]
        for metric, label in (("revenue", "营业收入"), ("net_profit", "归母净利润"), ("ebit", "EBIT"), ("ebitda", "EBITDA")):
            value = ttm.values.get(metric) if ttm else None
            evidence_id = f"calc_ttm_{metric}_{ttm.fiscal_period}" if metric == "net_profit" and value is not None else "—"
            lines.append(f"| {label} | {_number(value)} | {_period_label(ttm.fiscal_period) if ttm else '—'} | `{evidence_id}` |")
        lines += ["", "## 基础估值", "", "| 指标 | 数值 | Evidence ID |", "|---|---:|---|", f"| 市值 | {_number(valuation['market_cap'])} CNY | `calc_market_cap` |", f"| P/E（TTM） | {_number(valuation['pe_ttm'])}x | `calc_ttm_net_profit_{ttm.fiscal_period}` |", "", "## Validator 结果", "", f"- 状态：{'通过' if validation.valid else '未通过'}", f"- 错误：{', '.join(validation.errors) if validation.errors else '无'}", "", "## 证据索引", "", "| Evidence ID | 指标 | 数值 | 期间/日期 | 来源 |", "|---|---|---:|---|---|"]
        for record in records:
            period = record.fiscal_period or record.published_at or "—"
            lines.append(f"| `{record.evidence_id}` | {record.metric} | {_number(record.value)} | {period} | {record.provider} |")
        return "\n".join(lines) + "\n"
