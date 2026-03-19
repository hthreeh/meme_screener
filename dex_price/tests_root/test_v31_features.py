"""
v3.1 功能测试套件
测试新增的日志系统、持仓追踪和交易记录功能

运行方式: python test_v31_features.py
"""

import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

# 修复 Windows 控制台 UTF-8 输出
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 设置测试日志目录
TEST_LOG_DIR = Path(__file__).parent / "data" / "logs"
TEST_LOG_DIR.mkdir(parents=True, exist_ok=True)

# 初始化日志系统
from utils.logging_config import setup_logging
setup_logging(TEST_LOG_DIR)

# 导入被测模块
from services.trading_strategies import (
    TradingStrategy, StrategyType, StrategyConfig, StrategyState, Position,
    StrategyA, StrategyB, StrategyC, StrategyD, StrategyF, create_all_strategies
)
from services.position_tracker import PositionTracker


class TestResult:
    """测试结果收集器"""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def record(self, name: str, passed: bool, error: str = None):
        if passed:
            self.passed += 1
            print(f"  ✅ {name}")
        else:
            self.failed += 1
            self.errors.append((name, error))
            print(f"  ❌ {name}: {error}")
    
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*50}")
        print(f"测试结果: {self.passed}/{total} 通过")
        if self.errors:
            print(f"\n失败的测试:")
            for name, error in self.errors:
                print(f"  - {name}: {error}")
        print(f"{'='*50}")
        return self.failed == 0


def test_logger_initialization():
    """测试 1：验证新日志器是否正确初始化"""
    print("\n📋 测试 1: 日志器初始化")
    result = TestResult()
    
    # 检查所有新日志器
    loggers = ['alerts', 'trades', 'positions', 'scanner']
    
    for logger_name in loggers:
        logger = logging.getLogger(logger_name)
        has_handlers = len(logger.handlers) > 0 or len(logging.getLogger().handlers) > 0
        result.record(f"日志器 '{logger_name}' 已配置", has_handlers, 
                     "没有配置文件处理器" if not has_handlers else None)
    
    return result.summary()


def test_trade_logging():
    """测试 2：验证交易日志记录功能"""
    print("\n📋 测试 2: 交易日志记录")
    result = TestResult()
    
    # 创建模拟的数据库和 API
    mock_db = Mock()
    mock_db.record_multi_strategy_trade = Mock()
    
    mock_api = Mock()
    
    # 创建策略配置
    config = StrategyConfig(
        name="测试策略",
        trade_amount_sol=0.1,
        initial_balance_sol=100.0
    )
    
    # 创建策略 B 实例
    strategy = StrategyB(StrategyType.B, config, mock_db, mock_api)
    
    # 测试买入
    position = strategy.execute_buy(
        token_id=12345,
        token_ca="TestCA123",
        token_name="TestToken",
        current_market_cap=500000
    )
    
    result.record("买入执行成功", position is not None, 
                 "返回 None" if position is None else None)
    
    if position:
        result.record("持仓记录正确", 
                     position.token_name == "TestToken" and position.buy_market_cap == 500000,
                     f"实际: {position.token_name}, {position.buy_market_cap}")
        
        result.record("余额扣减正确", 
                     strategy.state.balance_sol == 99.9,
                     f"实际余额: {strategy.state.balance_sol}")
        
        result.record("数据库记录已调用",
                     mock_db.record_multi_strategy_trade.called,
                     "未调用数据库记录")
    
    # 检查 trades 日志文件
    trades_log = TEST_LOG_DIR / "trades.log"
    if trades_log.exists():
        with open(trades_log, 'r', encoding='utf-8') as f:
            content = f.read()
            result.record("trades.log 包含 BUY 记录",
                         "BUY" in content and "TestToken" in content,
                         "未找到买入记录")
    else:
        result.record("trades.log 文件存在", False, "文件不存在")
    
    return result.summary()


