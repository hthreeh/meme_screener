"""
历史数据 API 路由
提供 api_history 表数据查询、信号事件、交易记录和CSV导出
"""

from typing import List, Optional
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pathlib import Path
import sys
import csv
import io

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.database import DatabaseManager
from config.settings import DB_PATH

router = APIRouter()
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

class TokenSummary(BaseModel):
    """代币摘要"""
    token_id: int
    token_ca: str
    token_name: Optional[str]
    token_symbol: Optional[str]
    data_count: int
    first_time: Optional[str]
    last_time: Optional[str]


class HistoryDataPoint(BaseModel):
    """历史数据点"""
    timestamp: str
    price_usd: Optional[float]
    market_cap: Optional[float]
    liquidity_usd: Optional[float]
    volume_m5: Optional[float]
    volume_h1: Optional[float]
    volume_h24: Optional[float]
    txns_m5_buys: Optional[int]
    txns_m5_sells: Optional[int]
    txns_h1_buys: Optional[int]
    txns_h1_sells: Optional[int]
    price_change_h1: Optional[float]
    price_change_h24: Optional[float]


class HistoryResponse(BaseModel):
    """历史数据响应"""
    token_id: int
    token_ca: str
    token_name: Optional[str]
    data: List[HistoryDataPoint]


class SignalEvent(BaseModel):
    """信号事件"""
    id: int
    signal_type: str
    trigger_time: str
    trigger_value: Optional[float]
    market_cap: Optional[float]
    price: Optional[float]


class TradeRecord(BaseModel):
    """交易记录"""
    id: int
    strategy_type: str
    action: str
    timestamp: str
    price: Optional[float]
    amount: Optional[float]
    pnl: Optional[float]


# ==================== 路由 ====================

@router.get("/tokens", response_model=List[TokenSummary])
async def get_tokens_with_history(
    search: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500)
):
    """获取有历史数据的代币列表"""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        query = """
            SELECT 
                token_id,
                token_address as token_ca,
                token_name,
                token_symbol,
                COUNT(*) as data_count,
                MIN(timestamp) as first_time,
                MAX(timestamp) as last_time
            FROM api_history
        """
        params = []
        
        if search:
            query += " WHERE token_name LIKE ? OR token_address LIKE ?"
            params.extend([f"%{search}%", f"%{search}%"])
        
        query += """
            GROUP BY token_id, token_address
            ORDER BY data_count DESC
            LIMIT ?
        """
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        return [
            TokenSummary(
                token_id=row['token_id'],
                token_ca=row['token_ca'],
                token_name=row['token_name'],
                token_symbol=row['token_symbol'],
                data_count=row['data_count'],
                first_time=utc_to_local(row['first_time']) if row['first_time'] else None,
                last_time=utc_to_local(row['last_time']) if row['last_time'] else None
            )
            for row in rows
        ]


@router.get("/{token_id}", response_model=HistoryResponse)
async def get_token_history(
    token_id: int,
    hours: int = Query(24, ge=1, le=168),
    fields: Optional[str] = None  # 逗号分隔的字段列表
):
    """获取代币历史数据"""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # 获取代币基本信息
        cursor.execute("""
            SELECT token_address, token_name
            FROM api_history
            WHERE token_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (token_id,))
        token_info = cursor.fetchone()
        
        if not token_info:
            raise HTTPException(status_code=404, detail="Token not found")
        
        # 获取历史数据
        cursor.execute("""
            SELECT 
                timestamp, price_usd, market_cap, liquidity_usd,
                volume_m5, volume_h1, volume_h24,
                txns_m5_buys, txns_m5_sells,
                txns_h1_buys, txns_h1_sells,
                price_change_h1, price_change_h24
            FROM api_history
            WHERE token_id = ? AND timestamp >= ?
            ORDER BY timestamp ASC
        """, (token_id, cutoff.isoformat()))
        rows = cursor.fetchall()
        
        data = []
        for row in rows:
            data.append(HistoryDataPoint(
                timestamp=utc_to_local(row['timestamp']),
                price_usd=row['price_usd'],
                market_cap=row['market_cap'],
                liquidity_usd=row['liquidity_usd'],
                volume_m5=row['volume_m5'],
                volume_h1=row['volume_h1'],
                volume_h24=row['volume_h24'],
                txns_m5_buys=row['txns_m5_buys'],
                txns_m5_sells=row['txns_m5_sells'],
                txns_h1_buys=row['txns_h1_buys'],
                txns_h1_sells=row['txns_h1_sells'],
                price_change_h1=row['price_change_h1'],
                price_change_h24=row['price_change_h24']
            ))
        
        return HistoryResponse(
            token_id=token_id,
            token_ca=token_info['token_address'],
            token_name=token_info['token_name'],
            data=data
        )


@router.get("/{token_id}/signals", response_model=List[SignalEvent])
async def get_token_signals(
    token_id: int,
    hours: int = Query(24, ge=1, le=168)
):
    """获取代币的信号事件"""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, signal_type, created_at, trigger_value, 
                   market_cap_at_trigger, price_at_trigger
            FROM signal_events
            WHERE token_id = ? AND created_at >= ?
            ORDER BY created_at ASC
        """, (token_id, cutoff.isoformat()))
        rows = cursor.fetchall()
        
        return [
            SignalEvent(
                id=row['id'],
                signal_type=row['signal_type'],
                trigger_time=utc_to_local(row['created_at']),
                trigger_value=row['trigger_value'],
                market_cap=row['market_cap_at_trigger'],
                price=row['price_at_trigger']
            )
            for row in rows
        ]


