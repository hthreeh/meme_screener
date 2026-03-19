"""
新策略测试脚本
验证 StrategyG、StrategyH、StrategyR 的核心功能
"""

import sys
import os
import logging
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.trading_strategies import (
    StrategyType, StrategyG, StrategyH, StrategyR, StrategyConfig
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)


class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
    
    def record(self, name, condition, detail=""):
        if condition:
            self.passed += 1
            logger.info(f"✅ {name}: PASSED {detail}")
        else:
            self.failed += 1
            logger.error(f"❌ {name}: FAILED {detail}")


def test_strategy_g():
    """测试策略G：金狗狙击"""
    result = TestResult()
    logger.info("\n" + "=" * 60)
    logger.info("测试策略G：金狗狙击 (Golden Dog Sniper)")
    logger.info("=" * 60)
    
    mock_db = MagicMock()
    mock_api = MagicMock()
    config = StrategyConfig(name="金狗狙击", trade_amount_sol=0.2)
    strategy = StrategyG(StrategyType.G, config, mock_db, mock_api)
    
    # 验证自定义止盈止损
    result.record(
        "G - 自定义TP级别",
        strategy.TAKE_PROFIT_LEVELS == [(1.5, 0.5), (3.0, 0.3), (50.0, 0.2)],
        f"TP={strategy.TAKE_PROFIT_LEVELS}"
    )
    result.record(
        "G - 自定义SL",
        strategy.STOP_LOSS_PERCENT == -30.0,
        f"SL={strategy.STOP_LOSS_PERCENT}%"
    )
    
    # 测试should_buy - 满足所有条件
    session_data_good = {
        "signals": [{"type": "5m"}],
        "current_market_cap": 200_000,  # 在 $50K-$800K 范围内
        "api_data": {
            "txns_m5_buys": 30,    # > 20
            "txns_m5_sells": 15,   # 买卖比 = 2.0 > 1.5
            "volume_m5": 15_000,   # 15K / 200K = 7.5% > 5%
        }
    }
    result.record(
        "G - should_buy (满足条件)",
        strategy.should_buy(1, "CA", session_data_good) == True,
        "5m信号+市值范围内+量能OK"
    )
    
    # 测试should_buy - 市值超范围
    session_data_mc_high = {**session_data_good, "current_market_cap": 1_000_000}
    result.record(
        "G - should_buy (市值超范围)",
        strategy.should_buy(1, "CA", session_data_mc_high) == False,
        "市值=$1M > $800K"
    )
    
    # 测试should_buy - 买入笔数不足
    session_data_low_buys = {
        **session_data_good,
        "api_data": {"txns_m5_buys": 10, "txns_m5_sells": 5, "volume_m5": 15_000}
    }
    result.record(
        "G - should_buy (买入笔数不足)",
        strategy.should_buy(1, "CA", session_data_low_buys) == False,
        "5m买入=10 <= 20"
    )
    
    return result


def test_strategy_h():
    """测试策略H：钻石手趋势"""
    result = TestResult()
    logger.info("\n" + "=" * 60)
    logger.info("测试策略H：钻石手趋势 (Diamond Hand Trend)")
    logger.info("=" * 60)
    
    mock_db = MagicMock()
    mock_api = MagicMock()
    config = StrategyConfig(name="钻石手趋势", trade_amount_sol=0.3)
    strategy = StrategyH(StrategyType.H, config, mock_db, mock_api)
    
    # 验证自定义止盈止损
    result.record(
        "H - 自定义TP级别",
        strategy.TAKE_PROFIT_LEVELS == [(3.0, 0.3), (10.0, 0.4), (50.0, 0.3)],
        f"TP={strategy.TAKE_PROFIT_LEVELS}"
    )
    result.record(
        "H - 自定义SL",
        strategy.STOP_LOSS_PERCENT == -50.0,
        f"SL={strategy.STOP_LOSS_PERCENT}%"
    )
    
    # 测试should_buy - 满足所有条件
    session_data_good = {
        "signals": [{"type": "1h"}],
        "current_market_cap": 500_000,  # > $300K
        "heat_score": 250,              # > 200
        "highest_market_cap": 550_000,  # 回撤 = 9% < 20%
        "api_data": {"txns_h1_buys": 80}  # > 50
    }
    result.record(
        "H - should_buy (满足条件)",
        strategy.should_buy(1, "CA", session_data_good) == True,
        "1h信号+高热度+低回撤"
    )
    
    # 测试should_buy - 热度不足
    session_data_low_heat = {**session_data_good, "heat_score": 150}
    result.record(
        "H - should_buy (热度不足)",
        strategy.should_buy(1, "CA", session_data_low_heat) == False,
        "热度=150 < 200"
    )
    
    # 测试should_buy - 回撤过大
    session_data_drawdown = {**session_data_good, "highest_market_cap": 800_000}  # 回撤 = 37.5%
    result.record(
        "H - should_buy (回撤过大)",
        strategy.should_buy(1, "CA", session_data_drawdown) == False,
        "回撤=37.5% > 20%"
    )
    
    return result


