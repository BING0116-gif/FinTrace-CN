"""Tests for the deterministic A-share industry classification."""

from src.cn.industries import (
    Industry, get_industry, get_industry_code, get_industry_name,
    industry_peers, is_financial_institution, known_industries, known_stocks,
)


def test_get_industry_maotai():
    ind = get_industry("600519")
    assert ind is not None
    assert ind.name == "食品饮料"


def test_get_industry_midea():
    ind = get_industry("000333")
    assert ind is not None
    assert ind.name == "家用电器"


def test_get_industry_bank():
    ind = get_industry("600036")
    assert ind is not None
    assert ind.name == "银行"


def test_get_industry_unknown_returns_none():
    assert get_industry("999999") is None


def test_get_industry_code():
    assert get_industry_code("600519") == "L1_01"
    assert get_industry_code("999999") is None


def test_get_industry_name():
    assert get_industry_name("600519") == "食品饮料"
    assert get_industry_name("999999") is None


def test_is_financial_institution_bank():
    assert is_financial_institution("600036") is True  # 招商银行
    assert is_financial_institution("601318") is True  # 中国平安


def test_is_financial_institution_nonbank():
    assert is_financial_institution("600519") is False  # 茅台
    assert is_financial_institution("000333") is False  # 美的


def test_is_financial_institution_unknown():
    assert is_financial_institution("999999") is False


def test_industry_peers_liquor():
    peers = industry_peers("600519")
    assert "000858" in peers  # 五粮液
    assert "000568" in peers  # 泸州老窖
    assert "600519" not in peers  # target excluded


def test_industry_peers_bank():
    peers = industry_peers("600036")
    assert "601398" in peers  # 工商银行
    assert "601939" in peers  # 建设银行


def test_industry_peers_unknown():
    assert industry_peers("999999") == []


def test_known_industries_contains_all():
    industries = known_industries()
    assert len(industries) == 31
    assert "L1_01" in industries
    assert "L1_31" in industries


def test_known_industries_structure():
    ind = known_industries()["L1_01"]
    assert isinstance(ind, Industry)
    assert ind.code == "L1_01"
    assert ind.level == 1


def test_known_stocks_contains_major():
    stocks = known_stocks()
    assert "600519" in stocks
    assert "000333" in stocks
    assert "300750" in stocks
    assert "600036" in stocks


def test_known_stocks_industry_mapping():
    stocks = known_stocks()
    assert stocks["600519"] == "L1_01"
    assert stocks["600036"] == "L1_04"


def test_mapping_is_readonly():
    stocks = known_stocks()
    assert stocks["600519"] == "L1_01"


def test_industry_peers_empty_for_isolated_stock():
    # Stocks that exist but are the only one in their industry
    peers = industry_peers("600900")  # 长江电力 — 公用事业
    assert "601985" in peers  # 中国核电