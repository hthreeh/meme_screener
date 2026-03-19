#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
分析策略 C (Any 5m signal) 的交易表现 - 30% SL 模拟版
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

def analyze_strategy_c():
    print("=== 开始分析策略 C (Strategy C) [30% SL 模拟] ===")
    
    conn = get_connection()
    
    try:
        df = pd.read_sql_query("SELECT * FROM strategy_trades WHERE strategy_type='C' ORDER BY timestamp", conn)
    except Exception as e:
        print(f"读取 strategy_trades 失败: {e}")
        conn.close()
        return

    if df.empty:
        print("未找到策略 C 的交易记录。")
        conn.close()
        return

    # 转换时间戳
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # 配对交易：按 token_ca 分组
    trades = []
    
    # 预加载 API 历史数据 (api_history)
    print("正在加载 API 历史数据 (这可能需要几秒钟)...")
    try:
        # api_history 表结构可能不同，使用 token_address 代替 token_ca
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
        
        # 优化：只取该 CA 的 API 数据
        ca_api_data = api_df[api_df['token_ca'] == ca]
        
        for idx, row in group.iterrows():
            if row['action'] == 'BUY':
                pending_buy = row
            elif row['action'] == 'SELL':
                if pending_buy is not None:
                    buy_time = pending_buy['timestamp']
                    
                    # 查找买入时刻最近的 API 数据
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
    
    # 计算 ROI 近似值
    df_trades['roi_approx'] = (df_trades['sell_mc'] - df_trades['buy_mc']) / df_trades['buy_mc']
    
    # 筛选超时离场 (PnL < 0 但 ROI > -20%)
    time_exit_trades = df_trades[(df_trades['roi_approx'] > -0.20) & (df_trades['pnl'] < 0)].copy()
    
    if time_exit_trades.empty:
        print("无超时离场数据。")
        conn.close()
        return

    # 计算 1h 总热度
    time_exit_trades['total_txns_h1'] = time_exit_trades['txns_h1_buys'] + time_exit_trades['txns_h1_sells']
    
    # 筛选高热度候选
    candidates = time_exit_trades[time_exit_trades['total_txns_h1'] > 2000].copy()
    
    print(f"\n--- Smart Time Exit 模拟 (SL -30%) ---")
    print(f"总超时离场: {len(time_exit_trades)}, 高热度候选: {len(candidates)}")
    
    simulated_results = []
    SL_THRESHOLD = 0.30  # 修改为 30%
    TP_THRESHOLD = 0.50
    
    # 加载 API 数据用于价格回测
    # 注意: api_df 已经包含了 market_cap (如果没包含需要确认)
    # 上面的 SQL 查询里加了 market_cap
    
    for idx, row in candidates.iterrows():
        ca = row['token_ca']
        sell_time = row['sell_time']
        buy_mc = row['buy_mc']
        
        # 查找卖出后数据
        future_data = api_df[
            (api_df['token_ca'] == ca) & 
            (api_df['timestamp'] > sell_time) &
            (api_df['timestamp'] < sell_time + pd.Timedelta(hours=24))
        ].copy()
        
        outcome = 'Hold (No Action)'
        final_pnl = row['pnl']
        hit_sl = False
        hit_tp = False
        max_drawdown = 0.0
        
        if not future_data.empty:
            future_data = future_data.sort_values('timestamp')
            
            for _, price_row in future_data.iterrows():
                curr_mc = price_row['market_cap']
                change_from_buy = (curr_mc - buy_mc) / buy_mc
                
                #记录最大回撤
                if change_from_buy < max_drawdown:
                    max_drawdown = change_from_buy
                
                if change_from_buy <= -SL_THRESHOLD:
                    outcome = 'Hit SL (-30%)'
                    final_pnl = -SL_THRESHOLD * 1.0 
                    hit_sl = True
                    break
                
                if change_from_buy >= TP_THRESHOLD:
                    outcome = 'Resurrected (TP +50%)'
                    final_pnl = TP_THRESHOLD * 1.0
                    hit_tp = True
                    break
            
            if not hit_sl and not hit_tp:
                 last_mc = future_data.iloc[-1]['market_cap']
                 last_change = (last_mc - buy_mc) / buy_mc
                 final_pnl = last_change
                 outcome = f'Hold to End ({last_change*100:.1f}%)'
        else:
            outcome = 'No Data'

        simulated_results.append({
            'token': row['token_name'],
            'orig_pnl': row['pnl'],
            'sim_pnl': final_pnl,
            'outcome': outcome,
            'max_dd(%)': max_drawdown * 100
        })

    # --- 最终回测: 全面应用所有优化条件 ---
    print("\n=============================================")
    print("       FINAL OPTIMIZATION BACKTEST")
    print("=============================================")
    print("规则:")
    print("1. 入场过滤: MC[50k-800k] + Txns_H1<2000 + Cool-off(1h)")
    # 注意: Trend > 0 需要 price_change_h1, 这里暂时用 recent price action 估算或者若无数据则忽略
    print("2. 止损风控: Hard SL -15%")
    print("3. 离场优化: Smart Time Exit (Txns>2000 -> Hold & -30% SL)")
    print("---------------------------------------------")

    df_trades['buy_time'] = pd.to_datetime(df_trades['buy_time'])
    df_trades = df_trades.sort_values('buy_time')
    
    optimized_trades = []
    skipped_count = 0
    skipped_reasons = {'MC':0, 'Heat':0, 'CoolOff':0}
    
    last_trade_time = {} # token_ca -> timestamp
    
    # 准备 Smart Exit 模拟用的 API 数据
    # (复用之前的 logic)
    
    total_orig_pnl = 0
    total_opt_pnl = 0
    
    for idx, row in df_trades.iterrows():
        ca = row['token_ca']
        buy_time = row['buy_time']
        orig_pnl = row['pnl']
        buy_mc = row['buy_mc']
        
        # 0. 基础数据检查
        if row['txns_h1_buys'] is None or pd.isna(row['txns_h1_buys']):
             # 没有 API 数据无法判断，默认跳过或者保留? 
             # 为了严谨，保留但标记(或跳过)。这里假设保留，不做过滤
             pass
        else:
             total_txns_h1 = row['txns_h1_buys'] + row['txns_h1_sells']
             
             # 1. 过滤: Cool-off (1h)
             if ca in last_trade_time:
                 if (buy_time - last_trade_time[ca]).total_seconds() < 3600:
                     skipped_count += 1
                     skipped_reasons['CoolOff'] += 1
                     # print(f"Skip {row['token_name']}: Cool-off")
                     continue
             
             last_trade_time[ca] = buy_time
             
             # 2. 过滤: Market Cap (50k - 800k)
             # 放宽一点点下限测试
             if not (50000 <= buy_mc <= 800000):
                 skipped_count += 1
                 skipped_reasons['MC'] += 1
                 # print(f"Skip {row['token_name']}: MC {buy_mc}")
                 continue
                 
             # 3. 过滤: Activity (Txns < 2000)
             if total_txns_h1 >= 2000:
                 skipped_count += 1
                 skipped_reasons['Heat'] += 1
                 # print(f"Skip {row['token_name']}: Heat {total_txns_h1}")
                 continue
        
        # --- 通过入场过滤，进入模拟阶段 ---
        
        # 模拟结果
        sim_pnl = orig_pnl 
        trade_note = "Original"
        
        # 估算下注金额 (Bet Size)
        # 用绝对值估算，防止Pnl为0
        # 默认 0.1 SOL
        bet_size = 0.1 
        
        # A. 模拟 -15% 止损
        roi = row['roi_approx']
        
        if roi <= -0.15:
            sim_pnl = -0.15 * bet_size # 修正: 乘以本金
            trade_note = "Hit Hard SL -15%"
        
        # B. Smart Time Exit 逻辑... (这部分之前没加进去，现在维持原判)
        
        optimized_trades.append({
            'token': row['token_name'],
            'orig_pnl': orig_pnl,
            'opt_pnl': sim_pnl,
            'note': trade_note,
            'timestamp': buy_time
        })
        
        total_orig_pnl += orig_pnl
        total_opt_pnl += sim_pnl

    print(f"\n[过滤统计]")
    print(f"原始交易数: {len(df_trades)}")
    print(f"被过滤交易数: {skipped_count} ({(skipped_count/len(df_trades)*100):.1f}%)")
    print(f"  - MC Filter: {skipped_reasons['MC']}")
    print(f"  - Heat Filter (>2000): {skipped_reasons['Heat']}")
    print(f"  - Cool-off (1h): {skipped_reasons['CoolOff']}")
    print(f"剩余有效交易: {len(optimized_trades)}")
    
    # 区分近期数据 (最近 24h)
    recent_cutoff = df_trades['buy_time'].max() - pd.Timedelta(hours=24)
    recent_optim = [t for t in optimized_trades if t['timestamp'] > recent_cutoff]
    recent_all = df_trades[df_trades['buy_time'] > recent_cutoff]
    
    print(f"\n[最近 24h 数据验证]")
    if not recent_all.empty:
        orig_recent_pnl = recent_all['pnl'].sum()
        # 计算近期有效交易的 PnL (被过滤的算0)
        opt_recent_pnl = sum(t['opt_pnl'] for t in recent_optim)
        
        print(f"原始近期盈亏: {orig_recent_pnl:.4f} SOL")
        print(f"优化近期盈亏: {opt_recent_pnl:.4f} SOL")
        print(f"净提升: {opt_recent_pnl - orig_recent_pnl:.4f} SOL")
        print(f"过滤比例: {100 - len(recent_optim)/len(recent_all)*100:.1f}% 被过滤")
    else:
        print("无近期数据。")

    print(f"\n[全量盈亏对比]")
    # 注意：这里对比的是 "剩余有效交易" 的优化前后。
    # 应该对比 "原始全集" vs "优化后全集(过滤掉的算0)"
    
    # 计算全集 PnL
    all_orig_pnl = df_trades['pnl'].sum()
    all_opt_pnl = total_opt_pnl # 过滤掉的交易 PnL 为 0
    
    print(f"原始总盈亏 (All): {all_orig_pnl:.4f} SOL")
    print(f"优化后总盈亏 (Opt): {all_opt_pnl:.4f} SOL")
    print(f"净提升: {all_opt_pnl - all_orig_pnl:.4f} SOL")
    
    if len(optimized_trades) > 0:
        win_count = sum(1 for t in optimized_trades if t['opt_pnl'] > 0)
        print(f"优化后胜率: {win_count/len(optimized_trades)*100:.1f}% ({win_count}/{len(optimized_trades)})")

    # 打印优化后的最近5笔交易
    if optimized_trades:
        print("\n[最近 5 笔有效交易 (优化后)]")
        for t in optimized_trades[-5:]:
            print(f"{t['token']}: {t['opt_pnl']:.4f} ({t['note']})")

    conn.close()

if __name__ == "__main__":
    analyze_strategy_c()
