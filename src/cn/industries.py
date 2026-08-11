"""Deterministic A-share industry classification — fixed mapping, no external API.

Every A-share stock is assigned a primary industry code and a secondary industry
code from the "Shenwan Level 1 / Level 2" classification system, frozen at the
2026-08 snapshot.  This module is a pure, offline lookup — it never queries a
provider or API.

Industry codes are used for:
  1. Deterministic peer selection (same Level-1 industry = eligible peer).
  2. Industry-average multiples for fair-value comparison.
  3. Validation checks (e.g., "is a bank using PE/PB only?").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Industry:
    code: str
    name: str
    level: int  # 1 = Shenwan Level-1, 2 = Shenwan Level-2


# ---------------------------------------------------------------------------
#  Shenwan Level-1 industries — the 31 standard sectors.
#  These are the primary peer-selection boundary.
# ---------------------------------------------------------------------------

L1_INDUSTRIES: Dict[str, Industry] = {
    "L1_01": Industry("L1_01", "食品饮料", 1),
    "L1_02": Industry("L1_02", "家用电器", 1),
    "L1_03": Industry("L1_03", "医药生物", 1),
    "L1_04": Industry("L1_04", "银行", 1),
    "L1_05": Industry("L1_05", "非银金融", 1),
    "L1_06": Industry("L1_06", "房地产", 1),
    "L1_07": Industry("L1_07", "电子", 1),
    "L1_08": Industry("L1_08", "计算机", 1),
    "L1_09": Industry("L1_09", "传媒", 1),
    "L1_10": Industry("L1_10", "通信", 1),
    "L1_11": Industry("L1_11", "电力设备", 1),
    "L1_12": Industry("L1_12", "国防军工", 1),
    "L1_13": Industry("L1_13", "汽车", 1),
    "L1_14": Industry("L1_14", "机械设备", 1),
    "L1_15": Industry("L1_15", "建筑装饰", 1),
    "L1_16": Industry("L1_16", "建筑材料", 1),
    "L1_17": Industry("L1_17", "钢铁", 1),
    "L1_18": Industry("L1_18", "有色金属", 1),
    "L1_19": Industry("L1_19", "基础化工", 1),
    "L1_20": Industry("L1_20", "石油石化", 1),
    "L1_21": Industry("L1_21", "煤炭", 1),
    "L1_22": Industry("L1_22", "交通运输", 1),
    "L1_23": Industry("L1_23", "商贸零售", 1),
    "L1_24": Industry("L1_24", "社会服务", 1),
    "L1_25": Industry("L1_25", "农林牧渔", 1),
    "L1_26": Industry("L1_26", "纺织服饰", 1),
    "L1_27": Industry("L1_27", "轻工制造", 1),
    "L1_28": Industry("L1_28", "公用事业", 1),
    "L1_29": Industry("L1_29", "环保", 1),
    "L1_30": Industry("L1_30", "综合", 1),
    "L1_31": Industry("L1_31", "美容护理", 1),
}

# ---------------------------------------------------------------------------
#  Stock → Industry mapping — frozen at 2026-08.
#  Covers the most-researched A-share stocks.  New stocks are added on demand.
#  Format: {stock_code: [L1_code, L2_code]}
#  L2 industries are omitted for brevity in this P0 snapshot.
# ---------------------------------------------------------------------------

_STOCK_INDUSTRY: Dict[str, str] = {
    # 食品饮料
    "600519": "L1_01",  # 贵州茅台
    "000858": "L1_01",  # 五粮液
    "000568": "L1_01",  # 泸州老窖
    "600809": "L1_01",  # 山西汾酒
    "002304": "L1_01",  # 洋河股份
    "000596": "L1_01",  # 古井贡酒
    "603369": "L1_01",  # 今世缘
    "600600": "L1_01",  # 青岛啤酒
    "000895": "L1_01",  # 双汇发展
    "603288": "L1_01",  # 海天味业
    "002714": "L1_01",  # 牧原股份 (also 农林牧渔, but main business is food)
    # 家用电器
    "000333": "L1_02",  # 美的集团
    "000651": "L1_02",  # 格力电器
    "600690": "L1_02",  # 海尔智家
    "002032": "L1_02",  # 苏泊尔
    # 医药生物
    "600276": "L1_03",  # 恒瑞医药
    "300760": "L1_03",  # 迈瑞医疗
    "000538": "L1_03",  # 云南白药
    "600196": "L1_03",  # 复星医药
    "002007": "L1_03",  # 华兰生物
    "300015": "L1_03",  # 爱尔眼科
    "603259": "L1_03",  # 药明康德
    # 银行
    "601398": "L1_04",  # 工商银行
    "601939": "L1_04",  # 建设银行
    "601288": "L1_04",  # 农业银行
    "601988": "L1_04",  # 中国银行
    "600036": "L1_04",  # 招商银行
    "601166": "L1_04",  # 兴业银行
    "000001": "L1_04",  # 平安银行
    "600016": "L1_04",  # 民生银行
    "002142": "L1_04",  # 宁波银行
    # 非银金融
    "601318": "L1_05",  # 中国平安
    "601628": "L1_05",  # 中国人寿
    "601601": "L1_05",  # 中国太保
    "600030": "L1_05",  # 中信证券
    # 房地产
    "000002": "L1_06",  # 万科A
    "001979": "L1_06",  # 招商蛇口
    "600048": "L1_06",  # 保利发展
    # 电子
    "000725": "L1_07",  # 京东方A
    "002415": "L1_07",  # 海康威视
    "600703": "L1_07",  # 三安光电
    "603501": "L1_07",  # 韦尔股份
    # 计算机
    "002230": "L1_08",  # 科大讯飞
    "000938": "L1_08",  # 紫光股份
    "600570": "L1_08",  # 恒生电子
    "688111": "L1_08",  # 金山办公
    # 电力设备
    "300750": "L1_11",  # 宁德时代
    "002594": "L1_11",  # 比亚迪 (also 汽车)
    "601012": "L1_11",  # 隆基绿能
    "300274": "L1_11",  # 阳光电源
    "600438": "L1_11",  # 通威股份
    # 汽车
    "000625": "L1_13",  # 长安汽车
    "600104": "L1_13",  # 上汽集团
    "601238": "L1_13",  # 广汽集团
    # 有色金属
    "601899": "L1_18",  # 紫金矿业
    "600547": "L1_18",  # 山东黄金
    "002460": "L1_18",  # 赣锋锂业
    # 基础化工
    "600309": "L1_19",  # 万华化学
    "002601": "L1_19",  # 龙佰集团
    # 交通运输
    "601006": "L1_22",  # 大秦铁路
    "002352": "L1_22",  # 顺丰控股
    # 国防军工
    "600760": "L1_12",  # 中航沈飞
    "002179": "L1_12",  # 中航光电
    # 通信
    "600941": "L1_10",  # 中国移动
    "601728": "L1_10",  # 中国电信
    # 公用事业
    "600900": "L1_28",  # 长江电力
    "601985": "L1_28",  # 中国核电
}


def get_industry(symbol_code: str) -> Optional[Industry]:
    """Look up the Shenwan Level-1 industry for a stock code.

    Returns None for unknown stocks (e.g., newly listed micro-caps not yet
    indexed in the frozen mapping).
    """
    code = symbol_code.strip()
    l1_code = _STOCK_INDUSTRY.get(code)
    if l1_code is None:
        return None
    return L1_INDUSTRIES.get(l1_code)


def get_industry_name(symbol_code: str) -> Optional[str]:
    ind = get_industry(symbol_code)
    return ind.name if ind else None


def get_industry_code(symbol_code: str) -> Optional[str]:
    ind = get_industry(symbol_code)
    return ind.code if ind else None


def is_financial_institution(symbol_code: str) -> bool:
    """Banks and insurers are assessed with PE/PB only (no PS)."""
    ind = get_industry(symbol_code)
    return ind is not None and ind.code in ("L1_04", "L1_05")


def industry_peers(symbol_code: str) -> List[str]:
    """Return all stock codes in the same Shenwan Level-1 industry."""
    l1_code = get_industry_code(symbol_code)
    if l1_code is None:
        return []
    return sorted(code for code, ind_code in _STOCK_INDUSTRY.items() if ind_code == l1_code and code != symbol_code)


def known_industries() -> Dict[str, Industry]:
    """Return all registered Shenwan Level-1 industries."""
    return dict(L1_INDUSTRIES)


def known_stocks() -> Dict[str, str]:
    """Return the full stock → L1-code mapping (read-only view)."""
    return dict(_STOCK_INDUSTRY)