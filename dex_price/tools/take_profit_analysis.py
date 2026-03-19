# -*- coding: utf-8 -*-
"""
移动止盈数据分析
分析历史止盈情况，为优化方案提供数据支撑
"""

import sqlite3
from pathlib import Path
from collections import defaultdict

DB_PATH = Path(__file__).parent.parent / "data" / "dex_monitor.db"

def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def analyze_take_profit_patterns():
    """分析止盈触发时的涨幅分布和后续走势"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT token_ca, amount as buy_amount, timestamp as buy_time
        FROM strategy_trades WHERE action = "BUY" ORDER BY timestamp LIMIT 500
    ''')
    buys = cursor.fetchall()
    print(f"分析 {len(buys)} 笔交易的止盈模式...")
    
    # 分析每笔交易的最大涨幅和最终结果
    max_gain_distribution = {
        '0-20%': {'count': 0, 'avg_final': 0, 'finals': []},
        '20-50%': {'count': 0, 'avg_final': 0, 'finals': []},
        '50-100%': {'count': 0, 'avg_final': 0, 'finals': []},
        '100-200%': {'count': 0, 'avg_final': 0, 'finals': []},
        '200%+': {'count': 0, 'avg_final': 0, 'finals': []},
    }
    
    # 分析不同止盈阈值的效果
    take_profit_thresholds = [30, 50, 80, 100, 150, 200]
    tp_results = {tp: {'pnl': 0, 'count': 0, 'triggered': 0} for tp in take_profit_thresholds}
    
    # 分析回撤后的走势
    drawdown_after_peak = []
    
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
        
        # 计算最大涨幅和最终结果
        max_mc = buy_mc
        max_idx = 0
        for idx, point in enumerate(history):
            mc = point['market_cap']
            if mc and mc > max_mc:
                max_mc = mc
                max_idx = idx
        
        max_gain = (max_mc / buy_mc - 1) * 100  # 最大涨幅百分比
        final_mc = history[-1]['market_cap'] or buy_mc
        final_gain = (final_mc / buy_mc - 1) * 100  # 最终涨幅
        
        # 分组统计
        if max_gain < 20:
            group = '0-20%'
        elif max_gain < 50:
            group = '20-50%'
        elif max_gain < 100:
            group = '50-100%'
        elif max_gain < 200:
            group = '100-200%'
        else:
            group = '200%+'
        
        max_gain_distribution[group]['count'] += 1
        max_gain_distribution[group]['finals'].append(final_gain)
        
        # 测试不同止盈阈值
        for tp in take_profit_thresholds:
            tp_results[tp]['count'] += 1
            triggered = False
            exit_gain = final_gain  # 默认最终收益
            
            for idx, point in enumerate(history[:120]):  # 2小时内
                mc = point['market_cap']
                if not mc:
                    continue
                gain = (mc / buy_mc - 1) * 100
                if gain >= tp:
                    exit_gain = gain
                    triggered = True
                    break
            
            tp_results[tp]['pnl'] += exit_gain / 100 * buy['buy_amount']
            if triggered:
                tp_results[tp]['triggered'] += 1
        
        # 分析达到高点后的回撤
        if max_gain >= 30 and max_idx < len(history) - 10:
            # 计算从高点到数据结束的回撤
            post_peak_min = max_mc
            for point in history[max_idx:]:
                mc = point['market_cap']
                if mc and mc < post_peak_min:
                    post_peak_min = mc
            
            drawdown = (max_mc - post_peak_min) / max_mc * 100
            drawdown_after_peak.append({
                'max_gain': max_gain,
                'final_gain': final_gain,
                'drawdown': drawdown,
                'kept_ratio': final_gain / max_gain if max_gain > 0 else 0
            })
    
    conn.close()
    
    # 打印分析结果
    print("\n" + "=" * 60)
    print("【最大涨幅分布分析】")
    print("=" * 60)
    print(f"{'涨幅范围':<12} {'数量':<8} {'平均最终收益':<15}")
    print("-" * 40)
    
    for group, data in max_gain_distribution.items():
        if data['count'] > 0:
            avg_final = sum(data['finals']) / len(data['finals'])
            print(f"{group:<12} {data['count']:<8} {avg_final:>+10.1f}%")
    
    print("\n" + "=" * 60)
    print("【不同止盈阈值的效果】")
    print("=" * 60)
    print(f"{'止盈阈值':<12} {'触发次数':<10} {'触发率':<10} {'总PnL':<12}")
    print("-" * 50)
    
    for tp, data in sorted(tp_results.items()):
        if data['count'] > 0:
            trigger_rate = data['triggered'] / data['count'] * 100
            print(f"{tp}%止盈      {data['triggered']:<10} {trigger_rate:>6.1f}%    {data['pnl']:>+10.4f}")
    
    print("\n" + "=" * 60)
    print("【达到高点后的回撤分析】")
    print("=" * 60)
    
    if drawdown_after_peak:
        # 按最大涨幅分组
        groups = {'30-50%': [], '50-100%': [], '100%+': []}
        for d in drawdown_after_peak:
            if d['max_gain'] < 50:
                groups['30-50%'].append(d)
            elif d['max_gain'] < 100:
                groups['50-100%'].append(d)
            else:
                groups['100%+'].append(d)
        
        for group, items in groups.items():
            if items:
                avg_drawdown = sum(d['drawdown'] for d in items) / len(items)
                avg_kept = sum(d['kept_ratio'] for d in items) / len(items) * 100
                print(f"最大涨幅 {group}:")
                print(f"  平均从高点回撤: {avg_drawdown:.1f}%")
                print(f"  最终保留收益比例: {avg_kept:.1f}%")
                print(f"  样本数: {len(items)}")

if __name__ == "__main__":
    analyze_take_profit_patterns()
