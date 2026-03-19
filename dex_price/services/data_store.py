"""
DEX 价格监控 - 数据持久化服务
处理 JSON 数据文件的读写
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

from models.currency import CurrencyData


class DataStore:
    """
    管理价格监控器的持久化数据存储

    处理:
    - 当前市值（5分钟快照）
    - 周期性比较数据（20分钟、1小时、4小时）
    - 通知历史
    """

    def __init__(self, data_dir: Path):
        """
        初始化数据存储

        参数:
            data_dir: 数据文件目录
        """
        self.data_dir = data_dir
        self._logger = logging.getLogger(__name__)

        # 确保数据目录存在
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 文件路径
        self.current_data_file = self.data_dir / "currency_value_data.json"
        self.history_file = self.data_dir / "email_results.json"

    def get_periodic_data_file(self, interval_minutes: int) -> Path:
        """获取周期性比较数据文件路径"""
        return self.data_dir / f"currency_value_data_{interval_minutes}min.json"

    def save_current_data(self, data: Dict[str, CurrencyData]) -> None:
        """
        保存当前周期的货币数据

        参数:
            data: href 到 CurrencyData 的字典
        """
        serialized = {href: currency.to_dict() for href, currency in data.items()}
        self._save_json(self.current_data_file, serialized)
        self._logger.info(f"已保存 {len(serialized)} 条数据到 {self.current_data_file.name}")

    def load_current_data(self) -> Dict[str, Dict[str, Any]]:
        """
        加载当前周期的货币数据

        返回:
            href 到货币数据字典的映射
        """
        return self._load_json(self.current_data_file, {})

    def save_periodic_data(self, data: Dict[str, CurrencyData],
                           interval_minutes: int) -> None:
        """
        保存周期性比较数据

        参数:
            data: href 到 CurrencyData 的字典
            interval_minutes: 间隔分钟数（20、60、240）
        """
        file_path = self.get_periodic_data_file(interval_minutes)
        serialized = {href: currency.to_dict() for href, currency in data.items()}
        self._save_json(file_path, serialized)
        self._logger.info(f"已保存 {len(serialized)} 条数据到 {file_path.name}")

    def load_periodic_data(self, interval_minutes: int) -> Dict[str, Dict[str, Any]]:
        """
        加载周期性比较数据

        参数:
            interval_minutes: 间隔分钟数

        返回:
            href 到货币数据字典的映射
        """
        file_path = self.get_periodic_data_file(interval_minutes)
        return self._load_json(file_path, {})

    def save_notification_history(self, html_snippets: List[str]) -> None:
        """
        追加通知到历史记录并保存

        参数:
            html_snippets: HTML 通知片段列表
        """
        history = self._load_json(self.history_file, [])
        history.append(html_snippets)

        # 只保留最近 20 批
        history = history[-20:]

        self._save_json(self.history_file, history)

    def load_notification_history(self) -> List[List[str]]:
        """
        加载通知历史

        返回:
            通知批次列表
        """
        return self._load_json(self.history_file, [])

    def count_occurrences(self, href: str, period_name: Optional[str] = None) -> int:
        """
        统计某货币在通知中出现的次数

        参数:
            href: 货币 href 标识符
            period_name: 可选的周期名称过滤

        返回:
            出现次数
        """
        history = self.load_notification_history()
        count = 0

        for batch in history:
            for item in batch:
                if href in item:
                    if period_name is None or period_name in item:
                        count += 1

        return count

    def _save_json(self, file_path: Path, data: Any) -> None:
        """保存数据到 JSON 文件"""
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            self._logger.error(f"保存 {file_path} 失败: {e}", exc_info=True)

    def _load_json(self, file_path: Path, default: Any) -> Any:
        """从 JSON 文件加载数据"""
        if not file_path.exists():
            return default

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            self._logger.error(f"加载 {file_path} 失败: {e}", exc_info=True)
            return default
