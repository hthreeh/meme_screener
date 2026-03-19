"""
交易策略模拟测试脚本
测试各策略的 should_buy 逻辑是否按照新规则正确工作
"""

import sys
sys.path.insert(0, r'e:\project_claude_0103\dex_price')

from services.trading_strategies import (
    StrategyType, StrategyConfig, 
    StrategyA, StrategyB, StrategyC, StrategyD, StrategyE, StrategyF, StrategyG,
    StrategyH, StrategyI, StrategyAlpha
)

# Mock classes for testing
class MockDB:
    def load_strategy_state(self, *args): return None
    def save_strategy_state(self, *args): pass
    def save_position(self, *args): pass
    def delete_position(self, *args): pass
    def record_multi_strategy_trade(self, *args): pass

class MockAPI:
    pass

def create_test_strategy(strategy_class, strategy_type):
    """创建测试用策略实例"""
    config = StrategyConfig(
        name=f"Test {strategy_type.value}",
        trade_amount_sol=0.1,
        initial_balance_sol=100.0
    )
    return strategy_class(strategy_type, config, MockDB(), MockAPI())

def run_tests():
    """运行所有策略测试"""
    print("=" * 60)
    print("交易策略模拟测试")
    print("=" * 60)
    
    all_passed = True
    
    # ========== 策略 A: 热度策略 ==========
    print("\n【策略A】热度策略 (热度>=150)")
    strategy_a = create_test_strategy(StrategyA, StrategyType.A)
    
    # 测试1: 热度150触发
    result = strategy_a.should_buy(1, "token_a", {"heat_score": 150, "signals": []})
    print(f"  ✓ 热度=150 → {result}" if result else f"  ✗ 热度=150 → {result} (应为True)")
    all_passed &= result
    
    # 测试2: 热度149不触发
    result = strategy_a.should_buy(1, "token_a", {"heat_score": 149, "signals": []})
    print(f"  ✓ 热度=149 → {result}" if not result else f"  ✗ 热度=149 → {result} (应为False)")
    all_passed &= not result
    
    # ========== 策略 B: 信号策略 ==========
    print("\n【策略B】信号策略 (5m+20m组合)")
    strategy_b = create_test_strategy(StrategyB, StrategyType.B)
    
    # 测试1: 有5m和20m触发
    result = strategy_b.should_buy(1, "token_b", {
        "signals": [{"type": "5m"}, {"type": "20m"}]
    })
    print(f"  ✓ 5m+20m → {result}" if result else f"  ✗ 5m+20m → {result} (应为True)")
    all_passed &= result
    
    # 测试2: 只有5m不触发
    result = strategy_b.should_buy(1, "token_b", {
        "signals": [{"type": "5m"}]
    })
    print(f"  ✓ 仅5m → {result}" if not result else f"  ✗ 仅5m → {result} (应为False)")
    all_passed &= not result
    
    # ========== 策略 C: 5m信号 ==========
    print("\n【策略C】5m信号 (任意5m)")
    strategy_c = create_test_strategy(StrategyC, StrategyType.C)
    
    # 测试1: 有5m触发
    result = strategy_c.should_buy(1, "token_c", {
        "signals": [{"type": "5m"}]
    })
    print(f"  ✓ 有5m → {result}" if result else f"  ✗ 有5m → {result} (应为True)")
    all_passed &= result
    
    # 测试2: 只有20m不触发
    result = strategy_c.should_buy(1, "token_c", {
        "signals": [{"type": "20m"}]
    })
    print(f"  ✓ 仅20m → {result}" if not result else f"  ✗ 仅20m → {result} (应为False)")
    all_passed &= not result
    
    # ========== 策略 D: API暴涨 ==========
    print("\n【策略D】API暴涨 (涨幅>=50%)")
    strategy_d = create_test_strategy(StrategyD, StrategyType.D)
    
    # 测试1: 涨幅50%触发
    result = strategy_d.should_buy(1, "token_d", {
        "initial_market_cap": 100000,
        "current_market_cap": 150000
    })
    print(f"  ✓ 涨幅=50% → {result}" if result else f"  ✗ 涨幅=50% → {result} (应为True)")
    all_passed &= result
    
    # 测试2: 涨幅49%不触发
    result = strategy_d.should_buy(1, "token_d", {
        "initial_market_cap": 100000,
        "current_market_cap": 149000
    })
    print(f"  ✓ 涨幅=49% → {result}" if not result else f"  ✗ 涨幅=49% → {result} (应为False)")
    all_passed &= not result
    
    # ========== 策略 E: 20m信号 ==========
    print("\n【策略E】20m信号 (任意20m)")
    strategy_e = create_test_strategy(StrategyE, StrategyType.E)
    
    # 测试1: 有20m触发
    result = strategy_e.should_buy(1, "token_e", {
        "signals": [{"type": "20m"}]
    })
    print(f"  ✓ 有20m → {result}" if result else f"  ✗ 有20m → {result} (应为True)")
    all_passed &= result
    
    # ========== 策略 F: 1h信号 ==========
    print("\n【策略F】1h信号 (任意1h)")
    strategy_f = create_test_strategy(StrategyF, StrategyType.F)
    
    # 测试1: 有1h触发
    result = strategy_f.should_buy(1, "token_f", {
        "signals": [{"type": "1h"}]
    })
    print(f"  ✓ 有1h → {result}" if result else f"  ✗ 有1h → {result} (应为True)")
    all_passed &= result
    
    # ========== 策略 G: 4h信号 ==========
    print("\n【策略G】4h信号 (任意4h)")
    strategy_g = create_test_strategy(StrategyG, StrategyType.G)
    
    # 测试1: 有4h触发
    result = strategy_g.should_buy(1, "token_g", {
        "signals": [{"type": "4h"}]
    })
    print(f"  ✓ 有4h → {result}" if result else f"  ✗ 有4h → {result} (应为True)")
    all_passed &= result
    
    # ========== 策略 H: 金狗狙击 ==========
    print("\n【策略H】金狗狙击 (5m+放量+市值$50K-$2M)")
    strategy_h = create_test_strategy(StrategyH, StrategyType.H)
    
    # 测试1: 满足所有条件触发
    result = strategy_h.should_buy(1, "token_h", {
        "signals": [{"type": "5m"}],
        "current_market_cap": 500000,  # $500K
        "api_data": {
            "txns_m5_buys": 30,
            "txns_m5_sells": 15,
            "volume_m5": 50000
        }
    })
    print(f"  ✓ 满足所有条件 → {result}" if result else f"  ✗ 满足所有条件 → {result} (应为True)")
    all_passed &= result
    
    # 测试2: 市值超过2M不触发
    result = strategy_h.should_buy(1, "token_h", {
        "signals": [{"type": "5m"}],
        "current_market_cap": 2500000,  # $2.5M
        "api_data": {
            "txns_m5_buys": 30,
            "txns_m5_sells": 15,
            "volume_m5": 125000
        }
    })
    print(f"  ✓ 市值>$2M → {result}" if not result else f"  ✗ 市值>$2M → {result} (应为False)")
    all_passed &= not result
    
    # ========== 策略 I: 钻石手趋势 ==========
    print("\n【策略I】钻石手趋势 (20m/1h/4h+热度>150+市值>$100K)")
    strategy_i = create_test_strategy(StrategyI, StrategyType.I)
    
    # 测试1: 满足所有条件（使用20m信号）
    result = strategy_i.should_buy(1, "token_i", {
        "signals": [{"type": "20m"}],
        "current_market_cap": 150000,  # $150K
        "heat_score": 160,
        "highest_market_cap": 160000,
        "api_data": {"txns_h1_buys": 60}
    })
    print(f"  ✓ 20m+热度160+市值$150K → {result}" if result else f"  ✗ 20m+热度160+市值$150K → {result} (应为True)")
    all_passed &= result
    
    # 测试2: 市值<$100K不触发
    result = strategy_i.should_buy(1, "token_i", {
        "signals": [{"type": "1h"}],
        "current_market_cap": 80000,  # $80K
        "heat_score": 200,
        "api_data": {"txns_h1_buys": 60}
    })
    print(f"  ✓ 市值<$100K → {result}" if not result else f"  ✗ 市值<$100K → {result} (应为False)")
    all_passed &= not result
    
    # ========== 策略 Alpha: 阿尔法评分 ==========
    print("\n【策略Alpha】阿尔法评分 (5m+评分>=80)")
    strategy_alpha = create_test_strategy(StrategyAlpha, StrategyType.ALPHA)
    
    # 测试1: 高分通过
    result = strategy_alpha.should_buy(1, "token_alpha", {
        "signals": [{"type": "5m"}],
        "wallet_count": 500,
        "heat_score": 300,
        "current_market_cap": 100000,
        "api_data": {
            "txns_m5_buys": 60,
            "txns_m5_sells": 30,
            "liquidity_usd": 20000
        }
    })
    print(f"  ✓ 高分场景 → {result}" if result else f"  ✗ 高分场景 → {result} (应为True)")
    all_passed &= result
    
    # ========== 总结 ==========
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ 所有测试通过！策略逻辑正确。")
    else:
        print("❌ 部分测试失败，请检查策略逻辑。")
    print("=" * 60)
    
    return all_passed

if __name__ == "__main__":
    run_tests()
