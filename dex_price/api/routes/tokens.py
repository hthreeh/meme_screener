"""
代币相关 API 路由
提供代币列表和历史数据
"""

from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Query, HTTPException
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

class Token(BaseModel):
    """代币基础信息"""
    id: int
    ca: Optional[str]
    href: str
    name: Optional[str]
    symbol: Optional[str]
    first_seen: str
    last_updated: str


class TokenHistoryPoint(BaseModel):
    """代币历史数据点"""
    timestamp: str
    price_usd: Optional[float]
    market_cap: Optional[float]
    liquidity_usd: Optional[float]
    volume_h1: Optional[float]
    txns_h1_buys: Optional[int]
    txns_h1_sells: Optional[int]


class TokenLatest(BaseModel):
    """代币最新数据"""
    ca: str
    name: Optional[str]
    symbol: Optional[str]
    price_usd: Optional[float]
    market_cap: Optional[float]
    liquidity_usd: Optional[float]
    price_change_h1: Optional[float]
    price_change_h24: Optional[float]
    volume_h24: Optional[float]
    timestamp: str


# ==================== 路由 ====================

@router.get("", response_model=List[Token])
async def get_all_tokens(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """获取所有追踪的代币列表"""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, ca, href, name, symbol, first_seen, last_updated
            FROM tokens
            ORDER BY last_updated DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
        rows = cursor.fetchall()
        
        tokens = []
        for row in rows:
            tokens.append(Token(
                id=row['id'],
                ca=row['ca'],
                href=row['href'],
                name=row['name'],
                symbol=row['symbol'],
                first_seen=row['first_seen'] or '',
                last_updated=row['last_updated'] or ''
            ))
    
    return tokens


@router.get("/{ca}/history", response_model=List[TokenHistoryPoint])
async def get_token_history(
    ca: str,
    hours: int = Query(24, ge=1, le=168)
):
    """获取代币历史数据（用于市值曲线）"""
    # 计算时间范围
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours)
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # 先从 api_history 表获取
        cursor.execute("""
            SELECT timestamp, price_usd, market_cap, liquidity_usd,
                   volume_h1, txns_h1_buys, txns_h1_sells
            FROM api_history
            WHERE token_address = ? AND timestamp >= ?
            ORDER BY timestamp ASC
        """, (ca, start_time.isoformat()))
        rows = cursor.fetchall()
        
        if not rows:
            # 尝试从 api_data_cache 获取
            cursor.execute("""
                SELECT timestamp, price_usd, market_cap, liquidity_usd,
                       volume_h1, txns_h1_buys, txns_h1_sells
                FROM api_data_cache
                WHERE token_ca = ? AND timestamp >= ?
                ORDER BY timestamp ASC
            """, (ca, start_time.isoformat()))
            rows = cursor.fetchall()
        
        history = []
        for row in rows:
            history.append(TokenHistoryPoint(
                timestamp=row['timestamp'],
                price_usd=row['price_usd'],
                market_cap=row['market_cap'],
                liquidity_usd=row['liquidity_usd'],
                volume_h1=row['volume_h1'],
                txns_h1_buys=row['txns_h1_buys'],
                txns_h1_sells=row['txns_h1_sells']
            ))
    
    return history


@router.get("/{ca}/latest", response_model=TokenLatest)
async def get_token_latest(ca: str):
    """获取代币最新数据"""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # 获取代币基础信息
        cursor.execute("SELECT name, symbol FROM tokens WHERE ca = ?", (ca,))
        token_row = cursor.fetchone()
        
        # 获取最新缓存数据
        cursor.execute("""
            SELECT price_usd, market_cap, liquidity_usd,
                   price_change_h1, price_change_h24, volume_h24, timestamp
            FROM api_data_cache
            WHERE token_ca = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (ca,))
        cache_row = cursor.fetchone()
        
        if not cache_row:
            raise HTTPException(status_code=404, detail=f"Token {ca} not found")
        
        return TokenLatest(
            ca=ca,
            name=token_row['name'] if token_row else None,
            symbol=token_row['symbol'] if token_row else None,
            price_usd=cache_row['price_usd'],
            market_cap=cache_row['market_cap'],
            liquidity_usd=cache_row['liquidity_usd'],
            price_change_h1=cache_row['price_change_h1'],
            price_change_h24=cache_row['price_change_h24'],
            volume_h24=cache_row['volume_h24'],
            timestamp=cache_row['timestamp']
        )


@router.get("/positions/all", response_model=List[Token])
async def get_position_tokens():
    """获取所有持仓中的代币"""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT t.id, t.ca, t.href, t.name, t.symbol, 
                   t.first_seen, t.last_updated
            FROM tokens t
            JOIN strategy_positions sp ON t.ca = sp.token_ca
            ORDER BY t.last_updated DESC
        """)
        rows = cursor.fetchall()
        
        tokens = []
        for row in rows:
            tokens.append(Token(
                id=row['id'],
                ca=row['ca'],
                href=row['href'],
                name=row['name'],
                symbol=row['symbol'],
                first_seen=row['first_seen'] or '',
                last_updated=row['last_updated'] or ''
            ))
    
    return tokens
