"""
动态会话系统测试脚本
使用模拟数据测试 session_manager.py 的核心功能
"""

import sys
import os
import time
import logging
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.session_manager import (
    SignalType, MonitoringSession, SessionManager,
    calculate_session_params, SIGNAL_BASE_PARAMS, MARKET_CAP_MODIFIERS
)


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class TestResult:
    """测试结果收集器"""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results = []
    
    def record(self, name: str, passed: bool, detail: str = ""):
        self.results.append((name, passed, detail))
        if passed:
            self.passed += 1
            logger.info(f"✅ {name}: PASSED {detail}")
        else:
            self.failed += 1
            logger.error(f"❌ {name}: FAILED {detail}")
    
    def summary(self):
        logger.info("=" * 60)
        logger.info(f"测试结果: {self.passed} 通过, {self.failed} 失败")
        logger.info("=" * 60)
        return self.failed == 0


def test_calculate_session_params():
    """测试动态参数计算"""
    result = TestResult()
    logger.info("\n" + "=" * 60)
    logger.info("测试 1: 动态参数计算 (calculate_session_params)")
    logger.info("=" * 60)
    
    # 测试 5m 信号 + 小市值 (<$50K)
    poll, life, heat = calculate_session_params(SignalType.SIGNAL_5M, 30_000)
    result.record(
        "5m + 小市值($30K) 轮询间隔",
        poll == 30,  # 60 * 0.5 = 30
        f"期望=30s, 实际={poll}s"
    )
    result.record(
        "5m + 小市值($30K) 寿命增量",
        life == 450,  # 900 * 0.5 = 450
        f"期望=450s(7.5min), 实际={life}s"
    )
    
    # 测试 5m 信号 + 中市值 ($50K-$500K)
    poll, life, heat = calculate_session_params(SignalType.SIGNAL_5M, 200_000)
    result.record(
        "5m + 中市值($200K) 轮询间隔",
        poll == 60,  # 60 * 1.0 = 60
        f"期望=60s, 实际={poll}s"
    )
    
    # 测试 5m 信号 + 大市值 (>$500K)
    poll, life, heat = calculate_session_params(SignalType.SIGNAL_5M, 1_000_000)
    result.record(
        "5m + 大市值($1M) 轮询间隔",
        poll == 120,  # 60 * 2.0 = 120
        f"期望=120s, 实际={poll}s"
    )
    result.record(
        "5m + 大市值($1M) 寿命增量",
        life == 1350,  # 900 * 1.5 = 1350
        f"期望=1350s(22.5min), 实际={life}s"
    )
    
    # 测试 1h 信号 + 中市值
    poll, life, heat = calculate_session_params(SignalType.SIGNAL_1H, 200_000)
    result.record(
        "1h + 中市值($200K) 轮询间隔",
        poll == 300,  # 300 * 1.0 = 300
        f"期望=300s(5min), 实际={poll}s"
    )
    result.record(
        "1h + 中市值($200K) 寿命增量",
        life == 14400,  # 14400 * 1.0 = 14400
        f"期望=14400s(4h), 实际={life}s"
    )
    
    # 测试 4h 信号 + 大市值
    poll, life, heat = calculate_session_params(SignalType.SIGNAL_4H, 800_000)
    result.record(
        "4h + 大市值($800K) 轮询间隔",
        poll == 1200,  # 600 * 2.0 = 1200
        f"期望=1200s(20min), 实际={poll}s"
    )
    
    return result


def test_monitoring_session():
    """测试 MonitoringSession 类"""
    result = TestResult()
    logger.info("\n" + "=" * 60)
    logger.info("测试 2: MonitoringSession 类功能")
    logger.info("=" * 60)
    
    # 创建会话
    session = MonitoringSession(
        token_id=1,
        token_ca="TEST_CA_123",
        token_name="TEST_TOKEN",
        token_href="/solana/test",
        initial_market_cap=100_000,
        current_market_cap=100_000,
        highest_market_cap=100_000,
        poll_interval=60,
        remaining_life_seconds=900,
        heat_score=110,
    )
    
    result.record(
        "会话创建",
        session.token_name == "TEST_TOKEN" and session.is_active,
        f"名称={session.token_name}, 活跃={session.is_active}"
    )
    
    # 测试涨幅计算
    session.current_market_cap = 150_000  # 涨50%
    result.record(
        "当前涨幅计算",
        abs(session.current_gain - 50.0) < 0.1,
        f"期望=50%, 实际={session.current_gain:.1f}%"
    )
    
    session.highest_market_cap = 180_000  # 最高涨80%
    result.record(
        "最高涨幅计算",
        abs(session.api_gain_5m - 80.0) < 0.1,
        f"期望=80%, 实际={session.api_gain_5m:.1f}%"
    )
    
    # 测试信号更新 (快→慢)
    old_poll = session.poll_interval
    old_life = session.remaining_life_seconds
    session.update_with_signal(SignalType.SIGNAL_1H, 25.0, 0.001, 150_000)
    
    result.record(
        "信号更新 (5m→1h) 轮询变慢",
        session.poll_interval > old_poll,
        f"轮询: {old_poll}s → {session.poll_interval}s"
    )
    result.record(
        "信号更新 (5m→1h) 寿命增加",
        session.remaining_life_seconds > old_life,
        f"寿命: {old_life//60}min → {session.remaining_life_seconds//60}min"
    )
    result.record(
        "信号更新后信号列表",
        len(session.signals) == 1,
        f"信号数量={len(session.signals)}"
    )
    
    # 测试向后兼容的 add_signal 方法
    session.add_signal(SignalType.SIGNAL_5M, 30.0, 0.0012, 160_000)
    result.record(
        "add_signal 向后兼容",
        len(session.signals) == 2,
        f"信号数量={len(session.signals)}"
    )
    
    # 测试 to_session_data
    data = session.to_session_data()
    result.record(
        "to_session_data 输出",
        data["token_id"] == 1 and "signals" in data and len(data["signals"]) == 2,
        f"包含 token_id 和 signals"
    )
    
    return result


