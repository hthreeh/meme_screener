"""
DEX 价格监控 - 主入口点

加密货币价格监控工具，追踪 DexScreener 上的价格变化
并通过 Telegram 和飞书发送通知
支持多策略模拟交易系统
"""

import logging
import sys
from pathlib import Path

from config import load_settings
from core.browser import BrowserManager
from core.database import DatabaseManager
from core.api_client import DexScreenerAPI
from services.notifier import NotificationService
from services.data_store import DataStore
from services.price_monitor import PriceMonitor
from services.trading_strategies import create_all_strategies, StrategyType
from services.session_manager import SessionManager
from services.position_tracker import PositionTracker
from scheduler import TaskScheduler
from utils.logging_config import setup_logging as setup_file_logging


def setup_logging(log_dir: Path) -> None:
    """配置应用程序日志（控制台 + 文件）"""
    # 控制台输出
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )
    
    # 文件日志（分模块）
    setup_file_logging(log_dir)


def get_project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).parent


def main() -> None:
    """
    主应用程序入口点

    初始化所有服务并启动调度器
    """
    # 加载配置
    settings = load_settings()
    project_root = get_project_root()

    # 设置数据目录和日志目录
    data_dir = project_root / settings.data_dir
    data_dir.mkdir(exist_ok=True)
    log_dir = data_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    
    # 初始化日志系统
    setup_logging(log_dir)
    logger = logging.getLogger(__name__)
    logger.info("正在启动 DEX 价格监控系统（多策略模拟交易）- Jenkins CI/CD Test v1...")

    # 初始化数据库和 API
    db = DatabaseManager(data_dir / "dex_monitor.db")
    api = DexScreenerAPI()
    logger.info(f"数据库初始化完成: {db.get_database_stats()}")

    # 初始化通知服务（双通道）
    notifier = NotificationService(
        settings.email, 
        settings.telegram,
        settings.feishu
    )
    
    # Sniper 通知器（如果配置了）
    sniper_notifier = None
    if settings.telegram_sniper or settings.feishu_sniper:
        sniper_notifier = NotificationService(
            None,
            settings.telegram_sniper,
            settings.feishu_sniper
        )
        logger.info("Sniper 通知通道已启用")
    
    data_store = DataStore(data_dir)
    browser = BrowserManager(settings)
    
    # 创建多策略实例
    strategies = create_all_strategies(db, api, settings.strategies)
    logger.info(f"已加载 {len(strategies)} 个交易策略:")
    for st_type, strategy in strategies.items():
        logger.info(f"  - 策略{st_type.value}: {strategy.config.name} "
                    f"(每次{strategy.config.trade_amount_sol} SOL)")
    
    # 创建会话管理器

    session_manager = SessionManager(db, api)

    try:
        # 启动浏览器
        browser.start()
        
        # 启动会话管理器
        session_manager.start()
        
        # 创建止盈止损回调函数（发送飞书通知）
        def on_exit_triggered(st_type, result):
            if sniper_notifier:
                action = result.get("action", "EXIT")
                token_name = result.get("token_name", "Unknown")
                pnl = result.get("pnl", 0)
                pnl_pct = result.get("pnl_percent", 0)
                emoji = "🎉" if pnl > 0 else "❌"
                # 获取策略余额
                balance = 0.0
                if st_type in strategies:
                    balance = strategies[st_type].state.balance_sol
                
                # 获取代币 CA
                token_ca = result.get("token_ca", "")
                
                import asyncio
                exit_msg = (
                    f"{emoji} 【策略{st_type.value} {action}】{token_name}\n"
                    f"CA: <code>{token_ca}</code>\n"
                    f"PNL: {pnl:+.4f} SOL ({pnl_pct:+.1f}%)\n"
                    f"💵 余额: {balance:.2f} SOL"
                )
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(sniper_notifier.send_raw_message(exit_msg))
                except RuntimeError:
                    asyncio.run(sniper_notifier.send_raw_message(exit_msg))
        
        # 创建并启动持仓追踪器（独立于 Session 追踪持仓）
        position_tracker = PositionTracker(
            strategies=strategies,
            api=api,
            db=db,  # 传递数据库引用以缓存市值数据
            on_exit_callback=on_exit_triggered,
            settings=settings  # 传递配置以支持分段止损和趋势延期
        )
        position_tracker.start()

        # 创建价格监控器（集成新功能）
        monitor = PriceMonitor(
            settings=settings,
            browser=browser,
            notifier=notifier,
            data_store=data_store,
            data_dir=data_dir,
            db=db,
            strategies=strategies,
            session_manager=session_manager,
            sniper_notifier=sniper_notifier,
        )

        # 设置并启动调度器
        scheduler = TaskScheduler(settings, notifier)
        scheduler.register_task(monitor.run_cycle)
        scheduler.start(run_immediately=True)

    except KeyboardInterrupt:
        logger.info("收到关闭请求...")
    except Exception as e:
        logger.critical(f"致命错误: {e}", exc_info=True)
        notifier.send_error_notification(
            f"程序发生致命异常，停止运行: {e}",
            "【致命错误】DEX监控程序停止"
        )
        sys.exit(1)
    finally:
        # 停止会话管理器
        session_manager.stop()
        
        # 停止持仓追踪器
        if 'position_tracker' in locals():
            position_tracker.stop()
        
        # 输出所有策略最终状态
        logger.info("=" * 50)
        logger.info("所有策略最终状态:")
        for st_type, strategy in strategies.items():
            logger.info(strategy.get_summary())
        logger.info("=" * 50)
        
        browser.stop()
        logger.info("DEX 价格监控已停止")


if __name__ == "__main__":
    main()
