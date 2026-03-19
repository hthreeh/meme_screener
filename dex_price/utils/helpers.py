"""
DEX 价格监控 - 辅助工具函数
包含数据转换和格式化的纯函数
"""

import re
import logging
from typing import Optional


def convert_value_to_number(value_str: Optional[str]) -> float:
    """
    将市值/价格字符串转换为数字值

    支持的格式:
    - '$1.5K', '$2.3M', '$1.2B' - 带单位的格式
    - '$0.0₄9400' - 下标格式（₄表示4个零）
    - '$566', '$0.001234' - 普通数字格式

    参数:
        value_str: 市值/价格字符串

    返回:
        浮点数值，无效时返回 0.0
    """
    if not value_str or value_str in ("N/A", "-"):
        return 0.0
    
    # 清理字符串
    clean_str = value_str.strip()
    
    # 处理带 K/M/B 单位的格式 (如 $1.5M)
    match = re.match(r'^\$?([\d.]+)([KMB])$', clean_str)
    if match:
        num = float(match.group(1))
        unit = match.group(2)
        multipliers = {'K': 1_000, 'M': 1_000_000, 'B': 1_000_000_000}
        return num * multipliers.get(unit, 1)
    
    # 下标数字映射 (Unicode subscript digits)
    subscript_map = {
        '₀': 0, '₁': 1, '₂': 2, '₃': 3, '₄': 4,
        '₅': 5, '₆': 6, '₇': 7, '₈': 8, '₉': 9
    }
    
    # 处理下标格式 (如 $0.0₄9400 表示 $0.00009400)
    subscript_match = re.match(r'^\$?0\.0([₀₁₂₃₄₅₆₇₈₉])(\d+)$', clean_str)
    if subscript_match:
        zero_count = subscript_map.get(subscript_match.group(1), 0)
        significant = subscript_match.group(2)
        result = float(f"0.{'0' * zero_count}{significant}")
        return result
    
    # 处理普通数字格式 (如 $566, $0.001234)
    try:
        clean = clean_str.replace('$', '').replace(',', '').strip()
        if not clean:
            return 0.0
        return float(clean)
    except ValueError:
        pass
    
    logging.debug(f"无法解析的货币值格式: {value_str}")
    return 0.0


def format_rate_html(rate: float, highlight_threshold: float = 50.0) -> str:
    """
    格式化涨跌幅用于 HTML 邮件通知

    参数:
        rate: 百分比涨跌幅
        highlight_threshold: 超过此值时加粗显示

    返回:
        HTML 格式的涨跌幅字符串
    """
    if rate > highlight_threshold:
        return f"<strong>{rate:.2f}%</strong>"
    return f"{rate:.2f}%"


def format_rate_telegram(rate: float) -> str:
    """
    格式化涨跌幅用于 Telegram 通知

    参数:
        rate: 百分比涨跌幅

    返回:
        Telegram 格式的涨跌幅字符串
    """
    return f"<b>{rate:.2f}%</b>"


def check_page_validity(file_path: str, error_phrase: str = "请稍候",
                        required_phrase: str = "chakra-text custom-11dd6qx") -> bool:
    """
    检查保存的 HTML 页面是否存在加载问题

    参数:
        file_path: HTML 文件路径
        error_phrase: 表示页面仍在加载的短语
        required_phrase: 有效页面中应存在的短语

    返回:
        True 如果页面有问题，False 如果页面有效
    """
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
        return (error_phrase in content) or (required_phrase not in content)
    except Exception as e:
        logging.error(f"检查页面有效性出错 {file_path}: {e}")
        return True  # 出现异常视为页面有问题
