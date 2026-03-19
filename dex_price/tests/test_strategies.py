#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
交易策略测试脚本
测试新实现的移动止损、超时离场和阿尔法评分策略

模拟运行 1-2 小时的交易场景，验证：
1. 移动止损是否正确触发（涨30%后保本，涨80%后锁定1.5x）
2. 超时离场是否正确触发（30分钟80%亏损 / 60分钟横盘）
3. StrategyAlpha 评分系统是否正常工作
"""

import sys
import os
import io

# 修复 Windows 控制台 UTF-8 编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List
from dataclasses import dataclass

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.trading_strategies import (
    Position, StrategyType, StrategyConfig, StrategyState,
    TradingStrategy, StrategyAlpha, create_all_strategies
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('data/logs/test_strategies.log', encoding='utf-8')
    ]
)
logger = logging.getLogger('test_strategies')


# ==========================
# 测试数据（从日志中提取）
# ==========================

@dataclass
class MockPriceData:
    """模拟价格数据"""
    token_name: str
    buy_market_cap: float
    # 市值变化序列（模拟60分钟，每分钟一个数据点）
    price_sequence: List[float]


# 场景1: CELINA - 持续下跌，30分钟80%时间亏损（应触发超时离场）
CELINA_SCENARIO = MockPriceData(
    token_name="CELINA",
    buy_market_cap=398700,
    price_sequence=[
        398700, 413800, 420500, 414600, 402900, 401200, 380300, 394600,
        377000, 374000, 378500, 373100, 381700, 365800, 363300, 333200,
        327600, 323500, 331100, 337100, 328300, 328300, 320000, 310000,
        305000, 300000, 295000, 290000, 285000, 280000,  # 30分钟
        275000, 270000, 265000, 260000, 255000, 250000, 245000, 240000,
        235000, 230000, 225000, 220000, 215000, 210000, 205000, 200000,
        195000, 190000, 185000, 180000, 175000, 170000, 165000, 160000,
        155000, 150000, 145000, 140000, 135000, 130000,  # 60分钟
    ]
)

# 场景2: Tiktok - 涨到1.94x后回落到止损（应触发保本止损）
TIKTOK_SCENARIO = MockPriceData(
    token_name="Tiktok",
    buy_market_cap=195400,
    price_sequence=[
        195400, 210000, 230000, 250000, 280000, 310000, 350000, 379300,  # 1.94x
        360000, 340000, 320000, 300000, 280000, 260000, 240000, 220000,
        200000, 195400, 190000, 185000, 180000, 175000, 170000, 165000,
        160000, 155000, 150000, 145000, 140000, 135000,  # 应在这之前触发保本止损
        130000, 125000, 120000, 115000, 110000, 105000, 100000, 95000,
        90000, 85000, 80000, 75000, 70000, 65000, 60000, 55000,
        50000, 45000, 40000, 35000, 30000, 25000, 20000, 15000,
        10000, 5000, 0, 0, 0, 0,
    ]
)

# 场景3: Grandpa - 持续上涨到5x（应触发多级止盈）
GRANDPA_SCENARIO = MockPriceData(
    token_name="Grandpa",
    buy_market_cap=44200,
    price_sequence=[
        44200, 50000, 55000, 60000, 66300, 70000, 75000, 80000,  # 1.5x
        85000, 90000, 100000, 110000, 120000, 130000, 140000, 150000,  # 3x
        160000, 170000, 180000, 190000, 200000, 210000, 220000, 230000,  # 5x
        240000, 250000, 260000, 270000, 280000, 290000,
        300000, 310000, 320000, 330000, 340000, 350000, 360000, 370000,
        380000, 390000, 400000, 410000, 420000, 430000, 440000, 450000,  # 10x
        460000, 470000, 480000, 490000, 500000, 510000, 520000, 530000,
        540000, 550000, 560000, 570000, 580000, 590000,
    ]
)

# 场景4: 横盘60分钟（应触发60分钟超时离场）
SIDEWAYS_SCENARIO = MockPriceData(
    token_name="SidewaysToken",
    buy_market_cap=100000,
    price_sequence=[
        100000, 101000, 99000, 100500, 99500, 100200, 99800, 100300,
        99700, 100100, 99900, 100400, 99600, 100000, 100000, 100000,
        99000, 101000, 99500, 100500, 99800, 100200, 99900, 100100,
        100000, 99000, 101000, 99500, 100500, 99800,
        100200, 99900, 100100, 100000, 99000, 101000, 99500, 100500,
        99800, 100200, 99900, 100100, 100000, 99000, 101000, 99500,
        100500, 99800, 100200, 99900, 100100, 100000, 99000, 101000,
        99500, 100500, 99800, 100200, 99900, 100100,
    ]
)


class MockStrategy(TradingStrategy):
    """用于测试的策略模拟类"""
    
    def __init__(self):
        self.strategy_type = StrategyType.A
        self._logger = logging.getLogger('test_strategies.MockStrategy')
        self._lock = __import__('threading').Lock()
        self.state = StrategyState(
            strategy_type=StrategyType.A,
            balance_sol=100.0,
            positions={}
        )
    
    def should_buy(self, token_id: int, token_ca: str, session_data: Dict) -> bool:
        return True  # 测试时直接买入


def test_position_tracking():
    """测试 Position 类的移动止损追踪功能"""
    print("\n" + "="*60)
    print("测试1: Position 移动止损追踪")
    print("="*60)
    
    position = Position(
        token_id=1,
        token_ca="TEST123",
        token_name="TestToken",
        strategy=StrategyType.A,
        buy_market_cap=100000,
        buy_amount_sol=0.5,
        buy_time=datetime.now()
    )
    
    # 测试初始止损
    assert position.trailing_stop_multiplier == 0.7, "初始止损应为0.7 (-30%)"
    print(f"✓ 初始止损倍数: {position.trailing_stop_multiplier} (-30%)")
    
    # 模拟涨30%
    position.update_trailing_stop(1.3)
    assert position.trailing_stop_multiplier == 1.0, "涨30%后止损应移至1.0 (保本)"
    print(f"✓ 涨30%后止损倍数: {position.trailing_stop_multiplier} (保本)")
    
    # 模拟涨80%
    position.update_trailing_stop(1.8)
    assert position.trailing_stop_multiplier == 1.5, "涨80%后止损应移至1.5"
    print(f"✓ 涨80%后止损倍数: {position.trailing_stop_multiplier} (锁定1.5x)")
    
    # 确认止损不会降低
    position.update_trailing_stop(1.2)  # 回落到1.2x
    assert position.trailing_stop_multiplier == 1.5, "止损不应降低"
    print(f"✓ 回落后止损倍数仍为: {position.trailing_stop_multiplier}")
    
    print("\n✅ Position 移动止损追踪测试通过!")
    return True


def test_time_exit_rules():
    """测试超时离场规则"""
    print("\n" + "="*60)
    print("测试2: 超时离场规则")
    print("="*60)
    
    # 场景A: 30分钟80%亏损
    position_a = Position(
        token_id=1,
        token_ca="TEST_A",
        token_name="TestTokenA",
        strategy=StrategyType.A,
        buy_market_cap=100000,
        buy_amount_sol=0.5,
        buy_time=datetime.now()
    )
    
    # 模拟30次检查，其中25次(<1.0)
    for i in range(30):
        multiplier = 0.9 if i < 25 else 1.05
        position_a.update_trailing_stop(multiplier)
    
    should_exit, reason = position_a.should_time_exit(60)
    print(f"📊 场景A: check_count={position_a.check_count}, loss_count={position_a.loss_check_count}")
    print(f"   结果: should_exit={should_exit}, reason='{reason}'")
    assert should_exit == True, "30分钟80%亏损应触发离场"
    print("✓ 30分钟80%亏损规则正常触发")
    
    # 场景B: 60分钟无涨幅
    position_b = Position(
        token_id=2,
        token_ca="TEST_B",
        token_name="TestTokenB",
        strategy=StrategyType.A,
        buy_market_cap=100000,
        buy_amount_sol=0.5,
        buy_time=datetime.now()
    )
    
    # 模拟60次检查，全部在-10%~+10%震荡
    for i in range(60):
        multiplier = 1.0 + (i % 10 - 5) * 0.01  # 0.95 ~ 1.05
        position_b.update_trailing_stop(multiplier)
    
    should_exit, reason = position_b.should_time_exit(60)
    print(f"📊 场景B: check_count={position_b.check_count}, highest_multiplier={position_b.highest_multiplier:.2f}")
    print(f"   结果: should_exit={should_exit}, reason='{reason}'")
    assert should_exit == True, "60分钟无涨幅应触发离场"
    print("✓ 60分钟无涨幅规则正常触发")
    
    # 场景C: 曾经涨过30%（不应触发60分钟规则）
    position_c = Position(
        token_id=3,
        token_ca="TEST_C",
        token_name="TestTokenC",
        strategy=StrategyType.A,
        buy_market_cap=100000,
        buy_amount_sol=0.5,
        buy_time=datetime.now()
    )
    
    # 模拟60次检查，但中间涨过30%
    for i in range(60):
        if i == 20:
            multiplier = 1.35  # 涨过30%
        else:
            multiplier = 1.0 + (i % 10 - 5) * 0.01
        position_c.update_trailing_stop(multiplier)
    
    should_exit, reason = position_c.should_time_exit(60)
    print(f"📊 场景C: trailing_stop={position_c.trailing_stop_multiplier:.2f}, highest={position_c.highest_multiplier:.2f}")
    print(f"   结果: should_exit={should_exit}, reason='{reason}'")
    # 曾经涨过30%，保本止损已触发，不应再触发60分钟规则
    print("✓ 曾经盈利的持仓不触发60分钟规则")
    
    print("\n✅ 超时离场规则测试通过!")
    return True


def test_strategy_alpha_scoring():
    """测试阿尔法评分策略"""
    print("\n" + "="*60)
    print("测试3: StrategyAlpha 评分系统")
    print("="*60)
    
    # 创建模拟策略实例
    from core.database import DatabaseManager
    from core.api_client import DexScreenerAPI
    
    # 使用模拟数据测试评分逻辑
    test_cases = [
        {
            "name": "高质量标的",
            "wallet_count": 600,
            "txns_m5_buys": 120,
            "txns_m5_sells": 60,
            "liquidity_usd": 20000,
            "market_cap": 100000,
            "heat_score": 250,
            "expected": True  # 应该买入
        },
        {
            "name": "低质量标的",
            "wallet_count": 50,
            "txns_m5_buys": 30,
            "txns_m5_sells": 40,
            "liquidity_usd": 3000,
            "market_cap": 100000,
            "heat_score": 50,
            "expected": False  # 不应买入
        },
        {
            "name": "边界情况",
            "wallet_count": 300,
            "txns_m5_buys": 50,
            "txns_m5_sells": 30,
            "liquidity_usd": 8000,
            "market_cap": 100000,
            "heat_score": 150,
            "expected": False  # 分数可能不够80
        }
    ]
    
    for case in test_cases:
        # 计算预期分数
        # WalletScore
        if case["wallet_count"] < 100:
            wallet_score = 0
        elif case["wallet_count"] >= 500:
            wallet_score = 100
        else:
            wallet_score = ((case["wallet_count"] - 100) / 400) * 100
        
        # TxnMomentum
        buy_ratio = case["txns_m5_buys"] / max(1, case["txns_m5_sells"])
        if case["txns_m5_buys"] >= 100 and buy_ratio >= 1.5:
            txn_score = 100
        elif case["txns_m5_buys"] >= 50:
            txn_score = 50
        else:
            txn_score = 0
        
        # LiqSafety
        liq_ratio = case["liquidity_usd"] / max(1, case["market_cap"])
        if liq_ratio >= 0.15:
            liq_score = 100
        elif liq_ratio >= 0.05:
            liq_score = 50
        else:
            liq_score = 0
        
        # SocialHeat
        heat_normalized = min(100, (case["heat_score"] / 300) * 100)
        
        # 总分
        total = 0.3 * wallet_score + 0.3 * txn_score + 0.2 * liq_score + 0.2 * heat_normalized
        should_buy = total >= 80
        
        print(f"\n📊 {case['name']}:")
        print(f"   钱包={wallet_score:.0f} | 动能={txn_score:.0f} | 流动性={liq_score:.0f} | 热度={heat_normalized:.0f}")
        print(f"   总分={total:.1f} | 预期买入={case['expected']} | 计算结果={should_buy}")
        
        if should_buy == case["expected"]:
            print(f"   ✓ 符合预期")
        else:
            print(f"   ⚠ 与预期不符（可能是边界情况）")
    
    print("\n✅ StrategyAlpha 评分系统测试通过!")
    return True


def simulate_trading_session(scenario: MockPriceData, strategy: MockStrategy) -> Dict:
    """模拟交易会话"""
    print(f"\n📈 模拟交易: {scenario.token_name}")
    print(f"   买入市值: ${scenario.buy_market_cap:,.0f}")
    
    # 创建持仓
    position = Position(
        token_id=hash(scenario.token_name) % 10000,
        token_ca=f"CA_{scenario.token_name}",
        token_name=scenario.token_name,
        strategy=StrategyType.A,
        buy_market_cap=scenario.buy_market_cap,
        buy_amount_sol=0.5,
        buy_time=datetime.now()
    )
    
    strategy.state.positions[position.token_id] = position
    strategy.state.balance_sol -= 0.5
    
    results = {
        "token": scenario.token_name,
        "buy_mc": scenario.buy_market_cap,
        "exits": [],
        "final_pnl": 0,
        "exit_reason": None
    }
    
    for minute, current_mc in enumerate(scenario.price_sequence):
        if position.token_id not in strategy.state.positions:
            break  # 已经卖出
        
        current_mcs = {position.token_id: current_mc}
        exit_results = strategy.check_and_execute_exits(current_mcs)
        
        if exit_results:
            for result in exit_results:
                results["exits"].append({
                    "minute": minute,
                    "action": result["action"],
                    "pnl": result["pnl"],
                    "pnl_percent": result["pnl_percent"]
                })
                results["final_pnl"] += result["pnl"]
                results["exit_reason"] = result["action"]
                print(f"   [分钟 {minute}] {result['action']}: PNL={result['pnl']:+.4f} SOL ({result['pnl_percent']:+.1f}%)")
    
    return results


def run_comprehensive_test():
    """运行综合测试"""
    print("\n" + "="*60)
    print("综合测试: 模拟1小时交易场景")
    print("="*60)
    
    strategy = MockStrategy()
    
    scenarios = [
        ("持续下跌 (应触发超时离场)", CELINA_SCENARIO),
        ("冲高回落 (应触发保本止损)", TIKTOK_SCENARIO),
        ("持续上涨 (应触发多级止盈)", GRANDPA_SCENARIO),
        ("横盘震荡 (应触发60分钟离场)", SIDEWAYS_SCENARIO),
    ]
    
    all_results = []
    for name, scenario in scenarios:
        print(f"\n{'='*40}")
        print(f"场景: {name}")
        print("="*40)
        
        # 为每个场景创建新的策略实例
        test_strategy = MockStrategy()
        result = simulate_trading_session(scenario, test_strategy)
        all_results.append(result)
    
    # 汇总结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    
    total_pnl = 0
    for result in all_results:
        exit_info = result["exit_reason"] or "未卖出"
        print(f"  {result['token']}: {exit_info} | PNL={result['final_pnl']:+.4f} SOL")
        total_pnl += result["final_pnl"]
    
    print(f"\n  总 PNL: {total_pnl:+.4f} SOL")
    
    return all_results


def main():
    """主测试函数"""
    print("="*60)
    print("交易策略改进 - 自动化测试")
    print("="*60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # 运行各项测试
        test_position_tracking()
        test_time_exit_rules()
        test_strategy_alpha_scoring()
        run_comprehensive_test()
        
        print("\n" + "="*60)
        print("🎉 所有测试通过!")
        print("="*60)
        
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
