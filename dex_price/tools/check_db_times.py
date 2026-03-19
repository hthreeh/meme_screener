import sqlite3
import os
from datetime import datetime

DB_PATH = "data/dex_monitor.db"

def check_tables():
    if not os.path.exists(DB_PATH):
        print(f"[ERROR] Database not found: {DB_PATH}")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]
    print(f"Tables found: {tables}")
    
    for table in tables:
        print(f"\nChecking table: {table}")
        try:
            # Get column info to find time-related columns
            cursor.execute(f"PRAGMA table_info({table})")
            columns = cursor.fetchall()
            col_names = [c[1] for c in columns]
            
            time_cols = [c for c in col_names if 'time' in c.lower() or 'date' in c.lower() or 'created' in c.lower() or 'updated' in c.lower()]
            
            count_query = f"SELECT COUNT(*) FROM {table}"
            cursor.execute(count_query)
            count = cursor.fetchone()[0]
            print(f"  Total records: {count}")

            if time_cols:
                print(f"  Time columns: {time_cols}")
                for time_col in time_cols:
                    query = f"SELECT MIN({time_col}), MAX({time_col}) FROM {table}"
                    cursor.execute(query)
                    min_time, max_time = cursor.fetchone()
                    print(f"    Column '{time_col}': Min={min_time}, Max={max_time}")
            else:
                print("  No obvious time columns found.")
                
        except Exception as e:
            print(f"  Error checking table {table}: {e}")

    conn.close()

if __name__ == "__main__":
    check_tables()
