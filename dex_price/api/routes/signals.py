"""
信号相关 API 路由
提供信号事件列表和统计
"""

from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Query
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

class SignalEvent(BaseModel):
    """信号事件"""
    id: int
    token_id: int
    token_name: Optional[str]
    token_symbol: Optional[str]
    token_ca: Optional[str]
    signal_type: str
    trigger_value: Optional[float]
    market_cap_at_trigger: Optional[float]
    price_at_trigger: Optional[float]
    is_validated: bool
    validation_result: Optional[str]
    created_at: str


class SignalStats(BaseModel):
    """信号统计"""
    total_signals: int
    signals_24h: int
    signals_by_type: dict
    validated_count: int
    validation_rate: float


# ==================== 路由 ====================

@router.get("", response_model=List[SignalEvent])
async def get_signals(
    hours: int = Query(24, ge=1, le=168),
    signal_type: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500)
):
    """获取最近的信号事件"""
    cutoff = datetime.now() - timedelta(hours=hours)
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        query = """
            SELECT s.id, s.token_id, t.name as token_name, t.symbol as token_symbol,
                   t.ca as token_ca, s.signal_type, s.trigger_value,
                   s.market_cap_at_trigger, s.price_at_trigger,
                   s.is_validated, s.validation_result, s.created_at
            FROM signal_events s
            LEFT JOIN tokens t ON s.token_id = t.id
            WHERE s.created_at >= ?
        """
        params = [cutoff.isoformat()]
        
        if signal_type:
            query += " AND s.signal_type = ?"
            params.append(signal_type)
        
        query += " ORDER BY s.created_at DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        signals = []
        for row in rows:
            signals.append(SignalEvent(
                id=row['id'],
                token_id=row['token_id'],
                token_name=row['token_name'],
                token_symbol=row['token_symbol'],
                token_ca=row['token_ca'],
                signal_type=row['signal_type'],
                trigger_value=row['trigger_value'],
                market_cap_at_trigger=row['market_cap_at_trigger'],
                price_at_trigger=row['price_at_trigger'],
                is_validated=bool(row['is_validated']),
                validation_result=row['validation_result'],
                created_at=row['created_at']
            ))
    
    return signals


@router.get("/stats", response_model=SignalStats)
async def get_signal_stats():
    """获取信号统计"""
    cutoff_24h = datetime.now() - timedelta(hours=24)
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # 总信号数
        cursor.execute("SELECT COUNT(*) as count FROM signal_events")
        total = cursor.fetchone()['count']
        
        # 24小时信号数
        cursor.execute(
            "SELECT COUNT(*) as count FROM signal_events WHERE created_at >= ?",
            (cutoff_24h.isoformat(),)
        )
        signals_24h = cursor.fetchone()['count']
        
        # 按类型统计
        cursor.execute("""
            SELECT signal_type, COUNT(*) as count
            FROM signal_events
            GROUP BY signal_type
        """)
        by_type = {row['signal_type']: row['count'] for row in cursor.fetchall()}
        
        # 验证率
        cursor.execute("SELECT COUNT(*) as count FROM signal_events WHERE is_validated = 1")
        validated = cursor.fetchone()['count']
        validation_rate = (validated / total * 100) if total > 0 else 0.0
    
    return SignalStats(
        total_signals=total,
        signals_24h=signals_24h,
        signals_by_type=by_type,
        validated_count=validated,
        validation_rate=round(validation_rate, 2)
    )


@router.get("/types")
async def get_signal_types():
    """获取所有信号类型"""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT signal_type FROM signal_events ORDER BY signal_type")
        types = [row['signal_type'] for row in cursor.fetchall()]
    
    return {"types": types}