@router.get("/{token_id}/trades", response_model=List[TradeRecord])
async def get_token_trades(
    token_id: int,
    hours: int = Query(24, ge=1, le=168)
):
    """获取代币的交易记录"""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # 先获取代币的 CA
        cursor.execute("""
            SELECT token_address FROM api_history
            WHERE token_id = ?
            LIMIT 1
        """, (token_id,))
        token_row = cursor.fetchone()
        
        if not token_row:
            return []
        
        token_ca = token_row['token_address']
        
        # 查询交易记录
        cursor.execute("""
            SELECT id, strategy_type, action, timestamp, price, amount, pnl
            FROM strategy_trades
            WHERE token_ca = ? AND timestamp >= ?
            ORDER BY timestamp ASC
        """, (token_ca, cutoff.isoformat()))
        rows = cursor.fetchall()
        
        return [
            TradeRecord(
                id=row['id'],
                strategy_type=row['strategy_type'],
                action=row['action'],
                timestamp=utc_to_local(row['timestamp']),
                price=row['price'],
                amount=row['amount'],
                pnl=row['pnl']
            )
            for row in rows
        ]


@router.get("/{token_id}/export")
async def export_token_history(
    token_id: int,
    hours: int = Query(24, ge=1, le=168)
):
    """导出代币历史数据为CSV"""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # 获取代币信息
        cursor.execute("""
            SELECT token_address, token_name
            FROM api_history
            WHERE token_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (token_id,))
        token_info = cursor.fetchone()
        
        if not token_info:
            raise HTTPException(status_code=404, detail="Token not found")
        
        # 获取历史数据
        cursor.execute("""
            SELECT 
                timestamp, price_usd, market_cap, liquidity_usd,
                volume_m5, volume_h1, volume_h24,
                txns_m5_buys, txns_m5_sells,
                txns_h1_buys, txns_h1_sells,
                price_change_h1, price_change_h24
            FROM api_history
            WHERE token_id = ? AND timestamp >= ?
            ORDER BY timestamp ASC
        """, (token_id, cutoff.isoformat()))
        rows = cursor.fetchall()
        
        # 创建CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # 写入表头
        headers = [
            '时间', '价格(USD)', '市值', '流动性',
            '5分钟交易量', '1小时交易量', '24小时交易量',
            '5分钟买入笔数', '5分钟卖出笔数',
            '1小时买入笔数', '1小时卖出笔数',
            '1小时涨跌%', '24小时涨跌%'
        ]
        writer.writerow(headers)
        
        # 写入数据
        for row in rows:
            writer.writerow([
                utc_to_local(row['timestamp']),
                row['price_usd'],
                row['market_cap'],
                row['liquidity_usd'],
                row['volume_m5'],
                row['volume_h1'],
                row['volume_h24'],
                row['txns_m5_buys'],
                row['txns_m5_sells'],
                row['txns_h1_buys'],
                row['txns_h1_sells'],
                row['price_change_h1'],
                row['price_change_h24']
            ])
        
        output.seek(0)
        
        # 生成文件名
        token_name = token_info['token_name'] or 'unknown'
        filename = f"{token_name}_history_{hours}h.csv"
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
