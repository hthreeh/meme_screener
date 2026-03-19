# -*- coding: utf-8 -*-
"""
数据分析脚本：确定回测参数
分析历史数据，为回测方案提供数据支撑
"""

import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "dex_monitor.db"

def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def analyze_timeout_impact():
    """分析不同超时时间对收益的影响"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT token_ca, amount as buy_amount, timestamp as buy_time
        FROM strategy_trades WHERE action = 'BUY' ORDER BY timestamp
    """)
    
    buys = cursor.fetchall()
    print(f"分析 {len(buys)} 笔买入交易...")
    
    timeout_results = {
        30: {'total_pnl': 0, 'count': 0, 'wins': 0},
        60: {'total_pnl': 0, 'count': 0, 'wins': 0},
        90: {'total_pnl': 0, 'count': 0, 'wins': 0},
        120: {'total_pnl': 0, 'count': 0, 'wins': 0},
        180: {'total_pnl': 0, 'count': 0, 'wins': 0},
        240: {'total_pnl': 0, 'count': 0, 'wins': 0},
    }
    
    sample_count = 0
    for buy in buys[:500]:
        cursor.execute("""
            SELECT market_cap, timestamp FROM api_history
            WHERE token_address = ? AND timestamp > ?
            ORDER BY timestamp LIMIT 300
        """, (buy['token_ca'], buy['buy_time']))
        
        history = cursor.fetchall()
        if len(history) < 10:
            continue
        
        sample_count += 1
        buy_mc = history[0]['market_cap']
        if not buy_mc or buy_mc <= 0:
            continue
        
        for timeout_min in timeout_results.keys():
            try:
                target_time = datetime.fromisoformat(buy['buy_time'].replace('Z', '+00:00')) + timedelta(minutes=timeout_min)
            except:
                target_time = datetime.fromisoformat(buy['buy_time']) + timedelta(minutes=timeout_min)
            
            best_mc = None
            for h in history:
                try:
                    h_time = datetime.fromisoformat(h['timestamp'].replace('Z', '+00:00')) if 'Z' in h['timestamp'] else datetime.fromisoformat(h['timestamp'])
                    if h_time <= target_time and h['market_cap']:
                        best_mc = h['market_cap']
                except:
                    continue
            
            if best_mc and buy_mc > 0:
                multiplier = best_mc / buy_mc
                pnl = (multiplier - 1) * buy['buy_amount']
                timeout_results[timeout_min]['total_pnl'] += pnl
                timeout_results[timeout_min]['count'] += 1
                if multiplier > 1:
                    timeout_results[timeout_min]['wins'] += 1
    
    print(f"\n【不同超时时间的收益分析】(样本: {sample_count})")
    print("-" * 60)
    for timeout, data in sorted(timeout_results.items()):
        if data['count'] > 0:
            avg_pnl = data['total_pnl'] / data['count']
            win_rate = data['wins'] / data['count'] * 100
            print(f"  {timeout:3d}分钟: 平均收益 {avg_pnl:+.6f} SOL, 胜率 {win_rate:.1f}%")
    
    conn.close()
    return timeout_results

