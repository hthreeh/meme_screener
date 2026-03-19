"""
DEX 价格监控 - HTML 解析模块
从保存的 HTML 页面中提取加密货币数据
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from models.currency import CurrencyData, GrowthRates, MarketData
from utils.helpers import convert_value_to_number


_logger = logging.getLogger(__name__)


# 各时间周期对应的 CSS 类名映射
TIME_FRAME_CLASSES = {
    "5M": "ds-dex-table-row-col-price-change-m5",
    "1H": "ds-dex-table-row-col-price-change-h1",
    "6H": "ds-dex-table-row-col-price-change-h6",
    "24H": "ds-dex-table-row-col-price-change-h24",
}

# 新增市场数据 CSS 类名映射
MARKET_DATA_CLASSES = {
    "price": "ds-dex-table-row-col-price",
    "liquidity": "ds-dex-table-row-col-liquidity",
    "volume": "ds-dex-table-row-col-volume",
    "txns": "ds-dex-table-row-col-txns",
    "makers": "ds-dex-table-row-col-makers",
    "pair_age": "ds-dex-table-row-col-pair-age",
}


def parse_currency_rows(file_path: Path, source_file: str = "") -> List[CurrencyData]:
    """
    从 HTML 文件解析货币数据

    参数:
        file_path: HTML 文件路径
        source_file: 来源文件标识符，用于追踪

    返回:
        CurrencyData 对象列表
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            html_content = file.read()

        soup = BeautifulSoup(html_content, 'html.parser')
        rows = soup.find_all(class_="ds-dex-table-row")

        # 记录找到的行数
        _logger.debug(f"[{source_file}] HTML 中找到 {len(rows)} 个表格行")

        currencies = []
        parse_failed_count = 0

        for row in rows:
            currency = _parse_single_row(row, source_file)
            if currency:
                currencies.append(currency)
            else:
                parse_failed_count += 1

        # 记录解析结果
        if parse_failed_count > 0:
            _logger.debug(f"[{source_file}] 解析失败 {parse_failed_count} 行")

        _logger.info(f"[{source_file}] 成功提取 {len(currencies)} 条货币数据")

        return currencies

    except Exception as e:
        _logger.error(f"[{source_file}] 解析文件失败: {e}", exc_info=True)
        return []


def _parse_single_row(row, source_file: str) -> Optional[CurrencyData]:
    """
    解析单个表格行为 CurrencyData

    参数:
        row: BeautifulSoup 行元素
        source_file: 来源文件标识符

    返回:
        CurrencyData 对象，解析失败返回 None
    """
    try:
        href = row.get('href')
        if not href:
            return None

        # 提取货币名称
        name_tag = row.find("span", class_="ds-dex-table-row-base-token-symbol")
        currency_name = name_tag.text.strip() if name_tag else "Unknown"

        # 从图片 URL 提取合约地址
        contract_address = _extract_contract_address(row)

        # 提取涨跌幅
        growth_rates = _extract_growth_rates(row)

        # 提取市值
        market_value_tag = row.find("div", class_="ds-table-data-cell ds-dex-table-row-col-market-cap")
        market_value = market_value_tag.text.strip() if market_value_tag else "N/A"
        market_value_num = convert_value_to_number(market_value)

        # 提取新增市场数据
        market_data = _extract_market_data(row)

        return CurrencyData(
            href=href,
            currency_name=currency_name,
            contract_address=contract_address,
            market_value=market_value,
            market_value_num=market_value_num,
            growth_rates=growth_rates,
            source_file=source_file,
            market_data=market_data,
        )

    except Exception as e:
        _logger.warning(f"[{source_file}] 解析行失败: {e}")
        return None


