"""
重置模拟交易系统脚本
清空所有持仓、会话，重置账户余额，让系统重新开始
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


def reset_trading_system():
    """重置整个交易系统"""
    print("=" * 60)
    print("DEX 模拟交易系统重置工具")
    print("=" * 60)
    
    # 初始化数据库
    project_dir = Path(__file__).parent
    db_path = project_dir / "data" / "dex_monitor.db"
    
    if not db_path.exists():
        print(f"❌ 数据库文件不存在: {db_path}")
        return
    
    db = DatabaseManager(db_path)
    
    print(f"\n数据库路径: {db_path}")
    
    # 1. 获取当前统计
    print("\n📊 当前数据统计:")
    stats = db.get_database_stats()
    for table, count in stats.items():
        print(f"  - {table}: {count} 条记录")
    
    # 2. 确认重置
    print("\n⚠️ 将执行以下操作:")
    print("  1. 清空所有模拟交易记录 (simulated_trades)")
    print("  2. 重置账户状态到初始余额 (account_state)")
    print("  3. 清空多策略交易记录 (strategy_trades)")
    print("  4. 清空信号事件记录 (signal_events) [可选]")
    print("  5. 清空 API 缓存 (api_data_cache)")
    
    confirm = input("\n确认重置？(输入 'yes' 确认): ").strip().lower()
    if confirm != 'yes':
        print("❌ 操作已取消")
        return
    
    # 3. 执行重置
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # 清空交易记录
        cursor.execute("DELETE FROM simulated_trades")
        print(f"✅ 已清空 simulated_trades")
        
        # 重置账户状态
        cursor.execute("""
            UPDATE account_state SET
                balance_sol = 100.0,
                total_trades = 0,
                winning_trades = 0,
                losing_trades = 0,
                total_pnl = 0.0,
                last_updated = CURRENT_TIMESTAMP
        """)
        print(f"✅ 已重置 account_state (余额=100 SOL)")
        
        # 清空多策略交易记录（如果存在）
        try:
            cursor.execute("DELETE FROM strategy_trades")
            print(f"✅ 已清空 strategy_trades")
        except Exception:
            pass  # 表可能不存在
        
        # 清空 API 缓存
        cursor.execute("DELETE FROM api_data_cache")
        print(f"✅ 已清空 api_data_cache")
        
        # 询问是否清空信号记录
        clear_signals = input("\n是否清空信号事件记录？(y/n): ").strip().lower()
        if clear_signals == 'y':
            cursor.execute("DELETE FROM signal_events")
            cursor.execute("DELETE FROM signal_tracking")
            print(f"✅ 已清空 signal_events 和 signal_tracking")
        
        conn.commit()
    
    # 4. 清空会话相关的内存状态（重启程序时自动清空）
    print("\n📝 内存会话将在下次启动时自动清空")
    
    # 5. 显示最终状态
    print("\n📊 重置后状态:")
    stats = db.get_database_stats()
    for table, count in stats.items():
        print(f"  - {table}: {count} 条记录")
    
    print("\n✅ 系统重置完成！可以重新开始模拟交易。")
    print(f"   重置时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    reset_trading_system()
