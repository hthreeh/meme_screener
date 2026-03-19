# -*- coding: utf-8 -*-
"""快速测试：热度分段 + 趋势延期"""
import sqlite3
from pathlib import Path
from collections import defaultdict

DB_PATH = Path(__file__).parent.parent / "data" / "dex_monitor.db"

def get_timeout_by_heat(heat_5m):
    if heat_5m < 10: return 45
    elif heat_5m < 30: return 80
    elif heat_5m < 50: return 60
    elif heat_5m < 100: return 50
    else: return 55

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute('SELECT token_ca, amount as buy_amount, timestamp as buy_time FROM strategy_trades WHERE action = "BUY" ORDER BY timestamp LIMIT 500')
buys = cursor.fetchall()
print(f"分析 {len(buys)} 笔交易...")

results = {'total_pnl': 0, 'wins': 0, 'losses': 0, 'total': 0, 'extended': 0, 'exit_reasons': defaultdict(int)}

for i, buy in enumerate(buys):
    if i % 50 == 0:
        print(f"进度: {i}/{len(buys)}")
    
    cursor.execute('''SELECT market_cap, txns_m5_buys, txns_m5_sells FROM api_history 
                      WHERE token_address = ? AND timestamp > ? ORDER BY timestamp LIMIT 300''', 
                   (buy['token_ca'], buy['buy_time']))
    history = cursor.fetchall()
    if len(history) < 10: continue
    
    buy_mc = history[0]['market_cap']
    if not buy_mc or buy_mc <= 0: continue
    
    heat = (history[0]['txns_m5_buys'] or 0) + (history[0]['txns_m5_sells'] or 0)
    timeout = get_timeout_by_heat(heat)
    extensions = 0
    highest_mc = buy_mc
    extended = False
    exited = False
    
    for idx, point in enumerate(history):
        current_mc = point['market_cap']
        if not current_mc or current_mc <= 0: continue
        
        multiplier = current_mc / buy_mc
        if current_mc > highest_mc: highest_mc = current_mc
        
        if multiplier <= 0.70:
            pnl = (multiplier - 1) * buy['buy_amount']
            results['total_pnl'] += pnl
            results['total'] += 1
            results['losses'] += 1
            results['exit_reasons']['stop_loss'] += 1
            exited = True
            break
        
        if multiplier >= 1.50:
            pnl = (multiplier - 1) * buy['buy_amount']
            results['total_pnl'] += pnl
            results['total'] += 1
            results['wins'] += 1
            results['exit_reasons']['take_profit'] += 1
            exited = True
            break
        
        if highest_mc > buy_mc * 1.3:
            drawdown = (highest_mc - current_mc) / highest_mc
            if drawdown > 0.20:
                pnl = (multiplier - 1) * buy['buy_amount']
                results['total_pnl'] += pnl
                results['total'] += 1
                if multiplier > 1: results['wins'] += 1
                else: results['losses'] += 1
                results['exit_reasons']['trailing_stop'] += 1
                exited = True
                break
        
        if idx >= timeout:
            if multiplier >= 1.10 and extensions < 2:
                timeout += 30
                extensions += 1
                extended = True
            else:
                pnl = (multiplier - 1) * buy['buy_amount']
                results['total_pnl'] += pnl
                results['total'] += 1
                if multiplier > 1.001: results['wins'] += 1
                elif multiplier < 0.999: results['losses'] += 1
                results['exit_reasons']['timeout'] += 1
                if extended: results['extended'] += 1
                exited = True
                break
    
    if not exited and history:
        final_mc = history[-1]['market_cap'] or buy_mc
        multiplier = final_mc / buy_mc
        pnl = (multiplier - 1) * buy['buy_amount']
        results['total_pnl'] += pnl
        results['total'] += 1
        results['exit_reasons']['end_of_data'] += 1

conn.close()

print('=' * 60)
print('热度分段 + 趋势延期 组合回测结果')
print('=' * 60)
if results['total'] > 0:
    print(f"总交易数: {results['total']}")
    print(f"总 PnL: {results['total_pnl']:+.4f} SOL")
    print(f"平均 PnL: {results['total_pnl']/results['total']:+.6f} SOL")
    print(f"胜率: {results['wins']/results['total']*100:.1f}%")
    print(f"延期次数: {results['extended']}")
    print()
    print('退出原因:')
    for reason, count in sorted(results['exit_reasons'].items(), key=lambda x: -x[1]):
        print(f"  {reason}: {count} ({count/results['total']*100:.1f}%)")

    baseline = -2.6158
    trend_only = -2.3688
    heat_only = -2.4342
    mc_trend = -2.4914
    current = results['total_pnl']
    print()
    print('与其他方案对比:')
    print(f"  vs 基准(30分钟): {(baseline-current)/abs(baseline)*100:+.1f}%")
    print(f"  vs 趋势延期: {(trend_only-current)/abs(trend_only)*100:+.1f}%")
    print(f"  vs 热度分段: {(heat_only-current)/abs(heat_only)*100:+.1f}%")
    print(f"  vs 市值+趋势: {(mc_trend-current)/abs(mc_trend)*100:+.1f}%")
