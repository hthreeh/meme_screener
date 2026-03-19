"""
数据库表检查和初始化脚本
运行此脚本可以检查并创建缺失的策略相关表
"""
import sqlite3
import os

DB_PATH = "data/dex_monitor.db"

def check_and_create_tables():
    if not os.path.exists(DB_PATH):
        print(f"[INFO] Database not found: {DB_PATH}, creating new...")
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check existing tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = [r[0] for r in cursor.fetchall()]
    print(f"Existing tables: {existing_tables}")
    
    # Check strategy_states
    if 'strategy_states' not in existing_tables:
        print("[CREATING] strategy_states table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_type TEXT UNIQUE NOT NULL,
                balance_sol REAL NOT NULL,
                total_trades INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,
                total_pnl REAL DEFAULT 0.0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("[OK] strategy_states created!")
    else:
        print("[OK] strategy_states exists")
    
    # Check strategy_positions
    if 'strategy_positions' not in existing_tables:
        print("[CREATING] strategy_positions table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_type TEXT NOT NULL,
                token_id INTEGER NOT NULL,
                token_ca TEXT NOT NULL,
                token_name TEXT,
                buy_market_cap REAL NOT NULL,
                buy_amount_sol REAL NOT NULL,
                buy_time TIMESTAMP NOT NULL,
                remaining_ratio REAL DEFAULT 1.0,
                highest_multiplier REAL DEFAULT 1.0,
                take_profit_level INTEGER DEFAULT 0,
                poll_count INTEGER DEFAULT 0,
                loss_check_count INTEGER DEFAULT 0,
                trailing_stop_multiplier REAL DEFAULT 0.7,
                FOREIGN KEY (token_id) REFERENCES tokens(id),
                UNIQUE(strategy_type, token_id)
            )
        """)
        print("[OK] strategy_positions created!")
    else:
        print("[OK] strategy_positions exists")
        # Check if new columns exist
        cursor.execute("PRAGMA table_info(strategy_positions)")
        columns = [r[1] for r in cursor.fetchall()]
        if 'loss_check_count' not in columns:
            print("[ADDING] loss_check_count column...")
            cursor.execute("ALTER TABLE strategy_positions ADD COLUMN loss_check_count INTEGER DEFAULT 0")
        if 'trailing_stop_multiplier' not in columns:
            print("[ADDING] trailing_stop_multiplier column...")
            cursor.execute("ALTER TABLE strategy_positions ADD COLUMN trailing_stop_multiplier REAL DEFAULT 0.7")
    
    conn.commit()
    conn.close()
    print("\n[DONE] Database check complete!")

if __name__ == "__main__":
    check_and_create_tables()