def test_position_tracking():
    """测试 3：验证持仓追踪功能"""
    print("\n📋 测试 3: 持仓追踪")
    result = TestResult()
    
    # 创建模拟的策略和 API
    mock_db = Mock()
    mock_db.record_multi_strategy_trade = Mock()
    mock_api = Mock()
    
    # 模拟 API 返回市值数据
    mock_api.get_token_data_raw = Mock(return_value=[{"marketCap": 750000}])
    
    config = StrategyConfig(
        name="测试策略",
        trade_amount_sol=0.1,
        initial_balance_sol=100.0
    )
    
    strategy = StrategyB(StrategyType.B, config, mock_db, mock_api)
    
    # 先买入
    strategy.execute_buy(
        token_id=12345,
        token_ca="TestCA123",
        token_name="TestToken",
        current_market_cap=500000
    )
    
    strategies = {StrategyType.B: strategy}
    
    # 创建持仓追踪器
    exit_results = []
    def on_exit(st_type, result):
        exit_results.append((st_type, result))
    
    tracker = PositionTracker(strategies, mock_api, on_exit_callback=on_exit)
    
    result.record("PositionTracker 初始化成功", tracker is not None)
    result.record("检测到持仓", tracker.get_position_count() == 1,
                 f"实际持仓数: {tracker.get_position_count()}")
    
    # 手动触发一次轮询
    tracker._poll_all_positions()
    
    result.record("API 市值查询已调用",
                 mock_api.get_token_data_raw.called,
                 "未调用 API")
    
    # 检查 positions 日志
    positions_log = TEST_LOG_DIR / "positions.log"
    if positions_log.exists():
        with open(positions_log, 'r', encoding='utf-8') as f:
            content = f.read()
            result.record("positions.log 包含持仓记录",
                         "TestToken" in content,
                         "未找到持仓记录")
    else:
        result.record("positions.log 文件存在", False, "文件不存在")
    
    return result.summary()


def test_strategy_conditions():
    """测试 4：验证策略买入条件"""
    print("\n📋 测试 4: 策略买入条件")
    result = TestResult()
    
    mock_db = Mock()
    mock_api = Mock()
    
    config = StrategyConfig(name="测试", trade_amount_sol=0.1)
    
    # 测试 Strategy A: 热度>=150 或 5m+20m组合
    strategy_a = StrategyA(StrategyType.A, config, mock_db, mock_api)
    
    # 条件 1: 热度 >= 150
    session_data_1 = {"heat_score": 150, "signals": []}
    result.record("策略A: 热度150触发", 
                 strategy_a.should_buy(1, "ca", session_data_1))
    
    session_data_2 = {"heat_score": 100, "signals": []}
    result.record("策略A: 热度100不触发", 
                 not strategy_a.should_buy(1, "ca", session_data_2))
    
    # 条件 2: 5m + 20m 组合
    session_data_3 = {
        "heat_score": 50,
        "signals": [{"type": "5m"}, {"type": "20m"}]
    }
    result.record("策略A: 5m+20m组合触发", 
                 strategy_a.should_buy(1, "ca", session_data_3))
    
    # 测试 Strategy B: 连续两次 5m
    strategy_b = StrategyB(StrategyType.B, config, mock_db, mock_api)
    
    session_data_4 = {"signals": [{"type": "5m"}, {"type": "5m"}]}
    result.record("策略B: 两次5m触发", 
                 strategy_b.should_buy(1, "ca", session_data_4))
    
    session_data_5 = {"signals": [{"type": "5m"}]}
    result.record("策略B: 一次5m不触发", 
                 not strategy_b.should_buy(1, "ca", session_data_5))
    
    # 测试 Strategy C: 5m + 涨幅50%
    strategy_c = StrategyC(StrategyType.C, config, mock_db, mock_api)
    
    session_data_6 = {
        "signals": [{"type": "5m"}],
        "initial_market_cap": 100000,
        "current_market_cap": 160000  # +60%
    }
    result.record("策略C: 5m+60%涨幅触发", 
                 strategy_c.should_buy(1, "ca", session_data_6))
    
    session_data_7 = {
        "signals": [{"type": "5m"}],
        "initial_market_cap": 100000,
        "current_market_cap": 130000  # +30%
    }
    result.record("策略C: 5m+30%涨幅不触发", 
                 not strategy_c.should_buy(1, "ca", session_data_7))
    
    return result.summary()


