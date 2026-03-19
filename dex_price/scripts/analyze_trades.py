#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
分析 trades.log，统计每个策略的盈亏总额以及交易次数。
"""
import re
import json
import os
import sys

# Ensure UTF-8 stdout on Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'logs', 'trades.log')

pattern = re.compile(r"SELL \| (?P<strategy>策略[A-Z]) .* PNL=(?P<pnl_sign>[\+\-])(?P<pnl_val>[0-9\.]+) SOL")

stats = {}
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        m = pattern.search(line)
        if m:
            strat = m.group('strategy')
            sign = 1 if m.group('pnl_sign') == '+' else -1
            val = float(m.group('pnl_val')) * sign
            if strat not in stats:
                stats[strat] = {'pnl': 0.0, 'count': 0}
            stats[strat]['pnl'] += val
            stats[strat]['count'] += 1

# Also include BUY lines with zero PNL? Not needed for profit.

print('=== Strategy PNL Summary ===')
for strat, data in sorted(stats.items()):
    print(f"{strat}: total PNL = {data['pnl']:.4f} SOL over {data['count']} trades")

# Save to JSON for further use
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trade_stats.json')
with open(out_path, 'w', encoding='utf-8') as out_f:
    json.dump(stats, out_f, ensure_ascii=False, indent=2)