def _extract_contract_address(row) -> str:
    """
    从代币图标的图片 URL 中提取合约地址

    参数:
        row: BeautifulSoup 行元素

    返回:
        合约地址字符串，提取失败返回 "Unknown"
    """
    try:
        img_tag = row.find("img", class_="ds-dex-table-row-token-icon-img")
        if img_tag and 'src' in img_tag.attrs:
            src = img_tag.attrs['src']
            # 匹配模式: tokens/solana/{address}.png
            pattern = r'(?<=tokens\/solana\/)[^\/.]+(?=\.png)'
            match = re.search(pattern, src)
            if match:
                return match.group(0)
    except Exception:
        pass
    return "Unknown"


def _extract_growth_rates(row) -> GrowthRates:
    """
    提取各时间周期的涨跌幅

    参数:
        row: BeautifulSoup 行元素

    返回:
        GrowthRates 对象
    """
    rates = {}

    for timeframe, class_name in TIME_FRAME_CLASSES.items():
        try:
            change_tag = row.find("div", class_=class_name)
            if change_tag:
                span = change_tag.find("span", class_="ds-change-perc")
                if span:
                    value_text = span.text.strip()
                    if value_text != "-":
                        rates[timeframe] = float(value_text.strip('%').replace(',', ''))
                        continue
        except (ValueError, AttributeError):
            pass
        rates[timeframe] = 0.0

    return GrowthRates.from_dict(rates)


def _extract_market_data(row) -> MarketData:
    """
    提取市场数据（价格、流动性、交易量等）

    参数:
        row: BeautifulSoup 行元素

    返回:
        MarketData 对象
    """
    # 提取价格
    price_str = ""
    price = 0.0
    try:
        price_tag = row.find("div", class_=MARKET_DATA_CLASSES["price"])
        if price_tag:
            price_str = price_tag.text.strip()
            price = _parse_price(price_str)
    except Exception:
        pass

    # 提取流动性
    liquidity_str = ""
    liquidity = 0.0
    try:
        liq_tag = row.find("div", class_=MARKET_DATA_CLASSES["liquidity"])
        if liq_tag:
            liquidity_str = liq_tag.text.strip()
            liquidity = convert_value_to_number(liquidity_str)
    except Exception:
        pass

    # 提取交易量
    volume_str = ""
    volume = 0.0
    try:
        vol_tag = row.find("div", class_=MARKET_DATA_CLASSES["volume"])
        if vol_tag:
            volume_str = vol_tag.text.strip()
            volume = convert_value_to_number(volume_str)
    except Exception:
        pass

    # 提取交易次数
    txns = 0
    try:
        txns_tag = row.find("div", class_=MARKET_DATA_CLASSES["txns"])
        if txns_tag:
            txns_text = txns_tag.text.strip().replace(',', '')
            txns = int(txns_text) if txns_text.isdigit() else 0
    except Exception:
        pass

    # 提取交易钱包数
    makers = 0
    try:
        makers_tag = row.find("div", class_=MARKET_DATA_CLASSES["makers"])
        if makers_tag:
            makers_text = makers_tag.text.strip().replace(',', '')
            makers = int(makers_text) if makers_text.isdigit() else 0
    except Exception:
        pass

    # 提取交易对年龄
    pair_age = ""
    try:
        age_tag = row.find("div", class_=MARKET_DATA_CLASSES["pair_age"])
        if age_tag:
            span = age_tag.find("span")
            pair_age = span.text.strip() if span else age_tag.text.strip()
    except Exception:
        pass

    return MarketData(
        price=price,
        price_str=price_str,
        liquidity=liquidity,
        liquidity_str=liquidity_str,
        volume_24h=volume,
        volume_24h_str=volume_str,
        txns_24h=txns,
        makers_24h=makers,
        pair_age=pair_age,
    )


def _parse_price(price_str: str) -> float:
    """
    解析价格字符串为浮点数

    参数:
        price_str: 价格字符串，如 "$0.004549"

    返回:
        浮点数价格
    """
    try:
        # 移除 $ 符号和逗号
        clean = price_str.replace('$', '').replace(',', '').strip()
        if not clean or clean == '-':
            return 0.0
        return float(clean)
    except (ValueError, AttributeError):
        return 0.0

