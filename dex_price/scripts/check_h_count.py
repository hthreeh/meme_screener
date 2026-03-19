import sqlite3
import pandas as pd
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'dex_monitor.db')

conn = sqlite3.connect(DB_PATH)
try:
    cursor = conn.cursor()
    cursor.execute("SELECT action, count(*) FROM strategy_trades WHERE strategy_type='H' GROUP BY action")
    print("Counts by Action:")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}")
        
    cursor.execute("SELECT count(*) FROM strategy_trades WHERE strategy_type='H'")
    total = cursor.fetchone()[0]
    print(f"Total Rows: {total}")
    
    # Check for open positions
    df = pd.read_sql_query("SELECT * FROM strategy_trades WHERE strategy_type='H' ORDER BY timestamp", conn)
    
    trades = 0
    open_pos = 0
    grouped = df.groupby('token_ca')
    for ca, group in grouped:
        buy_count = len(group[group['action'] == 'BUY'])
        sell_count = len(group[group['action'] == 'SELL'])
        
        trades += min(buy_count, sell_count)
        if buy_count > sell_count:
            open_pos += (buy_count - sell_count)
            print(f"Open Position: {ca} (Buys: {buy_count}, Sells: {sell_count})")
            
    print(f"Calculated Completed Trades: {trades}")
    print(f"Calculated Open Positions: {open_pos}")

finally:
    conn.close()