def analyze_trend_patterns():
    """分析上升趋势的特征"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT DISTINCT token_ca FROM strategy_trades WHERE action = 'BUY' LIMIT 200")
    tokens = [row['token_ca'] for row in cursor.fetchall()]
    
    trend_patterns = {
        'rising_5m': 0, 'rising_15m': 0, 'rising_30m': 0,
        'total_analyzed': 0,
        'continued_rise_after_rise': 0, 'drop_after_rise': 0,
    }
    
    price_changes = []
    
    for token_ca in tokens:
        cursor.execute("""
            SELECT market_cap, timestamp FROM api_history
            WHERE token_address = ? ORDER BY timestamp LIMIT 120
        """, (token_ca,))
        
        history = cursor.fetchall()
        if len(history) < 60:
            continue
        
        base_mc = None
        base_idx = 0
        for i, h in enumerate(history):
            if h['market_cap'] and h['market_cap'] > 0:
                base_mc = h['market_cap']
                base_idx = i
                break
        
        if not base_mc:
            continue
        
        trend_patterns['total_analyzed'] += 1
        
        changes = {'base_mc': base_mc}
        for cp in [5, 15, 30, 60]:
            idx = base_idx + cp
            if idx < len(history) and history[idx]['market_cap']:
                change = (history[idx]['market_cap'] / base_mc - 1) * 100
                changes[f'{cp}m'] = change
                if change > 0:
                    trend_patterns[f'rising_{cp}m'] = trend_patterns.get(f'rising_{cp}m', 0) + 1
        
        price_changes.append(changes)
        
        if changes.get('30m', 0) > 5:
            if changes.get('60m', 0) > changes.get('30m', 0):
                trend_patterns['continued_rise_after_rise'] += 1
            else:
                trend_patterns['drop_after_rise'] += 1
    
    print(f"\n【上升趋势特征分析】(样本: {trend_patterns['total_analyzed']})")
    print("-" * 60)
    
    if trend_patterns['total_analyzed'] > 0:
        for key in ['rising_5m', 'rising_15m', 'rising_30m']:
            if key in trend_patterns:
                pct = trend_patterns[key] / trend_patterns['total_analyzed'] * 100
                print(f"  {key.replace('rising_', '')}内上涨: {trend_patterns[key]} ({pct:.1f}%)")
        
        rise_count = trend_patterns['continued_rise_after_rise'] + trend_patterns['drop_after_rise']
        if rise_count > 0:
            continue_pct = trend_patterns['continued_rise_after_rise'] / rise_count * 100
            print(f"\n  30分钟涨5%+后:")
            print(f"    继续上涨: {trend_patterns['continued_rise_after_rise']} ({continue_pct:.1f}%)")
            print(f"    开始下跌: {trend_patterns['drop_after_rise']} ({100-continue_pct:.1f}%)")
    
    print(f"\n【趋势延续分析】")
    print("-" * 60)
    
    groups = {'跌超5%': [], '跌0-5%': [], '涨0-5%': [], '涨5-10%': [], '涨10-20%': [], '涨20%+': []}
    
    for change in price_changes:
        if '30m' not in change or '60m' not in change:
            continue
        c30, c60 = change['30m'], change['60m']
        
        if c30 < -5: groups['跌超5%'].append(c60)
        elif c30 < 0: groups['跌0-5%'].append(c60)
        elif c30 < 5: groups['涨0-5%'].append(c60)
        elif c30 < 10: groups['涨5-10%'].append(c60)
        elif c30 < 20: groups['涨10-20%'].append(c60)
        else: groups['涨20%+'].append(c60)
    
    for group, values in groups.items():
        if values:
            avg = sum(values) / len(values)
            print(f"  30分钟{group}: 60分钟平均变化 {avg:+.1f}% (n={len(values)})")
    
    conn.close()
    return trend_patterns, price_changes

def analyze_market_cap_holding():
    """分析市值与最佳持有时间的关系"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT token_ca, timestamp as buy_time FROM strategy_trades
        WHERE action = 'BUY' ORDER BY timestamp LIMIT 500
    """)
    buys = cursor.fetchall()
    
    mc_groups = {
        '<50k': [], '50k-100k': [], '100k-200k': [],
        '200k-500k': [], '500k-1M': [], '>1M': []
    }
    
    for buy in buys:
        cursor.execute("""
            SELECT market_cap FROM api_history
            WHERE token_address = ? AND timestamp > ?
            ORDER BY timestamp LIMIT 240
        """, (buy['token_ca'], buy['buy_time']))
        
        history = cursor.fetchall()
        if len(history) < 10:
            continue
        
        buy_mc = history[0]['market_cap']
        if not buy_mc or buy_mc <= 0:
            continue
        
        # 找最大市值出现的位置（最佳持有时间）
        max_mc, max_idx = buy_mc, 0
        for i, h in enumerate(history):
            if h['market_cap'] and h['market_cap'] > max_mc:
                max_mc, max_idx = h['market_cap'], i
        
        # 分组
        if buy_mc < 50000: group = '<50k'
        elif buy_mc < 100000: group = '50k-100k'
        elif buy_mc < 200000: group = '100k-200k'
        elif buy_mc < 500000: group = '200k-500k'
        elif buy_mc < 1000000: group = '500k-1M'
        else: group = '>1M'
        
        mc_groups[group].append(max_idx)
    
    print(f"\n【市值与最佳持有时间关系】")
    print("-" * 60)
    
    for group, times in mc_groups.items():
        if times:
            avg_time = sum(times) / len(times)
            median_time = sorted(times)[len(times)//2]
            print(f"  市值 {group:12s}: 平均最佳持有 {avg_time:.0f}分钟, 中位数 {median_time}分钟 (n={len(times)})")
    
    conn.close()
    return mc_groups

def analyze_heat_holding():
    """分析热度与最佳持有时间的关系"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT token_ca, timestamp as buy_time FROM strategy_trades
        WHERE action = 'BUY' ORDER BY timestamp LIMIT 500
    """)
    buys = cursor.fetchall()
    
    heat_groups = {'<10': [], '10-30': [], '30-50': [], '50-100': [], '>100': []}
    
    for buy in buys:
        cursor.execute("""
            SELECT market_cap, txns_m5_buys, txns_m5_sells FROM api_history
            WHERE token_address = ? AND timestamp > ?
            ORDER BY timestamp LIMIT 240
        """, (buy['token_ca'], buy['buy_time']))
        
        history = cursor.fetchall()
        if len(history) < 10:
            continue
        
        buy_mc = history[0]['market_cap']
        heat = (history[0]['txns_m5_buys'] or 0) + (history[0]['txns_m5_sells'] or 0)
        
        if not buy_mc or buy_mc <= 0:
            continue
        
        max_mc, max_idx = buy_mc, 0
        for i, h in enumerate(history):
            if h['market_cap'] and h['market_cap'] > max_mc:
                max_mc, max_idx = h['market_cap'], i
        
        if heat < 10: group = '<10'
        elif heat < 30: group = '10-30'
        elif heat < 50: group = '30-50'
        elif heat < 100: group = '50-100'
        else: group = '>100'
        
        heat_groups[group].append(max_idx)
    
    print(f"\n【热度（5分钟交易次数）与最佳持有时间关系】")
    print("-" * 60)
    
    for group, times in heat_groups.items():
        if times:
            avg_time = sum(times) / len(times)
            median_time = sorted(times)[len(times)//2]
            print(f"  热度 {group:8s}: 平均最佳持有 {avg_time:.0f}分钟, 中位数 {median_time}分钟 (n={len(times)})")
    
    conn.close()
    return heat_groups

def main():
    print("=" * 60)
    print("回测参数数据分析")
    print("=" * 60)
    
    timeout_results = analyze_timeout_impact()
    trend_patterns, price_changes = analyze_trend_patterns()
    mc_groups = analyze_market_cap_holding()
    heat_groups = analyze_heat_holding()
    
    print("\n" + "=" * 60)
    print("【参数建议总结】")
    print("=" * 60)
    
    print("\n1. 超时时间测试范围: 60/90/120/180/240 分钟")
    print("2. 上升趋势判断标准:")
    print("   - 方案A: 当前市值 > 买入市值 × 1.10 (涨10%+)")
    print("   - 方案B: 近15分钟涨幅 > 5%")
    print("3. 市值/热度分段持有策略（基于数据分析）")

if __name__ == "__main__":
    main()
