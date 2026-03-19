"""
看板汇总 API 路由
提供综合看板数据
"""

from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter
from pydantic import BaseModel
from pathlib import Path
import sys

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.database import DatabaseManager
from config.settings import DB_PATH

router = APIRouter()
db = DatabaseManager(DB_PATH)


# ==================== 数据模型 ====================

class StrategyOverview(BaseModel):
    """策略概览"""
    strategy_type: str
    balance: float
    pnl: float
    position_count: int


class RecentTrade(BaseModel):
    """最近交易"""
    strategy_type: str
    token_name: str
    action: str
    pnl: Optional[float]
    timestamp: str


class DashboardData(BaseModel):
    """看板汇总数据"""
    # 总体统计
    total_balance: float
    total_pnl: float
    total_positions: int
    active_strategies: int
    
    # 24小时统计
    trades_24h: int
    signals_24h: int
    pnl_24h: float
    
    # 策略概览
    strategies: List[StrategyOverview]
    
    # 最近交易
    recent_trades: List[RecentTrade]
    
    # 系统状态
    last_update: str


# ==================== 路由 ====================

@router.get("", response_model=DashboardData)
async def get_dashboard():
    """获取综合看板数据"""
    cutoff_24h = datetime.now() - timedelta(hours=24)
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # ===== 策略概览 =====
        cursor.execute("""
            SELECT strategy_type, balance_sol, total_pnl
            FROM strategy_states
            ORDER BY strategy_type
        """)
        strategy_rows = cursor.fetchall()
        
        strategies = []
        total_balance = 0.0
        total_pnl = 0.0
        
        for row in strategy_rows:
            balance = row['balance_sol'] or 0.0
            pnl = row['total_pnl'] or 0.0
            
            # 获取持仓数
            cursor.execute("""
                SELECT COUNT(*) as count FROM strategy_positions
                WHERE strategy_type = ?
            """, (row['strategy_type'],))
            pos_count = cursor.fetchone()['count']
            
            strategies.append(StrategyOverview(
                strategy_type=row['strategy_type'],
                balance=round(balance, 4),
                pnl=round(pnl, 4),
                position_count=pos_count
            ))
            
            total_balance += balance
            total_pnl += pnl
        
        active_strategies = len([s for s in strategies if s.position_count > 0])
        
        # ===== 总持仓数 =====
        cursor.execute("SELECT COUNT(*) as count FROM strategy_positions")
        total_positions = cursor.fetchone()['count']
        
        # ===== 24小时统计 =====
        # 检查 strategy_trades 表是否存在
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='strategy_trades'
        """)
        has_trades_table = cursor.fetchone() is not None
        
        trades_24h = 0
        pnl_24h = 0.0
        recent_trades = []
        
        if has_trades_table:
            cursor.execute(
                "SELECT COUNT(*) as count FROM strategy_trades WHERE timestamp >= ?",
                (cutoff_24h.isoformat(),)
            )
            trades_24h = cursor.fetchone()['count']
            
            cursor.execute("""
                SELECT SUM(pnl) as pnl FROM strategy_trades 
                WHERE timestamp >= ? AND action = 'SELL' AND pnl IS NOT NULL
            """, (cutoff_24h.isoformat(),))
            pnl_row = cursor.fetchone()
            pnl_24h = pnl_row['pnl'] or 0.0
            
            # 最近5笔交易
            cursor.execute("""
                SELECT strategy_type, token_name, action, pnl, timestamp
                FROM strategy_trades
                ORDER BY timestamp DESC
                LIMIT 5
            """)
            for row in cursor.fetchall():
                recent_trades.append(RecentTrade(
                    strategy_type=row['strategy_type'],
                    token_name=row['token_name'],
                    action=row['action'],
                    pnl=row['pnl'],
                    timestamp=row['timestamp']
                ))
        
        # 24小时信号数
        cursor.execute(
            "SELECT COUNT(*) as count FROM signal_events WHERE created_at >= ?",
            (cutoff_24h.isoformat(),)
        )
        signals_24h = cursor.fetchone()['count']
    
    return DashboardData(
        total_balance=round(total_balance, 4),
        total_pnl=round(total_pnl, 4),
        total_positions=total_positions,
        active_strategies=active_strategies,
        trades_24h=trades_24h,
        signals_24h=signals_24h,
        pnl_24h=round(pnl_24h, 4),
        strategies=strategies,
        recent_trades=recent_trades,
        last_update=datetime.now().isoformat()
    )


@router.get("/summary")
async def get_summary():
    """获取简要汇总（用于状态栏）"""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # 总持仓
        cursor.execute("SELECT COUNT(*) as count FROM strategy_positions")
        positions = cursor.fetchone()['count']
        
        # 活跃策略
        cursor.execute("""
            SELECT COUNT(DISTINCT strategy_type) as count 
            FROM strategy_positions
        """)
        active = cursor.fetchone()['count']
        
        # 总余额
        cursor.execute("SELECT SUM(balance_sol) as total FROM strategy_states")
        balance_row = cursor.fetchone()
        total_balance = balance_row['total'] or 0.0
    
    return {
        "positions": positions,
        "active_strategies": active,
        "total_balance": round(total_balance, 4)
    }
