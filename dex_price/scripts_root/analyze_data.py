
import sqlite3
import pandas as pd
from datetime import datetime
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Connect to database
db_path = 'data/dex_monitor.db'
conn = sqlite3.connect(db_path)

# Target tokens
targets = ['learing', 'Grandma', 'Buttcoin']

print(f"--- Analyzing Tokens: {', '.join(targets)} ---")

for name in targets:
    print(f"\n[Token: {name}]")
    
    # Get Token ID
    cursor = conn.cursor()
    cursor.execute("SELECT id, ca, name FROM tokens WHERE name LIKE ?", (f"%{name}%",))
    token_rows = cursor.fetchall()
    
    if not token_rows:
        print("  ❌ Token not found in DB")
        continue
        
    for token_id, ca, full_name in token_rows:
        print(f"  ID: {token_id} | Name: {full_name} | CA: {ca}")
        
        # Get API History
        query = """
        SELECT 
            timestamp, 
            price_usd, 
            market_cap, 
            liquidity_usd,
            volume_m5,
            txns_m5_buys,
            txns_m5_sells
        FROM api_history 
        WHERE token_id = ?
        ORDER BY timestamp ASC
        """
        df = pd.read_sql_query(query, conn, params=(token_id,))
        
        if df.empty:
            print("  ⚠️ No API history data found")
            continue
            
        print(f"  📊 History Records: {len(df)}")
        print(df.head(5).to_string(index=False))
        if len(df) > 5:
            print("  ...")
            print(df.tail(5).to_string(index=False))
            
        # Analysis: Max/Min values
        max_mc = df['market_cap'].max()
        max_vol = df['volume_m5'].max()
        max_liq = df['liquidity_usd'].max()
        print(f"  📈 Peak MC: ${max_mc:,.0f} | Peak Vol(5m): ${max_vol:,.0f} | Peak Liq: ${max_liq:,.0f}")

conn.close()