def test_stop_loss_take_profit():
    """测试 5：验证止盈止损功能"""
    print("\n📋 测试 5: 止盈止损")
    result = TestResult()
    
    mock_db = Mock()
    mock_db.record_multi_strategy_trade = Mock()
    mock_api = Mock()
    
    config = StrategyConfig(name="测试", trade_amount_sol=0.1, initial_balance_sol=100.0)
    strategy = StrategyB(StrategyType.B, config, mock_db, mock_api)
    
    # 买入
    strategy.execute_buy(
        token_id=12345,
        token_ca="TestCA",
        token_name="TestToken",
        current_market_cap=100000
    )
    
    initial_balance = strategy.state.balance_sol
    
    # 测试止盈 2x
    market_caps_2x = {12345: 200000}  # 2x
    exits_2x = strategy.check_and_execute_exits(market_caps_2x)
    
    result.record("2x 止盈触发", len(exits_2x) == 1, f"实际: {len(exits_2x)}")
    
    if exits_2x:
        result.record("止盈类型正确", 
                     exits_2x[0].get("action") == "TAKE_PROFIT_2x",
                     f"实际: {exits_2x[0].get('action')}")
        
        # 检查余额增加（卖出50%，2倍）
        expected_sell_value = 0.1 * 0.5 * 2  # 0.1 SOL
        result.record("余额增加正确",
                     strategy.state.balance_sol > initial_balance,
                     f"余额: {strategy.state.balance_sol}")
    
    # 确认持仓还在（只卖了一半）
    result.record("持仓剩余50%",
                 12345 in strategy.state.positions,
                 "持仓已被完全移除")
    
    if 12345 in strategy.state.positions:
        result.record("剩余比例正确",
                     abs(strategy.state.positions[12345].remaining_ratio - 0.5) < 0.01,
                     f"实际比例: {strategy.state.positions[12345].remaining_ratio}")
    
    return result.summary()


def test_alerts_logging():
    """测试 6：验证预警日志记录"""
    print("\n📋 测试 6: 预警日志记录")
    result = TestResult()
    
    # 直接测试 alerts logger
    alerts_logger = logging.getLogger('alerts')
    
    # 写入测试预警
    test_alert = "5m | TestToken | 热度=120 | 市值=$500K | 策略触发: A=N, B=Y, C=N, D=N, F=N"
    alerts_logger.info(test_alert)
    
    # 给一点时间让日志写入
    time.sleep(0.1)
    
    # 检查日志文件
    alerts_log = TEST_LOG_DIR / "alerts.log"
    if alerts_log.exists():
        with open(alerts_log, 'r', encoding='utf-8') as f:
            content = f.read()
            result.record("alerts.log 包含预警记录",
                         "TestToken" in content and "策略触发" in content,
                         "未找到预警记录")
    else:
        result.record("alerts.log 文件存在", False, "文件不存在")
    
    return result.summary()


def test_scanner_logging():
    """测试 7：验证 Scanner 通知日志"""
    print("\n📋 测试 7: Scanner 通知日志")
    result = TestResult()
    
    scanner_logger = logging.getLogger('scanner')
    
    # 写入测试 Scanner 消息
    test_message = """第51轮
━━━━━━━━━━━━━━━━━━━━
📊 TestToken 【5分钟】
📁 来源: test.txt
涨跌幅: 5M=59.76% | 1H=19.29%
💰 市值: $84K → $136K (+61.90%)
━━━━━━━━━━━━━━━━━━━━"""
    
    scanner_logger.info(test_message)
    
    time.sleep(0.1)
    
    scanner_log = TEST_LOG_DIR / "scanner.log"
    if scanner_log.exists():
        with open(scanner_log, 'r', encoding='utf-8') as f:
            content = f.read()
            result.record("scanner.log 包含通知记录",
                         "第51轮" in content and "TestToken" in content,
                         "未找到通知记录")
    else:
        result.record("scanner.log 文件存在", False, "文件不存在")
    
    return result.summary()


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("🧪 v3.1 功能测试套件")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    tests = [
        ("日志器初始化", test_logger_initialization),
        ("交易日志记录", test_trade_logging),
        ("持仓追踪", test_position_tracking),
        ("策略条件", test_strategy_conditions),
        ("止盈止损", test_stop_loss_take_profit),
        ("预警日志", test_alerts_logging),
        ("Scanner日志", test_scanner_logging),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            print(f"  ❌ 测试异常: {e}")
    
    print("\n" + "=" * 60)
    print(f"📊 总测试结果: {passed}/{len(tests)} 测试组通过")
    
    if failed == 0:
        print("✅ 所有测试通过！v3.1 功能已就绪。")
    else:
        print(f"⚠️ {failed} 个测试组失败，请检查上述错误。")
    
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
