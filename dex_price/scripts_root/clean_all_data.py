"""
清理项目数据脚本 - 让项目干净地重新运行
清理内容：
1. 所有日志文件
2. data目录下的所有 .json 和 .txt 文件
3. 数据库表（保留 tokens 表）
4. 重置账户余额为 100 SOL
"""

import sys
import os
import io
from pathlib import Path
from datetime import datetime

# 修复 Windows 控制台编码问题
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.database import DatabaseManager


def clean_all_data():
    """清理所有项目数据"""
    print("=" * 60)
    print("DEX 项目数据清理工具")
    print("=" * 60)
    
    project_dir = Path(__file__).parent.parent
    data_dir = project_dir / "data"
    logs_dir = data_dir / "logs"
    db_path = data_dir / "dex_monitor.db"
    
    # ========== 1. 清理日志文件 ==========
    print("\n📁 [1/3] 清理日志文件...")
    log_count = 0
    if logs_dir.exists():
        for log_file in logs_dir.glob("*.log*"):
            try:
                log_file.unlink()
                log_count += 1
            except Exception as e:
                print(f"  ⚠️ 无法删除 {log_file.name}: {e}")
    print(f"  ✅ 已删除 {log_count} 个日志文件")
    
    # ========== 2. 清理 data 目录下的 json 和 txt 文件 ==========
    print("\n📁 [2/3] 清理数据文件...")
    file_count = 0
    
    # 清理 json 文件
    for json_file in data_dir.glob("*.json"):
        try:
            json_file.unlink()
            file_count += 1
        except Exception as e:
            print(f"  ⚠️ 无法删除 {json_file.name}: {e}")
    
    # 清理 txt 文件
    for txt_file in data_dir.glob("*.txt"):
        try:
            txt_file.unlink()
            file_count += 1
        except Exception as e:
            print(f"  ⚠️ 无法删除 {txt_file.name}: {e}")
    
    print(f"  ✅ 已删除 {file_count} 个数据文件")
    
    # ========== 3. 清理数据库（保留 tokens 表） ==========
    print("\n📁 [3/3] 清理数据库表...")
    
    if not db_path.exists():
        print(f"  ❌ 数据库文件不存在: {db_path}")
        return
    
    db = DatabaseManager(db_path)
    
    # 需要清空的表（保留 tokens）
    tables_to_clear = [
        "simulated_trades",      # 模拟交易记录
        "strategy_trades",       # 多策略交易记录
        "strategy_states",       # 策略状态 (余额、持仓统计)
        "strategy_positions",    # 策略持仓
        "signal_events",         # 信号事件
        "signal_tracking",       # 信号跟踪
        "api_data_cache",        # API 缓存
        "price_snapshots",       # 价格快照
        "api_history",           # API 历史记录
    ]
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        for table in tables_to_clear:
            try:
                cursor.execute(f"DELETE FROM {table}")
                print(f"  ✅ 已清空 {table}")
            except Exception as e:
                print(f"  ⚠️ 跳过 {table}: {e}")
        
        # 重置账户状态
        try:
            cursor.execute("""
                UPDATE account_state SET
                    balance_sol = 100.0,
                    total_trades = 0,
                    winning_trades = 0,
                    losing_trades = 0,
                    total_pnl = 0.0,
                    last_updated = CURRENT_TIMESTAMP
            """)
            print(f"  ✅ 已重置 account_state (余额=100 SOL)")
        except Exception as e:
            print(f"  ⚠️ 重置账户失败: {e}")
        
        conn.commit()
    
    # ========== 完成 ==========
    print("\n" + "=" * 60)
    print("✅ 数据清理完成！")
    print(f"   清理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("   保留内容: tokens 表")
    print("   初始余额: 100 SOL")
    print("=" * 60)
    print("\n🚀 现在可以干净地重新运行项目了！")


if __name__ == "__main__":
    clean_all_data()