def test_strategy_r():
    """测试策略R：复活反转"""
    result = TestResult()
    logger.info("\n" + "=" * 60)
    logger.info("测试策略R：复活反转 (Resurrection Reversal)")
    logger.info("=" * 60)
    
    mock_db = MagicMock()
    mock_api = MagicMock()
    config = StrategyConfig(name="复活反转", trade_amount_sol=0.15)
    strategy = StrategyR(StrategyType.R, config, mock_db, mock_api)
    
    # 验证自定义止盈止损
    result.record(
        "R - 自定义TP级别",
        strategy.TAKE_PROFIT_LEVELS == [(1.8, 0.7), (4.0, 0.3)],
        f"TP={strategy.TAKE_PROFIT_LEVELS}"
    )
    result.record(
        "R - 自定义SL",
        strategy.STOP_LOSS_PERCENT == -20.0,
        f"SL={strategy.STOP_LOSS_PERCENT}%"
    )
    
    # 测试should_buy - 满足所有条件
    session_data_good = {
        "signals": [{"type": "20m"}],
        "is_returning_token": True,     # 老用户
        "api_data": {
            "liquidity_usd": 50_000,    # > $20K
            "txns_h1_buys": 50,         # > 30
            "txns_h1_sells": 30         # 买入 > 卖出
        }
    }
    result.record(
        "R - should_buy (满足条件)",
        strategy.should_buy(1, "CA", session_data_good) == True,
        "20m信号+老用户+流动性OK"
    )
    
    # 测试should_buy - 非老用户
    session_data_new = {**session_data_good, "is_returning_token": False}
    result.record(
        "R - should_buy (非老用户)",
        strategy.should_buy(1, "CA", session_data_new) == False,
        "is_returning_token=False"
    )
    
    # 测试should_buy - 卖出多于买入
    session_data_sells = {
        **session_data_good,
        "api_data": {"liquidity_usd": 50_000, "txns_h1_buys": 40, "txns_h1_sells": 50}
    }
    result.record(
        "R - should_buy (卖出多于买入)",
        strategy.should_buy(1, "CA", session_data_sells) == False,
        "买入=40 <= 卖出=50"
    )
    
    return result


def main():
    logger.info("=" * 60)
    logger.info("新策略测试 - 开始")
    logger.info("=" * 60)
    
    results = []
    results.append(test_strategy_g())
    results.append(test_strategy_h())
    results.append(test_strategy_r())
    
    total_passed = sum(r.passed for r in results)
    total_failed = sum(r.failed for r in results)
    
    logger.info("\n" + "=" * 60)
    logger.info(f"总体结果: 通过={total_passed}, 失败={total_failed}")
    logger.info("=" * 60)
    
    if total_failed == 0:
        logger.info("🎉 所有新策略测试通过！")
        return 0
    else:
        logger.error("⚠️ 存在失败的测试")
        return 1


if __name__ == "__main__":
    sys.exit(main())
