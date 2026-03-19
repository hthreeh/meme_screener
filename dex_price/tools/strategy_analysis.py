# -*- coding: utf-8 -*-
"""
策略改进方向分析脚本
分析入场质量 vs 出场时机，确定优化大方向
"""

import sqlite3
import json
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "dex_monitor.db"

def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def analyze_trades():
    """分析所有交易记录"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. 获取所有交易记录，匹配买入和卖出
    cursor.execute("""
        SELECT 
            strategy_type,
            token_ca,
            token_name,
            action,
            price,
            amount,
            pnl,
            timestamp
        FROM strategy_trades
        ORDER BY token_ca, timestamp
    """)
    
    trades = cursor.fetchall()
    
    # 按 token_ca + strategy 配对买入和卖出
    trade_pairs = defaultdict(list)
    for t in trades:
        key = (t['strategy_type'], t['token_ca'])
        trade_pairs[key].append(dict(t))
    
    # 分析结果
    results = {
        'total_buys': 0,
        'total_sells': 0,
        'matched_pairs': 0,
        'entry_analysis': {
            'immediate_loss': 0,  # 买入后立即亏损（第一次检查就亏）
            'never_profit': 0,   # 从未盈利过
            'had_profit_but_lost': 0,  # 曾经盈利但最终亏损
            'profitable_exit': 0,  # 盈利退出
        },
        'exit_analysis': {
            'stop_loss': 0,       # 止损 -30%
            'timeout_loss': 0,    # 超时亏损离场
            'timeout_flat': 0,    # 超时保本离场  
            'breakeven': 0,       # 保本止损
            'take_profit': 0,     # 止盈
            'trailing_profit': 0, # 移动止盈
            'manual': 0,          # 手动
        },
        'pnl_by_exit': defaultdict(float),
        'count_by_exit': defaultdict(int),
        'strategy_summary': defaultdict(lambda: {
            'buys': 0, 'sells': 0, 'total_pnl': 0,
            'wins': 0, 'losses': 0, 'flat': 0
        })
    }
    
    for key, pair_trades in trade_pairs.items():
        strategy, token_ca = key
        buys = [t for t in pair_trades if t['action'] == 'BUY']
        sells = [t for t in pair_trades if t['action'] == 'SELL']
        
        results['total_buys'] += len(buys)
        results['total_sells'] += len(sells)
        results['strategy_summary'][strategy]['buys'] += len(buys)
        results['strategy_summary'][strategy]['sells'] += len(sells)
        
        for sell in sells:
            pnl = sell['pnl'] or 0
            results['strategy_summary'][strategy]['total_pnl'] += pnl
            if pnl > 0.001:
                results['strategy_summary'][strategy]['wins'] += 1
            elif pnl < -0.001:
                results['strategy_summary'][strategy]['losses'] += 1
            else:
                results['strategy_summary'][strategy]['flat'] += 1
    
    conn.close()
    return results

def analyze_exit_reasons_from_logs():
    """从日志分析退出原因分布"""
    logs_dir = Path(__file__).parent.parent / "data" / "logs"
    
    exit_reasons = defaultdict(lambda: {'count': 0, 'total_pnl': 0.0})
    
    # 读取所有 trades.log 文件
    for log_file in logs_dir.glob("trades.log*"):
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if 'SELL' not in line:
                        continue
                    
                    # 解析退出原因
                    reason = 'unknown'
                    if '止损(-30%)' in line or 'stop_loss' in line.lower():
                        reason = 'stop_loss_30'
                    elif '保本止损' in line or 'breakeven' in line.lower():
                        reason = 'breakeven'
                    elif '超时离场' in line or 'timeout' in line.lower():
                        if '亏损' in line:
                            reason = 'timeout_loss'
                        else:
                            reason = 'timeout_flat'
                    elif '止盈' in line or 'take_profit' in line.lower():
                        reason = 'take_profit'
                    elif '移动止损' in line or 'trailing' in line.lower():
                        reason = 'trailing_stop'
                    elif '手动' in line or 'manual' in line.lower():
                        reason = 'manual'
                    
                    # 提取 PnL
                    pnl = 0.0
                    if 'pnl=' in line.lower():
                        try:
                            pnl_str = line.lower().split('pnl=')[1].split()[0].replace('sol', '').strip()
                            pnl = float(pnl_str)
                        except:
                            pass
                    elif 'PnL:' in line:
                        try:
                            pnl_str = line.split('PnL:')[1].split()[0].replace('SOL', '').strip()
                            pnl = float(pnl_str)
                        except:
                            pass
                    
                    exit_reasons[reason]['count'] += 1
                    exit_reasons[reason]['total_pnl'] += pnl
        except Exception as e:
            print(f"Error reading {log_file}: {e}")
    
    return dict(exit_reasons)

def analyze_position_history():
    """分析持仓历史，了解价格走势"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 获取有交易记录的代币的 API 历史数据
    cursor.execute("""
        SELECT DISTINCT token_ca FROM strategy_trades WHERE action = 'BUY'
    """)
    traded_tokens = [row['token_ca'] for row in cursor.fetchall()]
    
    # 分析每个代币买入后的价格走势
    analysis = {
        'tokens_analyzed': 0,
        'immediate_drop': 0,  # 买入后 5 分钟内下跌
        'max_profit_avg': 0,  # 平均最大盈利倍数
        'final_outcome': {'profit': 0, 'loss': 0, 'flat': 0}
    }
    
    max_profits = []
    
    for token_ca in traded_tokens[:100]:  # 取样 100 个
        # 获取该代币的买入记录
        cursor.execute("""
            SELECT timestamp, price FROM strategy_trades 
            WHERE token_ca = ? AND action = 'BUY'
            ORDER BY timestamp
            LIMIT 1
        """, (token_ca,))
        buy = cursor.fetchone()
        if not buy:
            continue
        
        # 获取买入后的 API 历史数据
        cursor.execute("""
            SELECT market_cap, price_usd as price, timestamp FROM api_history
            WHERE token_address = ? AND timestamp > ?
            ORDER BY timestamp
            LIMIT 60
        """, (token_ca, buy['timestamp']))
        
        history = cursor.fetchall()
        if not history or len(history) < 2:
            continue
        
        analysis['tokens_analyzed'] += 1
        
        # 计算最大涨幅
        buy_mc = history[0]['market_cap'] if history else 0
        if buy_mc and buy_mc > 0:
            max_mc = max(h['market_cap'] for h in history if h['market_cap'])
            max_multiplier = max_mc / buy_mc if buy_mc > 0 else 1
            max_profits.append(max_multiplier)
            
            # 检查是否立即下跌（前5条记录）
            early_history = history[:5]
            if early_history:
                early_max = max(h['market_cap'] for h in early_history if h['market_cap'])
                if early_max < buy_mc * 0.95:  # 5分钟内跌超5%
                    analysis['immediate_drop'] += 1
    
    if max_profits:
        analysis['max_profit_avg'] = sum(max_profits) / len(max_profits)
        analysis['max_profit_median'] = sorted(max_profits)[len(max_profits)//2]
        analysis['reached_1_5x'] = sum(1 for p in max_profits if p >= 1.5) / len(max_profits) * 100
        analysis['reached_2x'] = sum(1 for p in max_profits if p >= 2.0) / len(max_profits) * 100
        analysis['reached_3x'] = sum(1 for p in max_profits if p >= 3.0) / len(max_profits) * 100
    
    conn.close()
    return analysis

def analyze_entry_quality():
    """深入分析入场质量"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 获取所有买入交易及其后续卖出
    cursor.execute("""
        SELECT 
            t1.strategy_type,
            t1.token_ca,
            t1.token_name,
            t1.amount as buy_amount,
            t1.timestamp as buy_time,
            t2.pnl as sell_pnl,
            t2.timestamp as sell_time
        FROM strategy_trades t1
        LEFT JOIN strategy_trades t2 ON 
            t1.token_ca = t2.token_ca AND 
            t1.strategy_type = t2.strategy_type AND
            t2.action = 'SELL' AND
            t2.timestamp > t1.timestamp
        WHERE t1.action = 'BUY'
        ORDER BY t1.timestamp
    """)
    
    trades = cursor.fetchall()
    
    # 分析入场质量: 买入后有多少比例能达到某个盈利水平
    entry_stats = {
        'total_entries': len(trades),
        'with_exit': 0,
        'profitable_exits': 0,
        'loss_exits': 0,
        'flat_exits': 0,
        'avg_pnl': 0,
        'by_strategy': defaultdict(lambda: {
            'entries': 0, 'profitable': 0, 'loss': 0, 'flat': 0, 'total_pnl': 0
        })
    }
    
    total_pnl = 0
    for t in trades:
        strategy = t['strategy_type']
        entry_stats['by_strategy'][strategy]['entries'] += 1
        
        if t['sell_pnl'] is not None:
            entry_stats['with_exit'] += 1
            pnl = t['sell_pnl']
            total_pnl += pnl
            entry_stats['by_strategy'][strategy]['total_pnl'] += pnl
            
            if pnl > 0.001:
                entry_stats['profitable_exits'] += 1
                entry_stats['by_strategy'][strategy]['profitable'] += 1
            elif pnl < -0.001:
                entry_stats['loss_exits'] += 1
                entry_stats['by_strategy'][strategy]['loss'] += 1
            else:
                entry_stats['flat_exits'] += 1
                entry_stats['by_strategy'][strategy]['flat'] += 1
    
    if entry_stats['with_exit'] > 0:
        entry_stats['avg_pnl'] = total_pnl / entry_stats['with_exit']
        entry_stats['win_rate'] = entry_stats['profitable_exits'] / entry_stats['with_exit'] * 100
    
    conn.close()
    return entry_stats

def analyze_missed_opportunities():
    """分析错过的机会：超时离场后价格继续上涨的情况"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 获取所有卖出交易
    cursor.execute("""
        SELECT 
            strategy_type,
            token_ca,
            token_name,
            pnl,
            timestamp as sell_time
        FROM strategy_trades
        WHERE action = 'SELL'
        ORDER BY timestamp
    """)
    
    sells = cursor.fetchall()
    
    missed = {
        'total_sells': len(sells),
        'checked': 0,
        'missed_profit': 0,  # 卖出后还涨了的
        'good_exit': 0,      # 卖出后继续跌的
        'avg_missed_multiplier': 0
    }
    
    missed_multipliers = []
    
    for sell in sells[:200]:  # 取样
        # 查看卖出后 30 分钟的价格走势
        cursor.execute("""
            SELECT market_cap, timestamp FROM api_history
            WHERE token_address = ? AND timestamp > ?
            ORDER BY timestamp
            LIMIT 30
        """, (sell['token_ca'], sell['sell_time']))
        
        future = cursor.fetchall()
        if not future or len(future) < 5:
            continue
        
        missed['checked'] += 1
        
        # 计算卖出后的最高价
        sell_mc = future[0]['market_cap'] if future[0]['market_cap'] else 0
        if sell_mc > 0:
            max_after = max(h['market_cap'] for h in future if h['market_cap'])
            multiplier = max_after / sell_mc if sell_mc > 0 else 1
            
            if multiplier > 1.2:  # 卖出后涨了20%以上
                missed['missed_profit'] += 1
                missed_multipliers.append(multiplier)
            else:
                missed['good_exit'] += 1
    
    if missed_multipliers:
        missed['avg_missed_multiplier'] = sum(missed_multipliers) / len(missed_multipliers)
    
    if missed['checked'] > 0:
        missed['missed_rate'] = missed['missed_profit'] / missed['checked'] * 100
    
    conn.close()
    return missed

def main():
    print("=" * 60)
    print("策略改进方向分析报告")
    print("=" * 60)
    
    # 1. 基础交易统计
    print("\n【1. 基础交易统计】")
    trades = analyze_trades()
    print(f"  总买入: {trades['total_buys']}")
    print(f"  总卖出: {trades['total_sells']}")
    print(f"\n  各策略表现:")
    for strategy, stats in sorted(trades['strategy_summary'].items()):
        win_rate = stats['wins'] / stats['sells'] * 100 if stats['sells'] > 0 else 0
        print(f"    {strategy}: 买{stats['buys']} 卖{stats['sells']} "
              f"胜率{win_rate:.1f}% PnL={stats['total_pnl']:.4f}SOL")
    
    # 2. 退出原因分析
    print("\n【2. 退出原因分析 (从日志)】")
    exits = analyze_exit_reasons_from_logs()
    total_exits = sum(e['count'] for e in exits.values())
    print(f"  总退出次数: {total_exits}")
    for reason, data in sorted(exits.items(), key=lambda x: -x[1]['count']):
        pct = data['count'] / total_exits * 100 if total_exits > 0 else 0
        print(f"    {reason}: {data['count']}次 ({pct:.1f}%) PnL={data['total_pnl']:.4f}SOL")
    
    # 3. 入场质量分析
    print("\n【3. 入场质量分析】")
    entry = analyze_entry_quality()
    print(f"  总入场: {entry['total_entries']}")
    print(f"  有退出记录: {entry['with_exit']}")
    if entry['with_exit'] > 0:
        print(f"  整体胜率: {entry['win_rate']:.1f}%")
        print(f"  平均 PnL: {entry['avg_pnl']:.6f} SOL")
        print(f"  盈利退出: {entry['profitable_exits']} ({entry['profitable_exits']/entry['with_exit']*100:.1f}%)")
        print(f"  亏损退出: {entry['loss_exits']} ({entry['loss_exits']/entry['with_exit']*100:.1f}%)")
        print(f"  持平退出: {entry['flat_exits']} ({entry['flat_exits']/entry['with_exit']*100:.1f}%)")
    
    # 4. 持仓走势分析
    print("\n【4. 买入后价格走势分析 (取样)】")
    history = analyze_position_history()
    print(f"  分析代币数: {history['tokens_analyzed']}")
    if history['tokens_analyzed'] > 0:
        print(f"  买入后立即下跌 (5分钟内跌>5%): {history['immediate_drop']} "
              f"({history['immediate_drop']/history['tokens_analyzed']*100:.1f}%)")
        print(f"  平均最大涨幅: {history.get('max_profit_avg', 0):.2f}x")
        print(f"  中位数最大涨幅: {history.get('max_profit_median', 0):.2f}x")
        print(f"  曾达到 1.5x: {history.get('reached_1_5x', 0):.1f}%")
        print(f"  曾达到 2x: {history.get('reached_2x', 0):.1f}%")
        print(f"  曾达到 3x: {history.get('reached_3x', 0):.1f}%")
    
    # 5. 错过机会分析
    print("\n【5. 卖出后走势分析 (错过机会)】")
    missed = analyze_missed_opportunities()
    print(f"  检查卖出数: {missed['checked']}")
    if missed['checked'] > 0:
        print(f"  卖出后继续涨20%+: {missed['missed_profit']} ({missed.get('missed_rate', 0):.1f}%)")
        print(f"  卖出决定正确: {missed['good_exit']} ({missed['good_exit']/missed['checked']*100:.1f}%)")
        if missed['missed_profit'] > 0:
            print(f"  错过的平均涨幅: {missed['avg_missed_multiplier']:.2f}x")
    
    # 6. 结论
    print("\n" + "=" * 60)
    print("【结论分析】")
    print("=" * 60)
    
    # 计算关键指标
    if entry['with_exit'] > 0:
        loss_rate = entry['loss_exits'] / entry['with_exit']
        
        if loss_rate > 0.5:
            print(f"\n⚠️ 亏损率 {loss_rate*100:.1f}% 过高")
            
            # 判断是入场问题还是出场问题
            immediate_drop_rate = history.get('immediate_drop', 0) / max(history.get('tokens_analyzed', 1), 1)
            missed_rate = missed.get('missed_rate', 0) / 100
            
            print(f"\n入场质量指标:")
            print(f"  - 买入后立即下跌比例: {immediate_drop_rate*100:.1f}%")
            print(f"  - 曾达到1.5x止盈线: {history.get('reached_1_5x', 0):.1f}%")
            
            print(f"\n出场时机指标:")
            print(f"  - 卖出后继续大涨比例: {missed_rate*100:.1f}%")
            
            if immediate_drop_rate > 0.3:
                print(f"\n📊 建议方向: 【增强入场过滤】")
                print(f"   原因: {immediate_drop_rate*100:.1f}% 的交易买入后立即下跌，说明入场信号质量不佳")
            elif missed_rate > 0.3:
                print(f"\n📊 建议方向: 【优化出场逻辑】")
                print(f"   原因: {missed_rate*100:.1f}% 的交易卖出后继续上涨，说明离场过早")
            else:
                print(f"\n📊 建议方向: 【两者兼顾，但优先入场】")
                print(f"   原因: 入场质量和出场时机都有改进空间")

if __name__ == "__main__":
    main()