def test_session_manager():
    """测试 SessionManager 类"""
    result = TestResult()
    logger.info("\n" + "=" * 60)
    logger.info("测试 3: SessionManager 类功能")
    logger.info("=" * 60)
    
    # 创建 Mock 对象
    mock_db = MagicMock()
    mock_api = MagicMock()
    
    # 创建 SessionManager
    manager = SessionManager(db=mock_db, api=mock_api)
    
    result.record(
        "SessionManager 初始化",
        manager.get_session_count() == 0,
        f"初始会话数={manager.get_session_count()}"
    )
    
    # 测试创建新会话 (5m 信号 + 中市值)
    session1 = manager.create_or_update_session(
        token_id=1,
        token_ca="CA_TOKEN_A",
        token_name="TokenA",
        token_href="/solana/a",
        signal_type=SignalType.SIGNAL_5M,
        trigger_value=35.0,
        price=0.001,
        market_cap=200_000
    )
    
    result.record(
        "创建新会话 (5m, $200K)",
        manager.get_session_count() == 1,
        f"会话数={manager.get_session_count()}, 轮询={session1.poll_interval}s"
    )
    result.record(
        "新会话轮询间隔正确",
        session1.poll_interval == 60,  # 5m 中市值 = 60s
        f"期望=60s, 实际={session1.poll_interval}s"
    )
    
    # 测试创建另一个会话 (1h 信号 + 大市值)
    session2 = manager.create_or_update_session(
        token_id=2,
        token_ca="CA_TOKEN_B",
        token_name="TokenB",
        token_href="/solana/b",
        signal_type=SignalType.SIGNAL_1H,
        trigger_value=25.0,
        price=0.05,
        market_cap=800_000
    )
    
    result.record(
        "创建第二个会话 (1h, $800K)",
        manager.get_session_count() == 2,
        f"会话数={manager.get_session_count()}"
    )
    result.record(
        "1h+大市值 轮询间隔正确",
        session2.poll_interval == 600,  # 300 * 2.0 = 600s
        f"期望=600s(10min), 实际={session2.poll_interval}s"
    )
    
    # 测试更新现有会话 (TokenA 触发 20m 信号)
    old_poll = session1.poll_interval
    old_heat = session1.heat_score
    updated_session = manager.create_or_update_session(
        token_id=1,  # 同一个 token_id
        token_ca="CA_TOKEN_A",
        token_name="TokenA",
        token_href="/solana/a",
        signal_type=SignalType.SIGNAL_20M,
        trigger_value=28.0,
        price=0.0015,
        market_cap=250_000
    )
    
    result.record(
        "更新现有会话 (5m→20m)",
        manager.get_session_count() == 2,  # 不应增加
        f"会话数仍为={manager.get_session_count()}"
    )
    result.record(
        "更新后轮询间隔变化",
        updated_session.poll_interval != old_poll,
        f"轮询: {old_poll}s → {updated_session.poll_interval}s"
    )
    result.record(
        "更新后热度增加",
        updated_session.heat_score > old_heat,
        f"热度: {old_heat} → {updated_session.heat_score}"
    )
    result.record(
        "更新后信号列表累加",
        len(updated_session.signals) == 2,
        f"信号数量={len(updated_session.signals)}"
    )
    
    # 测试获取会话
    fetched = manager.get_session(1)
    result.record(
        "get_session 功能",
        fetched is not None and fetched.token_name == "TokenA",
        f"获取到={fetched.token_name if fetched else 'None'}"
    )
    
    # 测试获取所有会话
    all_sessions = manager.get_all_sessions()
    result.record(
        "get_all_sessions 功能",
        len(all_sessions) == 2,
        f"返回数量={len(all_sessions)}"
    )
    
    # 测试获取市值映射
    market_caps = manager.get_current_market_caps()
    result.record(
        "get_current_market_caps 功能",
        len(market_caps) == 2 and 1 in market_caps and 2 in market_caps,
        f"市值映射: {market_caps}"
    )
    
    return result


