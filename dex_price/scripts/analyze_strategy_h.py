#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
分析策略 H (Golden Dog Sniper) 的交易表现
"""
import sqlite3
import pandas as pd
import os
import sys

# 确保 Windows 下输出中文正常
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'dex_monitor.db')

def get_connection():
    return sqlite3.connect(DB_PATH)

def analyze_strategy_h():
    print("=== 开始分析策略 H (Strategy H) [金狗狙击] ===")
    
    conn = get_connection()
    
    try:
        # 获取策略状态
        state_df = pd.read_sql_query("SELECT * FROM strategy_states WHERE strategy_type='H'", conn)
        if not state_df.empty:
            balance = state_df.iloc[0]['balance_sol']
            win_count = state_df.iloc[0]['winning_trades']
            loss_count = state_df.iloc[0]['losing_trades']
            total_count = win_count + loss_count
            real_win_rate = (win_count / total_count * 100) if total_count > 0 else 0
            print(f"当前策略余额: {balance:.4f} SOL")
            print(f"数据库记录胜率: {real_win_rate:.2f}% ({win_count} 胜 / {loss_count} 负)")

        df = pd.read_sql_query("SELECT * FROM strategy_trades WHERE strategy_type='H' ORDER BY timestamp", conn)
    except Exception as e:
        print(f"读取数据库失败: {e}")
        conn.close()
        return

    if df.empty:
        print("未找到策略 H 的交易记录。")
        conn.close()
        return

    # 转换时间戳
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # 配对交易
    trades = []
    
    print("正在加载 API 历史数据...")
    try:
        api_df = pd.read_sql_query(
            """
            SELECT token_address as token_ca, timestamp, 
                   txns_m5_buys, txns_m5_sells, volume_m5, 
                   txns_h1_buys, txns_h1_sells, volume_h1, 
                   liquidity_usd, market_cap
            FROM api_history
            """, 
            conn
        )
        api_df['timestamp'] = pd.to_datetime(api_df['timestamp'])
        api_df = api_df.sort_values('timestamp')
    except Exception as e:
        print(f"读取 api_history 失败: {e}")
        conn.close()
        return

    grouped = df.groupby('token_ca')
    
    for ca, group in grouped:
        group = group.sort_values('timestamp')
        pending_buy = None
        
        ca_api_data = api_df[api_df['token_ca'] == ca]
        
        for idx, row in group.iterrows():
            if row['action'] == 'BUY':
                pending_buy = row
            elif row['action'] == 'SELL':
                if pending_buy is not None:
                    buy_time = pending_buy['timestamp']
                    relevant_api = ca_api_data[ca_api_data['timestamp'] <= buy_time]
                    
                    api_metrics = {}
                    if not relevant_api.empty:
                        latest = relevant_api.iloc[-1]
                        time_diff = (buy_time - latest['timestamp']).total_seconds() / 60
                        
                        if time_diff <= 60:
                            api_metrics = {
                                'txns_m5_buys': latest['txns_m5_buys'],
                                'txns_m5_sells': latest['txns_m5_sells'],
                                'volume_m5': latest['volume_m5'],
                                'txns_h1_buys': latest['txns_h1_buys'],
                                'txns_h1_sells': latest['txns_h1_sells'],
                                'volume_h1': latest['volume_h1'],
                                'liquidity': latest['liquidity_usd'],
                            }
                    
                    trade = {
                        'token_ca': ca,
                        'token_name': row['token_name'],
                        'buy_time': buy_time,
                        'buy_mc': pending_buy['price'],
                        'sell_time': row['timestamp'],
                        'sell_mc': row['price'],
                        'pnl': row['pnl'],
                        **api_metrics
                    }
                    trades.append(trade)
                    pending_buy = None

    if not trades:
        print("未找到完整的买卖配对记录。")
        conn.close()
        return
        
    df_trades = pd.DataFrame(trades)
    
    # 基础指标
    total_pnl = df_trades['pnl'].sum()
    print(f"\n[总体表现]")
    print(f"总交易次数: {len(df_trades)}")
    print(f"总盈亏 (PnL): {total_pnl:.4f} SOL")
    print(f"平均每笔盈亏: {df_trades['pnl'].mean():.4f} SOL")
    win_rate = (df_trades['pnl'] > 0).mean() * 100
    print(f"胜率: {win_rate:.2f}%")
    
    # 维度1: 市值分布
    print("\n--- 市值分布 (Market Cap) ---")
    bins = [0, 50000, 100000, 500000, 1000000, 2000000, float('inf')]
    labels = ['<50k', '50k-100k', '100k-500k', '500k-1M', '1M-2M', '>2M']
    df_trades['mc_group'] = pd.cut(df_trades['buy_mc'], bins=bins, labels=labels)
    
    def calc_win_rate(x): return (x > 0).sum() / len(x) * 100 if len(x) > 0 else 0
    def avg_win(x): return x[x > 0].mean() if not x[x > 0].empty else 0
    def avg_loss(x): return x[x <= 0].mean() if not x[x <= 0].empty else 0
    
    print(df_trades.groupby('mc_group', observed=False)['pnl'].agg(['count', 'sum', 'mean', calc_win_rate, avg_win, avg_loss]).to_string())
    
    # 维度2: 1h 交易次数 (热度)
    print("\n--- 1h 交易热度 (Txns) ---")
    # Strategy H 喜欢高热度，看看是否被打脸
    if 'txns_h1_buys' in df_trades.columns:
        df_trades['total_txns_h1'] = df_trades['txns_h1_buys'] + df_trades['txns_h1_sells']
        bins = [0, 1000, 2000, 5000, 10000, float('inf')]
        labels = ['<1k', '1k-2k', '2k-5k', '5k-10k', '>10k']
        df_trades['heat_group'] = pd.cut(df_trades['total_txns_h1'], bins=bins, labels=labels)
        print(df_trades.groupby('heat_group', observed=False)['pnl'].agg(['count', 'sum', 'mean', calc_win_rate]).to_string())
        
    # 维度3: 5m 交易量
    print("\n--- 5m 交易量 (Volume) ---")
    if 'volume_m5' in df_trades.columns:
        bins = [0, 1000, 10000, 50000, 100000, float('inf')]
        labels = ['<1k', '1k-10k', '10k-50k', '50k-100k', '>100k']
        df_trades['vol_group'] = pd.cut(df_trades['volume_m5'], bins=bins, labels=labels)
        print(df_trades.groupby('vol_group', observed=False)['pnl'].agg(['count', 'sum', 'mean', calc_win_rate]).to_string())

    # 深度分析: 止损 vs 复活
    print("\n--- 止损与复活分析 ---")
    # H 的止损也是 30% (之前配置)
    df_trades['roi_approx'] = (df_trades['sell_mc'] - df_trades['buy_mc']) / df_trades['buy_mc']
    
    sl_losses = df_trades[df_trades['roi_approx'] <= -0.20] # 模拟硬止损
    time_exit = df_trades[(df_trades['roi_approx'] > -0.20) & (df_trades['pnl'] < 0)]
    
    print(f"硬止损数量 (>20% loss): {len(sl_losses)} (Total PnL: {sl_losses['pnl'].sum():.4f})")
    print(f"离场数量 (<20% loss): {len(time_exit)} (Total PnL: {time_exit['pnl'].sum():.4f})")
    
    # 检查超时单的复活情况
    print("\n检查超时单是否卖飞 (Resurrection Check)...")
    resurrected_count = 0
    if not time_exit.empty:
        for idx, row in time_exit.iterrows():
            ca = row['token_ca']
            sell_time = row['sell_time']
            sell_mc = row['sell_mc']
            
            future_data = api_df[
                (api_df['token_ca'] == ca) & 
                (api_df['timestamp'] > sell_time) & 
                (api_df['timestamp'] < sell_time + pd.Timedelta(hours=24))
            ]
            
            if not future_data.empty:
                max_mc = future_data['market_cap'].max()
                if max_mc > sell_mc * 1.5:
                    resurrected_count += 1
                    # print(f"  - {row['token_name']} Resurrected! Sell: {sell_mc} -> Max: {max_mc}")
    
    print(f"超时单卖飞数量: {resurrected_count} (占比 {resurrected_count/len(time_exit)*100 if len(time_exit)>0 else 0:.1f}%)")

    # Smart Exit 模拟 (高热度持有 + 30% SL)
    print("\n--- Smart Exit 模拟 (针对 Strategy H) ---")
    # Strategy H 本身就倾向于做高热度的，所以可能大部分都符合 Smart Exit 条件?
    if 'total_txns_h1' in df_trades.columns:
        high_heat_exits = time_exit[time_exit['total_txns_h1'] > 2000].copy()
        print(f"符合高热度 (>2k txns) 的超时单: {len(high_heat_exits)}")
        
        sim_pnl_change = 0
        
        for idx, row in high_heat_exits.iterrows():
            ca = row['token_ca']
            sell_time = row['sell_time']
            buy_mc = row['buy_mc']
            orig_pnl = row['pnl']
            
            future_data = api_df[
                (api_df['token_ca'] == ca) & 
                (api_df['timestamp'] > sell_time) & 
                (api_df['timestamp'] < sell_time + pd.Timedelta(hours=24))
            ].sort_values('timestamp')
            
            new_pnl = orig_pnl
            bet_size = 0.1
            
            outcome = "Hold"
            hit_sl = False
            
            # 模拟 30% 止损
            for _, r in future_data.iterrows():
                curr_mc = r['market_cap']
                change = (curr_mc - buy_mc) / buy_mc
                
                if change <= -0.30:
                    new_pnl = -0.30 * bet_size
                    outcome = "Hit SL -30%"
                    hit_sl = True
                    break
                
                if change >= 0.50:
                    new_pnl = 0.50 * bet_size
                    outcome = "TP +50%"
                    break
            
            # print(f"  - {row['token_name']}: {orig_pnl:.4f} -> {new_pnl:.4f} ({outcome})")
            sim_pnl_change += (new_pnl - orig_pnl)
            
        print(f"Smart Exit (High Heat + 30% SL) 预期收益提升: {sim_pnl_change:.4f} SOL")

    conn.close()

if __name__ == "__main__":
    analyze_strategy_h()
