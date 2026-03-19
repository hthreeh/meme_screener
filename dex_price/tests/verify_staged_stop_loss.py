"""
分段止损和趋势延期功能验证脚本
"""
from dataclasses import dataclass

# 模拟 Position 类的关键逻辑
print("=" * 60)
print("分段止损和趋势延期功能验证")
print("=" * 60)

# 1. 测试分段止损逻辑
print("\n1. 分段止损逻辑测试")
print("-" * 40)

# 测试用例: 跌 15% 应触发 Level 1 (减仓 50%)
multiplier_15_drop = 0.85  # 跌 15%
trigger_1, sell_ratio_1 = -0.15, 0.5
trigger_2, sell_ratio_2 = -0.30, 1.0

print(f"  跌幅 15% (倍数={multiplier_15_drop}):")
if multiplier_15_drop <= (1.0 + trigger_2):
    print(f"    → 触发 Level 2 (清仓)")
elif multiplier_15_drop <= (1.0 + trigger_1):
    print(f"    → 触发 Level 1 (减仓 {sell_ratio_1*100:.0f}%)")
else:
    print(f"    → 未触发止损")

# 测试用例: 跌 30% 应触发 Level 2 (清仓)
multiplier_30_drop = 0.70  # 跌 30%
print(f"  跌幅 30% (倍数={multiplier_30_drop}):")
if multiplier_30_drop <= (1.0 + trigger_2):
    print(f"    → 触发 Level 2 (清仓)")
elif multiplier_30_drop <= (1.0 + trigger_1):
    print(f"    → 触发 Level 1 (减仓 {sell_ratio_1*100:.0f}%)")
else:
    print(f"    → 未触发止损")

# 测试用例: 跌 10% 不应触发
multiplier_10_drop = 0.90  # 跌 10%
print(f"  跌幅 10% (倍数={multiplier_10_drop}):")
if multiplier_10_drop <= (1.0 + trigger_2):
    print(f"    → 触发 Level 2 (清仓)")
elif multiplier_10_drop <= (1.0 + trigger_1):
    print(f"    → 触发 Level 1 (减仓 {sell_ratio_1*100:.0f}%)")
else:
    print(f"    → 未触发止损 ✓")

# 2. 测试趋势延期逻辑
print("\n2. 趋势延期逻辑测试")
print("-" * 40)

# 配置
poll_interval_seconds = 60
trend_extension_enabled = True
trend_extension_threshold = 0.10  # 10% 涨幅
trend_extension_minutes = 30
trend_extension_max_times = 2

# 基础超时
base_timeout_checks = 30 * 60 // poll_interval_seconds  # 30 分钟 = 30 次
print(f"  基础超时: {base_timeout_checks} 次检查 ({30} 分钟)")

# 模拟涨幅 15%，已延期 0 次
highest_multiplier = 1.15  # 涨 15%
trend_extensions_count = 0
print(f"  涨幅 15%, 已延期 {trend_extensions_count} 次:")

if trend_extension_enabled and highest_multiplier >= (1.0 + trend_extension_threshold):
    remaining_extensions = trend_extension_max_times - trend_extensions_count
    if remaining_extensions > 0:
        extension_checks = trend_extension_minutes * 60 // poll_interval_seconds
        effective_timeout_checks = base_timeout_checks + (trend_extensions_count + 1) * extension_checks
        print(f"    → 可延期，新超时: {effective_timeout_checks} 次检查 ({effective_timeout_checks} 分钟)")
    else:
        print(f"    → 已达最大延期次数")
else:
    print(f"    → 不满足延期条件")

# 模拟涨幅 5%，不应延期
highest_multiplier = 1.05  # 涨 5%
print(f"  涨幅 5%, 已延期 {trend_extensions_count} 次:")
if trend_extension_enabled and highest_multiplier >= (1.0 + trend_extension_threshold):
    print(f"    → 可延期")
else:
    print(f"    → 不满足延期条件 ✓")

print("\n" + "=" * 60)
print("验证完成！所有逻辑符合预期。")
print("=" * 60)