def test_signal_transition():
    """测试信号流转场景"""
    result = TestResult()
    logger.info("\n" + "=" * 60)
    logger.info("测试 4: 信号流转场景 (快→慢, 慢→快)")
    logger.info("=" * 60)
    
    mock_db = MagicMock()
    mock_api = MagicMock()
    manager = SessionManager(db=mock_db, api=mock_api)
    
    # 场景1: 先 5m (快) 后 1h (慢) - 应该变慢
    session = manager.create_or_update_session(
        token_id=100,
        token_ca="CA_TRANSITION",
        token_name="TransitionToken",
        token_href="/solana/t",
        signal_type=SignalType.SIGNAL_5M,
        trigger_value=35.0,
        price=0.001,
        market_cap=200_000
    )
    poll_after_5m = session.poll_interval
    
    manager.create_or_update_session(
        token_id=100,
        token_ca="CA_TRANSITION",
        token_name="TransitionToken",
        token_href="/solana/t",
        signal_type=SignalType.SIGNAL_1H,
        trigger_value=30.0,
        price=0.0015,
        market_cap=250_000
    )
    poll_after_1h = session.poll_interval
    
    result.record(
        "快→慢 (5m→1h) 轮询变慢",
        poll_after_1h > poll_after_5m,
        f"{poll_after_5m}s → {poll_after_1h}s"
    )
    
    # 场景2: 再触发 5m (快) - 应该变快
    manager.create_or_update_session(
        token_id=100,
        token_ca="CA_TRANSITION",
        token_name="TransitionToken",
        token_href="/solana/t",
        signal_type=SignalType.SIGNAL_5M,
        trigger_value=40.0,
        price=0.002,
        market_cap=300_000
    )
    poll_after_5m_again = session.poll_interval
    
    result.record(
        "慢→快 (1h→5m) 轮询变快",
        poll_after_5m_again < poll_after_1h,
        f"{poll_after_1h}s → {poll_after_5m_again}s"
    )
    
    # 验证信号历史累加
    result.record(
        "信号历史完整记录",
        len(session.signals) == 3,
        f"信号数量={len(session.signals)}, 类型={[s.signal_type.value for s in session.signals]}"
    )
    
    return result


def test_market_cap_impact():
    """测试市值对参数的影响"""
    result = TestResult()
    logger.info("\n" + "=" * 60)
    logger.info("测试 5: 市值对会话参数的影响")
    logger.info("=" * 60)
    
    mock_db = MagicMock()
    mock_api = MagicMock()
    manager = SessionManager(db=mock_db, api=mock_api)
    
    # 小市值代币 ($30K)
    small = manager.create_or_update_session(
        token_id=201, token_ca="CA_SMALL", token_name="SmallCap",
        token_href="/s", signal_type=SignalType.SIGNAL_5M,
        trigger_value=50.0, price=0.0001, market_cap=30_000
    )
    
    # 中市值代币 ($200K)
    medium = manager.create_or_update_session(
        token_id=202, token_ca="CA_MEDIUM", token_name="MediumCap",
        token_href="/m", signal_type=SignalType.SIGNAL_5M,
        trigger_value=50.0, price=0.001, market_cap=200_000
    )
    
    # 大市值代币 ($1M)
    large = manager.create_or_update_session(
        token_id=203, token_ca="CA_LARGE", token_name="LargeCap",
        token_href="/l", signal_type=SignalType.SIGNAL_5M,
        trigger_value=50.0, price=0.01, market_cap=1_000_000
    )
    
    result.record(
        "小市值轮询更快",
        small.poll_interval < medium.poll_interval,
        f"小:{small.poll_interval}s < 中:{medium.poll_interval}s"
    )
    result.record(
        "大市值轮询更慢",
        large.poll_interval > medium.poll_interval,
        f"大:{large.poll_interval}s > 中:{medium.poll_interval}s"
    )
    result.record(
        "小市值寿命更短",
        small.remaining_life_seconds < medium.remaining_life_seconds,
        f"小:{small.remaining_life_seconds//60}min < 中:{medium.remaining_life_seconds//60}min"
    )
    result.record(
        "大市值寿命更长",
        large.remaining_life_seconds > medium.remaining_life_seconds,
        f"大:{large.remaining_life_seconds//60}min > 中:{medium.remaining_life_seconds//60}min"
    )
    
    return result


def main():
    """运行所有测试"""
    logger.info("=" * 60)
    logger.info("动态会话系统测试 - 开始")
    logger.info("=" * 60)
    
    all_results = []
    
    # 运行各项测试
    all_results.append(test_calculate_session_params())
    all_results.append(test_monitoring_session())
    all_results.append(test_session_manager())
    all_results.append(test_signal_transition())
    all_results.append(test_market_cap_impact())
    
    # 汇总结果
    total_passed = sum(r.passed for r in all_results)
    total_failed = sum(r.failed for r in all_results)
    
    logger.info("\n")
    logger.info("=" * 60)
    logger.info("总体测试结果")
    logger.info("=" * 60)
    logger.info(f"通过: {total_passed}")
    logger.info(f"失败: {total_failed}")
    logger.info("=" * 60)
    
    if total_failed == 0:
        logger.info("🎉 所有测试通过！动态会话系统功能正常。")
        return 0
    else:
        logger.error("⚠️ 存在失败的测试，请检查代码。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
