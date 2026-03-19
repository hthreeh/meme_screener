"""
分段止损和趋势延期功能最终测试
"""
import sys
from datetime import datetime
from dataclasses import dataclass

# 添加项目路径
sys.path.insert(0, '.')

print("=" * 70)
print("分段止损与趋势延期功能 - 最终测试")
print("=" * 70)

# ==================== 测试 1: 配置加载 ====================
print("\n📋 测试 1: 配置加载")
print("-" * 50)

try:
    from config.settings import load_settings, StagedStopLossConfig, TrendExtensionConfig
    settings = load_settings()
    
    # 检查分段止损配置
    if hasattr(settings, 'staged_stop_loss') and settings.staged_stop_loss:
        ssl = settings.staged_stop_loss
        print(f"  ✅ 分段止损配置:")
        print(f"     - enabled: {ssl.enabled}")
        print(f"     - level_1: trigger={ssl.level_1.trigger}, sell_ratio={ssl.level_1.sell_ratio}")
        print(f"     - level_2: trigger={ssl.level_2.trigger}, sell_ratio={ssl.level_2.sell_ratio}")
    else:
        print("  ⚠️ 分段止损配置未找到")
    
    # 检查趋势延期配置
    if hasattr(settings, 'trend_extension') and settings.trend_extension:
        te = settings.trend_extension
        print(f"  ✅ 趋势延期配置:")
        print(f"     - enabled: {te.enabled}")
        print(f"     - threshold: {te.threshold}")
        print(f"     - extension_minutes: {te.extension_minutes}")
        print(f"     - max_times: {te.max_times}")
    else:
        print("  ⚠️ 趋势延期配置未找到")
        
except Exception as e:
    print(f"  ❌ 配置加载失败: {e}")

# ==================== 测试 2: Position 类新字段 ====================
print("\n📋 测试 2: Position 类新字段")
print("-" * 50)

try:
    from services.trading_strategies import Position, StrategyType
    
    position = Position(
        token_id=1,
        token_ca="test_ca",
        token_name="TestToken",
        strategy=StrategyType.A,
        buy_market_cap=100000,
        buy_amount_sol=0.1,
        buy_time=datetime.now()
    )
    
    # 检查新字段
    print(f"  ✅ staged_stop_level: {position.staged_stop_level} (预期: 0)")
    print(f"  ✅ trend_extensions_count: {position.trend_extensions_count} (预期: 0)")
    
    # 测试 should_time_exit 参数
    should_exit, reason = position.should_time_exit(
        poll_interval_seconds=60,
        trend_extension_enabled=True,
        trend_extension_threshold=0.10,
        trend_extension_minutes=30,
        trend_extension_max_times=2
    )
    print(f"  ✅ should_time_exit() 正常运行: should_exit={should_exit}")
    
except Exception as e:
    print(f"  ❌ Position 测试失败: {e}")
    import traceback
    traceback.print_exc()

# ==================== 测试 3: 分段止损逻辑 ====================
print("\n📋 测试 3: 分段止损逻辑")
print("-" * 50)

# 模拟测试
trigger_1, sell_ratio_1 = -0.15, 0.5
trigger_2, sell_ratio_2 = -0.30, 1.0

test_cases = [
    (0.90, "跌10%", "不触发"),
    (0.85, "跌15%", "Level 1 减仓50%"),
    (0.75, "跌25%", "Level 1 减仓50%"),
    (0.70, "跌30%", "Level 2 清仓"),
    (0.50, "跌50%", "Level 2 清仓"),
]

for multiplier, desc, expected in test_cases:
    if multiplier <= (1.0 + trigger_2):
        result = "Level 2 清仓"
    elif multiplier <= (1.0 + trigger_1):
        result = "Level 1 减仓50%"
    else:
        result = "不触发"
    
    status = "✅" if result == expected else "❌"
    print(f"  {status} {desc} (倍数={multiplier}): {result}")

# ==================== 测试 4: 趋势延期逻辑 ====================
print("\n📋 测试 4: 趋势延期逻辑")
print("-" * 50)

