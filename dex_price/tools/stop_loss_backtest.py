# -*- coding: utf-8 -*-
"""
止损机制优化回测程序
测试不同止损策略的效果
"""

import sqlite3
from pathlib import Path
from collections import defaultdict

DB_PATH = Path(__file__).parent.parent / "data" / "dex_monitor.db"

def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def run_stop_loss_backtest():
    """运行止损策略回测"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT token_ca, amount as buy_amount, timestamp as buy_time
        FROM strategy_trades WHERE action = "BUY" ORDER BY timestamp LIMIT 500
    ''')
    buys = cursor.fetchall()
    print(f"分析 {len(buys)} 笔交易...")
    
    # 定义测试场景
    scenarios = {
        'A. 固定-30%止损': {'type': 'fixed', 'threshold': -0.30},
        'B. 固定-25%止损': {'type': 'fixed', 'threshold': -0.25},
        'C. 固定-20%止损': {'type': 'fixed', 'threshold': -0.20},
        'D. 分段止损(-15%/-30%)': {'type': 'staged'},
        'E. 回撤10%止损': {'type': 'trailing', 'threshold': 0.10},
        'F. 回撤15%止损': {'type': 'trailing', 'threshold': 0.15},
        'G. 回撤20%止损': {'type': 'trailing', 'threshold': 0.20},
        'H. 回撤15%+趋势延期': {'type': 'trailing_trend', 'threshold': 0.15},
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
            result = simulate_trade_with_stop_loss(buy_mc, buy_amount, history, config)
            results[name]['total_pnl'] += result['pnl']
            results[name]['count'] += 1
            if result['pnl'] > 0.001:
                results[name]['wins'] += 1
            results[name]['exit_reasons'][result['exit_reason']] += 1
    
    conn.close()
    
    # 打印结果
    print("\n" + "=" * 80)
    print("【止损策略回测结果】")
    print("=" * 80)
    print(f"{'策略名称':<25} {'总PnL':<12} {'平均PnL':<12} {'胜率':<8} {'vs基准':<10}")
    print("-" * 80)
    
    baseline_pnl = results['A. 固定-30%止损']['total_pnl']
    
    for name, data in sorted(results.items(), key=lambda x: x[1]['total_pnl'], reverse=True):
        if data['count'] > 0:
            avg_pnl = data['total_pnl'] / data['count']
            win_rate = data['wins'] / data['count'] * 100
            vs_baseline = (baseline_pnl - data['total_pnl']) / abs(baseline_pnl) * 100 if baseline_pnl != 0 else 0
            print(f"{name:<25} {data['total_pnl']:>+10.4f} {avg_pnl:>+10.6f} {win_rate:>6.1f}% {vs_baseline:>+8.1f}%")
    
    # 退出原因分析
    print("\n" + "=" * 80)
    print("【退出原因分布】")
    print("=" * 80)
    
    for name in ['A. 固定-30%止损', 'F. 回撤15%止损', 'D. 分段止损(-15%/-30%)']:
        if name in results:
            data = results[name]
            print(f"\n{name}:")
            for reason, count in sorted(data['exit_reasons'].items(), key=lambda x: -x[1]):
                pct = count / data['count'] * 100 if data['count'] > 0 else 0
                print(f"  {reason}: {count} ({pct:.1f}%)")

def simulate_trade_with_stop_loss(buy_mc, buy_amount, history, config):
    """模拟单笔交易"""
    highest_mc = buy_mc
    position = 1.0  # 仓位比例
    timeout = 30
    extensions = 0
    
    for idx, point in enumerate(history):
        mc = point['market_cap']
        if not mc or mc <= 0:
            continue
        
        multiplier = mc / buy_mc
        if mc > highest_mc:
            highest_mc = mc
        
        # 止盈 50%
        if multiplier >= 1.50:
            return {'pnl': (multiplier - 1) * buy_amount * position, 'exit_reason': 'take_profit'}
        
        # 移动止盈（涨30%后回撤20%）
        if highest_mc > buy_mc * 1.3:
            drawdown = (highest_mc - mc) / highest_mc
            if drawdown > 0.20:
                return {'pnl': (multiplier - 1) * buy_amount * position, 'exit_reason': 'trailing_profit'}
        
        # 止损逻辑
        if config['type'] == 'fixed':
            if multiplier <= (1 + config['threshold']):
                return {'pnl': (multiplier - 1) * buy_amount, 'exit_reason': 'stop_loss'}
        
        elif config['type'] == 'staged':
            if multiplier <= 0.85 and position > 0.5:  # 跌15%减仓50%
                position = 0.5
            if multiplier <= 0.70:  # 跌30%清仓
                return {'pnl': (multiplier - 1) * buy_amount * position, 'exit_reason': 'stop_loss'}
        
        elif config['type'] == 'trailing':
            if highest_mc > buy_mc:  # 曾经上涨过
                drawdown = (highest_mc - mc) / highest_mc
                if drawdown >= config['threshold']:
                    return {'pnl': (multiplier - 1) * buy_amount, 'exit_reason': 'trailing_stop'}
            # 还需要固定止损兜底
            if multiplier <= 0.70:
                return {'pnl': (multiplier - 1) * buy_amount, 'exit_reason': 'stop_loss'}
        
        elif config['type'] == 'trailing_trend':
            # 趋势延期
            if idx >= timeout:
                if multiplier >= 1.10 and extensions < 2:
                    timeout += 30
                    extensions += 1
                else:
                    return {'pnl': (multiplier - 1) * buy_amount, 'exit_reason': 'timeout'}
            
            # 回撤止损
            if highest_mc > buy_mc:
                drawdown = (highest_mc - mc) / highest_mc
                if drawdown >= config['threshold']:
                    return {'pnl': (multiplier - 1) * buy_amount, 'exit_reason': 'trailing_stop'}
            if multiplier <= 0.70:
                return {'pnl': (multiplier - 1) * buy_amount, 'exit_reason': 'stop_loss'}
        
        # 超时
        if idx >= 60:
            return {'pnl': (multiplier - 1) * buy_amount * position, 'exit_reason': 'timeout'}
    
    # 数据结束
    final_mc = history[-1]['market_cap'] or buy_mc
    return {'pnl': (final_mc / buy_mc - 1) * buy_amount * position, 'exit_reason': 'end_of_data'}

if __name__ == "__main__":
    run_stop_loss_backtest()
