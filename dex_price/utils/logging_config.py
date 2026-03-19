"""
DEX 价格监控 - 日志配置模块

为不同模块配置独立的日志文件，支持：
- 分模块日志记录
- 日志轮转（按天）
- 自动清理超过7天的日志
"""

import logging
import os
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Dict, List


class LoggerManager:
    """日志管理器"""
    
    # 日志保留天数
    LOG_RETENTION_DAYS = 7
    
    # 日志格式
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
    
    # 模块名称前缀 -> 日志文件映射
    # 键是 logger 名称的前缀，值是对应的日志文件
    MODULE_MAPPINGS = {
        'services.session_manager': 'session_manager.log',
        'services.trading_strategies': 'trading_strategies.log',
        'core.api_client': 'api_client.log',
        'services.price_monitor': 'price_monitor.log',
        'services.notifier': 'notifications.log',
        '__main__': 'main.log',
        # v3.1 新增专用日志
        'alerts': 'alerts.log',           # 预警记录（含策略触发情况）
        'trades': 'trades.log',           # 买入/卖出交易记录
        'positions': 'positions.log',     # 持仓状态追踪
        'scanner': 'scanner.log',         # Scanner 通知消息完整记录
        'manual_trades': 'manual_trades.log', # 手动交易专用日志
    }
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if LoggerManager._initialized:
            return
        LoggerManager._initialized = True
        
        self.log_dir: Path = None
        self.file_handlers: Dict[str, TimedRotatingFileHandler] = {}
        
    def setup(self, log_dir: Path) -> None:
        """初始化日志系统"""
        self.log_dir = log_dir
        self.log_dir.mkdir(exist_ok=True)
        
        # 清理旧日志
        self._cleanup_old_logs()
        
        # 为每个模块创建专用的文件处理器并直接附加
        for module_name, log_file in self.MODULE_MAPPINGS.items():
            handler = self._create_file_handler(log_file)
            self.file_handlers[module_name] = handler
            
            # 直接附加到对应模块的 logger
            logger = logging.getLogger(module_name)
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)
        
        # 同时创建一个主日志文件，记录所有日志
        main_handler = self._create_file_handler('all.log')
        root_logger = logging.getLogger()
        root_logger.addHandler(main_handler)
            
        print(f"[日志系统] 初始化完成，日志目录: {self.log_dir}")
        
    def _create_file_handler(self, log_file: str) -> TimedRotatingFileHandler:
        """创建文件处理器"""
        log_path = self.log_dir / log_file
        
        handler = TimedRotatingFileHandler(
            log_path,
            when='midnight',
            interval=1,
            backupCount=self.LOG_RETENTION_DAYS,
            encoding='utf-8'
        )
        handler.setFormatter(logging.Formatter(self.LOG_FORMAT, self.DATE_FORMAT))
        handler.setLevel(logging.DEBUG)
        
        return handler
        
    def _cleanup_old_logs(self) -> None:
        """清理超过保留期限的日志文件"""
        if not self.log_dir or not self.log_dir.exists():
            return
            
        cutoff_date = datetime.now() - timedelta(days=self.LOG_RETENTION_DAYS)
        cleaned_count = 0
        
        for log_file in self.log_dir.glob('*.log*'):
            try:
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                if mtime < cutoff_date:
                    log_file.unlink()
                    cleaned_count += 1
            except Exception:
                pass
                
        if cleaned_count > 0:
            print(f"[日志系统] 已清理 {cleaned_count} 个过期日志文件")


# 全局实例
_logger_manager = LoggerManager()


def setup_logging(log_dir: Path) -> None:
    """初始化日志系统（在 main.py 中调用）"""
    _logger_manager.setup(log_dir)