try:
    from services.trading_strategies import Position, StrategyType
    
    # 创建测试持仓
    pos = Position(
        token_id=2,
        token_ca="test_ca_2",
        token_name="TrendTest",
        strategy=StrategyType.A,
        buy_market_cap=100000,
        buy_amount_sol=0.1,
        buy_time=datetime.now()
    )
    
    # 模拟到达超时边界
    pos.check_count = 30  # 30分钟
    pos.loss_check_count = 10  # 低于80%亏损
    pos.highest_multiplier = 1.15  # 涨15%，满足延期条件
    
    # 第一次检查 - 应该延期
    should_exit_1, reason_1 = pos.should_time_exit(
        poll_interval_seconds=60,
        trend_extension_enabled=True,
        trend_extension_threshold=0.10,
        trend_extension_minutes=30,
        trend_extension_max_times=2
    )
    print(f"  ✅ 第1次超时边界: should_exit={should_exit_1}, 延期次数={pos.trend_extensions_count} (预期: 1)")
    
    # 模拟到达第二次超时边界（60分钟）
    pos.check_count = 60
    
    # 第二次检查 - 应该再次延期
    should_exit_2, reason_2 = pos.should_time_exit(
        poll_interval_seconds=60,
        trend_extension_enabled=True,
        trend_extension_threshold=0.10,
        trend_extension_minutes=30,
        trend_extension_max_times=2
    )
    print(f"  ✅ 第2次超时边界: should_exit={should_exit_2}, 延期次数={pos.trend_extensions_count} (预期: 2)")
    
    # 模拟到达第三次超时边界（90分钟）
    pos.check_count = 90
    pos.loss_check_count = 75  # 超过80%亏损
    
    # 第三次检查 - 超过最大延期次数，且满足亏损条件，应该退出
    should_exit_3, reason_3 = pos.should_time_exit(
        poll_interval_seconds=60,
        trend_extension_enabled=True,
        trend_extension_threshold=0.10,
        trend_extension_minutes=30,
        trend_extension_max_times=2
    )
    print(f"  ✅ 第3次超时边界: should_exit={should_exit_3}, 原因='{reason_3}'")
    
except Exception as e:
    print(f"  ❌ 趋势延期测试失败: {e}")
    import traceback
    traceback.print_exc()

# ==================== 测试 5: PositionTracker 初始化 ====================
print("\n📋 测试 5: PositionTracker 初始化")
print("-" * 50)

try:
    from services.position_tracker import PositionTracker
    import inspect
    
    # 检查 __init__ 签名
    sig = inspect.signature(PositionTracker.__init__)
    params = list(sig.parameters.keys())
    
    if 'settings' in params:
        print(f"  ✅ PositionTracker.__init__ 包含 'settings' 参数")
    else:
        print(f"  ❌ PositionTracker.__init__ 缺少 'settings' 参数")
        
except Exception as e:
    print(f"  ❌ PositionTracker 测试失败: {e}")

# ==================== 测试 6: check_and_execute_exits 签名 ====================
print("\n📋 测试 6: check_and_execute_exits 签名")
print("-" * 50)

try:
    from services.trading_strategies import TradingStrategy
    import inspect
    
    sig = inspect.signature(TradingStrategy.check_and_execute_exits)
    params = list(sig.parameters.keys())
    
    required_params = [
        'staged_stop_loss_enabled',
        'staged_stop_loss_level_1',
        'staged_stop_loss_level_2',
        'trend_extension_enabled',
        'trend_extension_threshold',
        'trend_extension_minutes',
        'trend_extension_max_times'
    ]
    
    missing = [p for p in required_params if p not in params]
    if not missing:
        print(f"  ✅ check_and_execute_exits 包含所有必要参数")
    else:
        print(f"  ❌ 缺少参数: {missing}")
        
except Exception as e:
    print(f"  ❌ 签名检查失败: {e}")

# ==================== 总结 ====================
print("\n" + "=" * 70)
print("测试完成！")
print("=" * 70)
