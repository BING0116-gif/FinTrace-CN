import pytest

from src.cn.errors import UnsupportedSymbolError
from src.cn.symbols import normalize_cn_symbol


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("600519", "600519.SH"),
        ("600519.SH", "600519.SH"),
        ("000333", "000333.SZ"),
        ("300750.SZ", "300750.SZ"),
        ("920001.BJ", "920001.BJ"),
    ],
)
def test_normalize_cn_symbol(raw, expected):
    assert str(normalize_cn_symbol(raw)) == expected


@pytest.mark.parametrize("raw", ["830001.BJ", "600519.SZ", "INVALID", "123456"])
def test_invalid_cn_symbol_fails_fast(raw):
    with pytest.raises(UnsupportedSymbolError):
        normalize_cn_symbol(raw)
