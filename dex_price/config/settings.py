"""
DEX 价格监控 - 配置模块
定义配置数据类和加载函数
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


@dataclass
class EmailConfig:
    """邮件通知配置（已禁用）"""
    to_email: str
    from_email: str
    smtp_server: str
    smtp_port: int
    password: str


@dataclass
class TelegramConfig:
    """Telegram 通知配置"""
    telegram_bot_token: str
    telegram_chat_id: str
    connect_timeout: float = 90.0
    read_timeout: float = 90.0


@dataclass
class FeishuConfig:
    """飞书 Webhook 通知配置"""
    webhook_url: str


@dataclass
class ThresholdSettings:
    """价格变化阈值配置"""
    default: float = 30.0
    above_1m: float = 25.0
    above_10m: float = 20.0

    def get_threshold(self, market_value: float) -> float:
        """根据市值获取适当的阈值"""
        if market_value > 10_000_000:
            return self.above_10m
        elif market_value > 1_000_000:
            return self.above_1m
        return self.default


@dataclass
class StagedStopLossLevel:
    """分段止损级别"""
    trigger: float  # 触发百分比 (如 -0.15 = -15%)
    sell_ratio: float  # 卖出比例 (如 0.5 = 50%)


@dataclass
class StagedStopLossConfig:
    """分段止损配置"""
    enabled: bool = True
    level_1: StagedStopLossLevel = None  # 跌15%减仓50%
    level_2: StagedStopLossLevel = None  # 跌30%清仓
    
    def __post_init__(self):
        if self.level_1 is None:
            self.level_1 = StagedStopLossLevel(trigger=-0.15, sell_ratio=0.5)
        if self.level_2 is None:
            self.level_2 = StagedStopLossLevel(trigger=-0.30, sell_ratio=1.0)


@dataclass
class TrendExtensionConfig:
    """趋势延期配置"""
    enabled: bool = False  # 默认关闭（报告标注"可选"）
    threshold: float = 0.10  # 涨10%触发延期
    extension_minutes: int = 30  # 延期30分钟
    max_times: int = 2  # 最多延期2次


@dataclass
class AppSettings:
    """应用程序全局设置"""
    # 浏览器设置
    num_pages: int = 5
    browser_restart_interval: int = 24  # 每 24 个周期（2小时）重启
    base_url: str = "https://dexscreener.com/watchlist/Fe0Mqc2lqxhEw03Lk8Od"
    page_load_wait: float = 3.0
    click_wait: float = 0.2

    # 任务调度
    task_interval_minutes: int = 5

    # 周期性检查间隔（分钟）
    check_intervals: Dict[str, int] = field(default_factory=lambda: {
        "20分钟": 20,
        "1小时": 60,
        "4小时": 240,
    })

    # 数据路径
    data_dir: str = "data"
    config_dir: str = "config"

    # 阈值
    thresholds: ThresholdSettings = field(default_factory=ThresholdSettings)

    # 通知设置（分别加载）
    email: Optional[EmailConfig] = None
    telegram: Optional[TelegramConfig] = None
    feishu: Optional[FeishuConfig] = None
    
    # Sniper 通知通道（API 信号专用）
    telegram_sniper: Optional[TelegramConfig] = None
    feishu_sniper: Optional[FeishuConfig] = None
    
    # 策略配置
    strategies: Dict = field(default_factory=dict)
    take_profit: Dict = field(default_factory=dict)
    stop_loss_percent: float = -50.0
    
    # 分段止损配置
    staged_stop_loss: StagedStopLossConfig = field(default_factory=StagedStopLossConfig)
    
    # 趋势延期配置（默认关闭）
    trend_extension: TrendExtensionConfig = field(default_factory=TrendExtensionConfig)


def get_project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).parent.parent


def load_notification_config(config_path: Optional[str] = None) -> Dict:
    """从 JSON 文件加载通知配置"""
    if config_path is None:
        config_path = get_project_root() / "config" / "email.json"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"配置文件未找到: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_settings(config_path: Optional[str] = None) -> AppSettings:
    """
    加载应用程序设置
    将默认设置与 JSON 中的通知配置合并
    """
    settings = AppSettings()

    try:
        config = load_notification_config(config_path)

        # 邮件配置（已禁用，但仍加载以备将来启用）
        if 'email' in config:
            settings.email = EmailConfig(**config['email'])

        if 'telegram' in config:
            settings.telegram = TelegramConfig(**config['telegram'])

        if 'feishu' in config:
            settings.feishu = FeishuConfig(**config['feishu'])
        
        # Sniper 通道
        if 'telegram_sniper' in config:
            settings.telegram_sniper = TelegramConfig(**config['telegram_sniper'])
        
        if 'feishu_sniper' in config:
            settings.feishu_sniper = FeishuConfig(**config['feishu_sniper'])
        
        # 策略配置
        if 'strategies' in config:
            settings.strategies = config['strategies']
        
        if 'take_profit' in config:
            settings.take_profit = config['take_profit']
        
        if 'stop_loss_percent' in config:
            settings.stop_loss_percent = config['stop_loss_percent']
        
        # 分段止损配置
        if 'staged_stop_loss' in config:
            ssl_cfg = config['staged_stop_loss']
            settings.staged_stop_loss = StagedStopLossConfig(
                enabled=ssl_cfg.get('enabled', True),
                level_1=StagedStopLossLevel(
                    trigger=ssl_cfg.get('level_1', {}).get('trigger', -0.15),
                    sell_ratio=ssl_cfg.get('level_1', {}).get('sell_ratio', 0.5)
                ),
                level_2=StagedStopLossLevel(
                    trigger=ssl_cfg.get('level_2', {}).get('trigger', -0.30),
                    sell_ratio=ssl_cfg.get('level_2', {}).get('sell_ratio', 1.0)
                )
            )
        
        # 趋势延期配置
        if 'trend_extension' in config:
            te_cfg = config['trend_extension']
            settings.trend_extension = TrendExtensionConfig(
                enabled=te_cfg.get('enabled', False),
                threshold=te_cfg.get('threshold', 0.10),
                extension_minutes=te_cfg.get('extension_minutes', 30),
                max_times=te_cfg.get('max_times', 2)
            )

    except FileNotFoundError as e:
        import logging
        logging.warning(f"通知配置加载失败: {e}")

    return settings


def load_url_mappings(config_path: Optional[str] = None) -> Dict[str, str]:
    """从 JSON 文件加载 URL 映射"""
    if config_path is None:
        config_path = get_project_root() / "config" / "url_mappings.json"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"URL 映射文件未找到: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


# 数据库路径常量（供 API 模块使用）
DB_PATH = get_project_root() / "data" / "dex_monitor.db"
