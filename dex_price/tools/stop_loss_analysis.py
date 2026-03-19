# -*- coding: utf-8 -*-
"""
止损机制数据分析
分析历史止损情况，为优化方案提供数据支撑
"""

import sqlite3
from pathlib import Path
from collections import defaultdict
from datetime import datetime

DB_PATH = Path(__file__).parent.parent / "data" / "dex_monitor.db"

def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def analyze_stop_loss_distribution():
    """分析止损触发时的跌幅分布"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT token_ca, amount as buy_amount, timestamp as buy_time
        FROM strategy_trades WHERE action = "BUY" ORDER BY timestamp LIMIT 500
    ''')
    buys = cursor.fetchall()
    print(f"分析 {len(buys)} 笔交易的止损分布...")
    
    # 跟踪每笔交易的最大回撤和最终结果
    drawdown_distribution = {
        '0-10%': {'count': 0, 'recovered': 0, 'final_loss': 0},
        '10-15%': {'count': 0, 'recovered': 0, 'final_loss': 0},
        '15-20%': {'count': 0, 'recovered': 0, 'final_loss': 0},
        '20-25%': {'count': 0, 'recovered': 0, 'final_loss': 0},
        '25-30%': {'count': 0, 'recovered': 0, 'final_loss': 0},
        '30%+': {'count': 0, 'recovered': 0, 'final_loss': 0},
    }
    
    # 分析每笔交易的价格走势
    recovery_after_dip = []  # 跌N%后反弹的情况
    
    for i, buy in enumerate(buys):
        if i % 100 == 0:
            print(f"进度: {i}/{len(buys)}")
        
        cursor.execute('''
            SELECT market_cap FROM api_history
            WHERE token_address = ? AND timestamp > ?
            ORDER BY timestamp LIMIT 240
        ''', (buy['token_ca'], buy['buy_time']))
        
        history = cursor.fetchall()
        if len(history) < 10:
            continue
        
        buy_mc = history[0]['market_cap']
        if not buy_mc or buy_mc <= 0:
            continue
        
        # 计算最大回撤和后续走势
        min_mc = buy_mc
        max_mc_after_min = buy_mc
        min_idx = 0
        
        for idx, point in enumerate(history):
            mc = point['market_cap']
            if not mc or mc <= 0:
                continue
            
            if mc < min_mc:
                min_mc = mc
                min_idx = idx
                max_mc_after_min = mc  # 重置
            elif idx > min_idx:
                if mc > max_mc_after_min:
                    max_mc_after_min = mc
        
        max_drawdown = (buy_mc - min_mc) / buy_mc * 100  # 最大回撤百分比
        recovery = (max_mc_after_min - min_mc) / min_mc * 100 if min_mc > 0 else 0  # 反弹百分比
        final_mc = history[-1]['market_cap'] or buy_mc
        final_pnl = (final_mc - buy_mc) / buy_mc * 100  # 最终收益百分比
        
        # 分组统计
        if max_drawdown < 10:
            group = '0-10%'
        elif max_drawdown < 15:
            group = '10-15%'
        elif max_drawdown < 20:
            group = '15-20%'
        elif max_drawdown < 25:
            group = '20-25%'
        elif max_drawdown < 30:
            group = '25-30%'
        else:
            group = '30%+'
        
        drawdown_distribution[group]['count'] += 1
        if final_pnl > 0:
            drawdown_distribution[group]['recovered'] += 1
        else:
            drawdown_distribution[group]['final_loss'] += 1
        
        # 记录跌幅和反弹情况
        recovery_after_dip.append({
            'max_drawdown': max_drawdown,
            'recovery': recovery,
            'final_pnl': final_pnl,
            'recovered_to_profit': final_pnl > 0
        })
    
    conn.close()
    
    # 打印分析结果
    print("\n" + "=" * 60)
    print("【最大回撤分布分析】")
    print("=" * 60)
    print(f"{'回撤范围':<12} {'数量':<8} {'最终盈利':<10} {'最终亏损':<10} {'反弹率':<10}")
    print("-" * 60)
    
    for group, data in drawdown_distribution.items():
        if data['count'] > 0:
            recovery_rate = data['recovered'] / data['count'] * 100
            print(f"{group:<12} {data['count']:<8} {data['recovered']:<10} {data['final_loss']:<10} {recovery_rate:.1f}%")
    
    # 分析不同止损点的效果
    print("\n" + "=" * 60)
    print("【不同止损阈值的效果分析】")
    print("=" * 60)
    
    for threshold in [10, 15, 20, 25, 30]:
        # 计算如果在threshold%止损会怎样
        would_stop = [r for r in recovery_after_dip if r['max_drawdown'] >= threshold]
        would_recover = [r for r in would_stop if r['final_pnl'] > 0]
        
        if would_stop:
            miss_rate = len(would_recover) / len(would_stop) * 100
            avg_missed_gain = sum(r['final_pnl'] for r in would_recover) / len(would_recover) if would_recover else 0
            print(f"  止损线 -{threshold}%:")
            print(f"    触发次数: {len(would_stop)}")
            print(f"    错过反弹: {len(would_recover)} ({miss_rate:.1f}%)")
            print(f"    错过平均收益: {avg_missed_gain:+.1f}%")
    
    # 分析回撤止损（从最高点回撤）的效果
    print("\n" + "=" * 60)
    print("【回撤止损分析（从最高点回撤）】")
    print("=" * 60)
    
    analyze_trailing_stop_loss(buys, conn)
    
    return recovery_after_dip

def analyze_trailing_stop_loss(buys, conn):
    """分析从最高点回撤的止损效果"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT token_ca, amount as buy_amount, timestamp as buy_time
        FROM strategy_trades WHERE action = "BUY" ORDER BY timestamp LIMIT 500
    ''')
    buys = cursor.fetchall()
    
    trailing_results = {
        10: {'total_pnl': 0, 'count': 0, 'wins': 0},
        15: {'total_pnl': 0, 'count': 0, 'wins': 0},
        20: {'total_pnl': 0, 'count': 0, 'wins': 0},
        25: {'total_pnl': 0, 'count': 0, 'wins': 0},
        30: {'total_pnl': 0, 'count': 0, 'wins': 0},
    }
    
    for buy in buys:
        cursor.execute('''
            SELECT market_cap FROM api_history
            WHERE token_address = ? AND timestamp > ?
            ORDER BY timestamp LIMIT 120
        ''', (buy['token_ca'], buy['buy_time']))
        
        history = cursor.fetchall()
        if len(history) < 10:
            continue
        
        buy_mc = history[0]['market_cap']
        if not buy_mc or buy_mc <= 0:
            continue
        
        for trailing_pct in trailing_results.keys():
            highest_mc = buy_mc
            exit_mc = None
            
            for point in history:
                mc = point['market_cap']
                if not mc or mc <= 0:
                    continue
                
                if mc > highest_mc:
                    highest_mc = mc
                
                # 检查从最高点回撤
                if highest_mc > buy_mc:  # 只有涨过才触发
                    drawdown_from_high = (highest_mc - mc) / highest_mc * 100
                    if drawdown_from_high >= trailing_pct:
                        exit_mc = mc
                        break
            
            if exit_mc is None:
                exit_mc = history[-1]['market_cap'] or buy_mc
            
            pnl = (exit_mc / buy_mc - 1) * buy['buy_amount']
            trailing_results[trailing_pct]['total_pnl'] += pnl
            trailing_results[trailing_pct]['count'] += 1
            if exit_mc > buy_mc:
                trailing_results[trailing_pct]['wins'] += 1
    
    conn.close()
    
    print(f"{'回撤阈值':<12} {'总PnL':<15} {'平均PnL':<15} {'胜率':<10}")
    print("-" * 55)
    for pct, data in trailing_results.items():
        if data['count'] > 0:
            avg_pnl = data['total_pnl'] / data['count']
            win_rate = data['wins'] / data['count'] * 100
            print(f"回撤{pct}%止损   {data['total_pnl']:>+10.4f}   {avg_pnl:>+12.6f}   {win_rate:>6.1f}%")

if __name__ == "__main__":
    analyze_stop_loss_distribution()
