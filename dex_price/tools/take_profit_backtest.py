# -*- coding: utf-8 -*-
"""
移动止盈优化回测程序
测试不同止盈策略的效果，结合最优分段止损
"""

import sqlite3
from pathlib import Path
from collections import defaultdict

DB_PATH = Path(__file__).parent.parent / "data" / "dex_monitor.db"

def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def run_take_profit_backtest():
    """运行止盈策略回测"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT token_ca, amount as buy_amount, timestamp as buy_time
        FROM strategy_trades WHERE action = "BUY" ORDER BY timestamp LIMIT 500
    ''')
    buys = cursor.fetchall()
    print(f"分析 {len(buys)} 笔交易...")
    
    # 定义测试场景（全部使用分段止损作为基础）
    scenarios = {
        'A. 基准(50%止盈+分段止损)': {'tp': 0.50, 'trailing_start': None, 'trailing_pct': None, 'staged_tp': False},
        'B. 30%止盈': {'tp': 0.30, 'trailing_start': None, 'trailing_pct': None, 'staged_tp': False},
        'C. 80%止盈': {'tp': 0.80, 'trailing_start': None, 'trailing_pct': None, 'staged_tp': False},
        'D. 移动止盈(涨30%后回撤15%)': {'tp': None, 'trailing_start': 0.30, 'trailing_pct': 0.15, 'staged_tp': False},
        'E. 移动止盈(涨50%后回撤20%)': {'tp': None, 'trailing_start': 0.50, 'trailing_pct': 0.20, 'staged_tp': False},
        'F. 移动止盈(涨30%后回撤10%)': {'tp': None, 'trailing_start': 0.30, 'trailing_pct': 0.10, 'staged_tp': False},
        'G. 分段止盈(30%减50%,60%清)': {'tp': None, 'trailing_start': None, 'trailing_pct': None, 'staged_tp': True, 'tp_levels': [(0.30, 0.5), (0.60, 1.0)]},
        'H. 分段止盈(50%减50%,100%清)': {'tp': None, 'trailing_start': None, 'trailing_pct': None, 'staged_tp': True, 'tp_levels': [(0.50, 0.5), (1.00, 1.0)]},
        'I. 组合(分段止盈+移动止损)': {'tp': None, 'trailing_start': 0.30, 'trailing_pct': 0.15, 'staged_tp': True, 'tp_levels': [(0.30, 0.5), (0.80, 1.0)]},
    }
    
    results = {name: {'total_pnl': 0, 'count': 0, 'wins': 0, 'exit_reasons': defaultdict(int)} 
               for name in scenarios}
    
    for i, buy in enumerate(buys):
        if i % 100 == 0:
            print(f"进度: {i}/{len(buys)}")
        
        cursor.execute('''
            SELECT market_cap FROM api_history
            WHERE token_address = ? AND timestamp > ?
            ORDER BY timestamp LIMIT 180
        ''', (buy['token_ca'], buy['buy_time']))
        
        history = cursor.fetchall()
        if len(history) < 10:
            continue
        
        buy_mc = history[0]['market_cap']
        if not buy_mc or buy_mc <= 0:
            continue
        
        buy_amount = buy['buy_amount']
        
        for name, config in scenarios.items():
            result = simulate_trade_with_take_profit(buy_mc, buy_amount, history, config)
            results[name]['total_pnl'] += result['pnl']
            results[name]['count'] += 1
            if result['pnl'] > 0.001:
                results[name]['wins'] += 1
            results[name]['exit_reasons'][result['exit_reason']] += 1
    
    conn.close()
    
    # 打印结果
    print("\n" + "=" * 85)
    print("【移动止盈策略回测结果】（使用分段止损-15%/-30%作为基础）")
    print("=" * 85)
    print(f"{'策略名称':<35} {'总PnL':<12} {'平均PnL':<12} {'胜率':<8} {'vs基准':<10}")
    print("-" * 85)
    
    baseline_pnl = results['A. 基准(50%止盈+分段止损)']['total_pnl']
    
    for name, data in sorted(results.items(), key=lambda x: x[1]['total_pnl'], reverse=True):
        if data['count'] > 0:
            avg_pnl = data['total_pnl'] / data['count']
            win_rate = data['wins'] / data['count'] * 100
            vs_baseline = (data['total_pnl'] - baseline_pnl) / abs(baseline_pnl) * 100 if baseline_pnl != 0 else 0
            print(f"{name:<35} {data['total_pnl']:>+10.4f} {avg_pnl:>+10.6f} {win_rate:>6.1f}% {vs_baseline:>+8.1f}%")
    
    # 退出原因分析
    print("\n" + "=" * 85)
    print("【退出原因分布（前3名）】")
    print("=" * 85)
    
    sorted_results = sorted(results.items(), key=lambda x: x[1]['total_pnl'], reverse=True)[:3]
    for name, data in sorted_results:
        print(f"\n{name}:")
        for reason, count in sorted(data['exit_reasons'].items(), key=lambda x: -x[1]):
            pct = count / data['count'] * 100 if data['count'] > 0 else 0
            print(f"  {reason}: {count} ({pct:.1f}%)")

def simulate_trade_with_take_profit(buy_mc, buy_amount, history, config):
    """模拟单笔交易"""
    highest_mc = buy_mc
    position = 1.0  # 仓位比例
    realized_pnl = 0  # 已实现收益
    
    for idx, point in enumerate(history):
        mc = point['market_cap']
        if not mc or mc <= 0:
            continue
        
        multiplier = mc / buy_mc
        if mc > highest_mc:
            highest_mc = mc
        
        # 分段止损（-15%减仓50%，-30%清仓）
        if multiplier <= 0.85 and position > 0.5:
            # 减仓50%，记录亏损
            sell_ratio = 0.5
            realized_pnl += (multiplier - 1) * buy_amount * sell_ratio
            position -= sell_ratio
        
        if multiplier <= 0.70 and position > 0:
            # 清仓
            realized_pnl += (multiplier - 1) * buy_amount * position
            return {'pnl': realized_pnl, 'exit_reason': 'stop_loss'}
        
        # 固定止盈
        if config['tp'] and multiplier >= (1 + config['tp']) and position > 0:
            realized_pnl += (multiplier - 1) * buy_amount * position
            return {'pnl': realized_pnl, 'exit_reason': 'take_profit'}
        
        # 分段止盈
        if config['staged_tp'] and 'tp_levels' in config:
            for tp_threshold, tp_ratio in config['tp_levels']:
                if multiplier >= (1 + tp_threshold):
                    if tp_ratio >= 1.0:
                        # 清仓
                        realized_pnl += (multiplier - 1) * buy_amount * position
                        return {'pnl': realized_pnl, 'exit_reason': 'staged_take_profit'}
                    elif position > (1 - tp_ratio + 0.01):
                        # 部分止盈
                        sell_amount = position * tp_ratio
                        realized_pnl += (multiplier - 1) * buy_amount * sell_amount
                        position -= sell_amount
        
        # 移动止盈（从高点回撤）
        if config['trailing_start'] and config['trailing_pct']:
            if highest_mc >= buy_mc * (1 + config['trailing_start']):
                drawdown = (highest_mc - mc) / highest_mc
                if drawdown >= config['trailing_pct'] and position > 0:
                    realized_pnl += (multiplier - 1) * buy_amount * position
                    return {'pnl': realized_pnl, 'exit_reason': 'trailing_take_profit'}
        
        # 超时 60分钟
        if idx >= 60:
            realized_pnl += (multiplier - 1) * buy_amount * position
            return {'pnl': realized_pnl, 'exit_reason': 'timeout'}
    
    # 数据结束
    final_mc = history[-1]['market_cap'] or buy_mc
    final_mult = final_mc / buy_mc
    realized_pnl += (final_mult - 1) * buy_amount * position
    return {'pnl': realized_pnl, 'exit_reason': 'end_of_data'}

if __name__ == "__main__":
    run_take_profit_backtest()
