"""
Configuration package for DEX Price Monitor.
Provides centralized settings management.
"""

from .settings import (
    AppSettings,
    ThresholdSettings,
    EmailConfig,
    TelegramConfig,
    FeishuConfig,
    load_settings,
    load_url_mappings,
)

__all__ = [
    "AppSettings",
    "ThresholdSettings",
    "EmailConfig",
    "TelegramConfig",
    "FeishuConfig",
    "load_settings",
    "load_url_mappings",
]
