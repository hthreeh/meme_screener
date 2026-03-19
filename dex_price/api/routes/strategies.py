"""
策略相关 API 路由
提供策略状态和持仓信息
"""

from typing import List, Optional
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Query
from pydantic import BaseModel
from pathlib import Path
import sys

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.database import DatabaseManager
from config.settings import DB_PATH

router = APIRouter()

# 初始化数据库
db = DatabaseManager(DB_PATH)

# 上海时区 (UTC+8)
SHANGHAI_TZ = timezone(timedelta(hours=8))

def utc_to_local(utc_str: str) -> str:
    """将 UTC 时间字符串转换为本地时间（上海 UTC+8）"""
    if not utc_str:
        return utc_str
    try:
        if 'T' in utc_str:
            dt = datetime.fromisoformat(utc_str.replace('Z', '+00:00'))
        else:
            dt = datetime.strptime(utc_str, '%Y-%m-%d %H:%M:%S')
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone(SHANGHAI_TZ)
        return local_dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return utc_str


# ==================== 数据模型 ====================

class StrategyState(BaseModel):
    """策略状态"""
    strategy_type: str
    balance_sol: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_pnl: float
    win_rate: float


class Position(BaseModel):
    """持仓信息"""
    id: int
    token_id: int  # 代币 ID，用于手动卖出
    strategy_type: str
    token_ca: str
    token_name: Optional[str]
    buy_market_cap: float
    buy_amount_sol: float
    buy_time: str
    remaining_ratio: float
    highest_multiplier: float
    take_profit_level: int
    # 新增：当前市值和持仓金额
    current_market_cap: Optional[float] = None
    current_amount_sol: Optional[float] = None
    current_multiplier: Optional[float] = None
    pnl_percent: Optional[float] = None  # 盈亏百分比


class StrategyDetail(BaseModel):
    """策略详情（含持仓）"""
    state: StrategyState
    positions: List[Position]


# ==================== 路由 ====================

@router.get("", response_model=List[StrategyState])
async def get_all_strategies():
    """获取所有策略状态"""
    strategies = []
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT strategy_type, balance_sol, total_trades, 
                   winning_trades, losing_trades, total_pnl
            FROM strategy_states
            ORDER BY strategy_type
        """)
        rows = cursor.fetchall()
        
        for row in rows:
            total = row['total_trades'] or 0
            wins = row['winning_trades'] or 0
            win_rate = (wins / total * 100) if total > 0 else 0.0
            
            strategies.append(StrategyState(
                strategy_type=row['strategy_type'],
                balance_sol=row['balance_sol'] or 0.0,
                total_trades=total,
                winning_trades=wins,
                losing_trades=row['losing_trades'] or 0,
                total_pnl=row['total_pnl'] or 0.0,
                win_rate=round(win_rate, 2)
            ))
    
    return strategies


@router.get("/{strategy_type}", response_model=StrategyDetail)
async def get_strategy_detail(strategy_type: str):
    """获取策略详情（含持仓）"""
    strategy_type = strategy_type.upper()
    
    # 获取策略状态
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT strategy_type, balance_sol, total_trades, 
                   winning_trades, losing_trades, total_pnl
            FROM strategy_states
            WHERE strategy_type = ?
        """, (strategy_type,))
        row = cursor.fetchone()
        
        if not row:
            # 返回默认状态
            state = StrategyState(
                strategy_type=strategy_type,
                balance_sol=0.0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                total_pnl=0.0,
                win_rate=0.0
            )
        else:
            total = row['total_trades'] or 0
            wins = row['winning_trades'] or 0
            win_rate = (wins / total * 100) if total > 0 else 0.0
            
            state = StrategyState(
                strategy_type=row['strategy_type'],
                balance_sol=row['balance_sol'] or 0.0,
                total_trades=total,
                winning_trades=wins,
                losing_trades=row['losing_trades'] or 0,
                total_pnl=row['total_pnl'] or 0.0,
                win_rate=round(win_rate, 2)
            )
        
        # 获取持仓
        cursor.execute("""
            SELECT id, token_id, strategy_type, token_ca, token_name,
                   buy_market_cap, buy_amount_sol, buy_time,
                   remaining_ratio, highest_multiplier, take_profit_level
            FROM strategy_positions
            WHERE strategy_type = ?
            ORDER BY buy_time DESC
        """, (strategy_type,))
        position_rows = cursor.fetchall()
        
        positions = []
        for pos in position_rows:
            positions.append(Position(
                id=pos['id'],
                token_id=pos['token_id'],
                strategy_type=pos['strategy_type'],
                token_ca=pos['token_ca'],
                token_name=pos['token_name'],
                buy_market_cap=pos['buy_market_cap'],
                buy_amount_sol=pos['buy_amount_sol'],
                buy_time=pos['buy_time'],
                remaining_ratio=pos['remaining_ratio'],
                highest_multiplier=pos['highest_multiplier'],
                take_profit_level=pos['take_profit_level']
            ))
    
    return StrategyDetail(state=state, positions=positions)


@router.get("/{strategy_type}/positions", response_model=List[Position])
async def get_strategy_positions(strategy_type: str):
    """获取策略的所有持仓"""
    strategy_type = strategy_type.upper()
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, token_id, strategy_type, token_ca, token_name,
                   buy_market_cap, buy_amount_sol, buy_time,
                   remaining_ratio, highest_multiplier, take_profit_level
            FROM strategy_positions
            WHERE strategy_type = ?
            ORDER BY buy_time DESC
        """, (strategy_type,))
        rows = cursor.fetchall()
        
        positions = []
        for pos in rows:
            token_ca = pos['token_ca']
            buy_market_cap = pos['buy_market_cap'] or 0
            buy_amount_sol = pos['buy_amount_sol'] or 0
            remaining_ratio = pos['remaining_ratio'] or 1.0
            
            # 获取当前市值（从api_data_cache获取最新数据）
            current_market_cap = None
            current_amount_sol = None
            current_multiplier = None
            pnl_percent = None
            
            cursor.execute("""
                SELECT market_cap FROM api_data_cache
                WHERE token_ca = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, (token_ca,))
            cache_row = cursor.fetchone()
            
            if cache_row and cache_row['market_cap'] and buy_market_cap > 0:
                current_market_cap = cache_row['market_cap']
                # 计算当前倍数
                current_multiplier = current_market_cap / buy_market_cap
                # 计算当前持仓金额 = 买入金额 * 当前倍数 * 剩余比例
                current_amount_sol = buy_amount_sol * current_multiplier * remaining_ratio
                # 计算盈亏百分比
                base_amount = buy_amount_sol * remaining_ratio
                if base_amount > 0:
                    pnl_percent = ((current_amount_sol - base_amount) / base_amount) * 100
            
            positions.append(Position(
                id=pos['id'],
                token_id=pos['token_id'],
                strategy_type=pos['strategy_type'],
                token_ca=token_ca,
                token_name=pos['token_name'],
                buy_market_cap=buy_market_cap,
                buy_amount_sol=buy_amount_sol,
                buy_time=pos['buy_time'],
                remaining_ratio=remaining_ratio,
                highest_multiplier=pos['highest_multiplier'],
                take_profit_level=pos['take_profit_level'],
                current_market_cap=current_market_cap,
                current_amount_sol=round(current_amount_sol, 4) if current_amount_sol else None,
                current_multiplier=round(current_multiplier, 4) if current_multiplier else None,
                pnl_percent=round(pnl_percent, 2) if pnl_percent else None
            ))
    
    return positions
