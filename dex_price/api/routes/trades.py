"""
交易相关 API 路由
提供交易历史和统计
"""

from typing import List, Optional
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from pathlib import Path
import sys
import time
import json

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
        # 解析 UTC 时间
        if 'T' in utc_str:
            dt = datetime.fromisoformat(utc_str.replace('Z', '+00:00'))
        else:
            dt = datetime.strptime(utc_str, '%Y-%m-%d %H:%M:%S')
        
        # 如果没有时区信息，假定为 UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        
        # 转换到上海时区
        local_dt = dt.astimezone(SHANGHAI_TZ)
        return local_dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return utc_str  # 解析失败时返回原值


# ==================== 数据模型 ====================

class Trade(BaseModel):
    """交易记录"""
    id: int
    strategy_type: Optional[str]
    token_ca: str
    token_name: str
    action: str
    price: Optional[float]
    amount: Optional[float]
    pnl: Optional[float]
    timestamp: str


class TradeStats(BaseModel):
    """交易统计"""
    total_trades: int
    trades_24h: int
    buy_count: int
    sell_count: int
    total_pnl: float
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_pnl: float


# ==================== 路由 ====================

@router.get("", response_model=List[Trade])
async def get_trades(
    hours: int = Query(72, ge=1, le=168),
    strategy_type: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = Query(100, ge=1, le=2000)
):
    """获取交易历史"""
    cutoff = datetime.now() - timedelta(hours=hours)
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # 从 strategy_trades 表获取
        query = """
            SELECT id, strategy_type, token_ca, token_name, 
                   action, price, amount, pnl, timestamp
            FROM strategy_trades
            WHERE timestamp >= ?
        """
        params = [cutoff.isoformat()]
        
        if strategy_type:
            query += " AND strategy_type = ?"
            params.append(strategy_type)
        
        if action:
            query += " AND action = ?"
            params.append(action)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        trades = []
        for row in rows:
            trades.append(Trade(
                id=row['id'],
                strategy_type=row['strategy_type'],
                token_ca=row['token_ca'],
                token_name=row['token_name'],
                action=row['action'],
                price=row['price'],
                amount=row['amount'],
                pnl=row['pnl'],
                timestamp=utc_to_local(row['timestamp'])
            ))
    
    return trades


@router.get("/stats", response_model=TradeStats)
async def get_trade_stats():
    """获取交易统计"""
    cutoff_24h = datetime.now() - timedelta(hours=24)
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # 检查表是否存在
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='strategy_trades'
        """)
        if not cursor.fetchone():
            return TradeStats(
                total_trades=0,
                trades_24h=0,
                buy_count=0,
                sell_count=0,
                total_pnl=0.0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                avg_pnl=0.0
            )
        
        # 总交易数
        cursor.execute("SELECT COUNT(*) as count FROM strategy_trades")
        total = cursor.fetchone()['count']
        
        # 24小时交易数
        cursor.execute(
            "SELECT COUNT(*) as count FROM strategy_trades WHERE timestamp >= ?",
            (cutoff_24h.isoformat(),)
        )
        trades_24h = cursor.fetchone()['count']
        
        # 买卖统计
        cursor.execute("""
            SELECT action, COUNT(*) as count
            FROM strategy_trades
            GROUP BY action
        """)
        action_counts = {row['action']: row['count'] for row in cursor.fetchall()}
        buy_count = action_counts.get('BUY', 0)
        sell_count = action_counts.get('SELL', 0)
        
        # 盈亏统计
        cursor.execute("""
            SELECT SUM(pnl) as total_pnl,
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END) as losses
            FROM strategy_trades
            WHERE action = 'SELL' AND pnl IS NOT NULL
        """)
        pnl_row = cursor.fetchone()
        
        total_pnl = pnl_row['total_pnl'] or 0.0
        wins = pnl_row['wins'] or 0
        losses = pnl_row['losses'] or 0
        
        total_sells = wins + losses
        win_rate = (wins / total_sells * 100) if total_sells > 0 else 0.0
        avg_pnl = (total_pnl / total_sells) if total_sells > 0 else 0.0
    
    return TradeStats(
        total_trades=total,
        trades_24h=trades_24h,
        buy_count=buy_count,
        sell_count=sell_count,
        total_pnl=round(total_pnl, 4),
        winning_trades=wins,
        losing_trades=losses,
        win_rate=round(win_rate, 2),
        avg_pnl=round(avg_pnl, 4)
    )


@router.get("/by-strategy")
async def get_trades_by_strategy():
    """按策略分组的交易统计"""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # 检查表是否存在
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='strategy_trades'
        """)
        if not cursor.fetchone():
            return {"strategies": []}
        
        cursor.execute("""
            SELECT strategy_type,
                   COUNT(*) as total,
                   SUM(CASE WHEN action = 'BUY' THEN 1 ELSE 0 END) as buys,
                   SUM(CASE WHEN action = 'SELL' THEN 1 ELSE 0 END) as sells,
                   SUM(CASE WHEN action = 'SELL' AND pnl > 0 THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN action = 'SELL' THEN pnl ELSE 0 END) as total_pnl
            FROM strategy_trades
            GROUP BY strategy_type
            ORDER BY strategy_type
        """)
        rows = cursor.fetchall()
        
        strategies = []
        for row in rows:
            sells = row['sells'] or 0
            wins = row['wins'] or 0
            win_rate = (wins / sells * 100) if sells > 0 else 0.0
            
            strategies.append({
                "strategy_type": row['strategy_type'],
                "total_trades": row['total'],
                "buy_count": row['buys'],
                "sell_count": sells,
                "winning_trades": wins,
                "total_pnl": round(row['total_pnl'] or 0, 4),
                "win_rate": round(win_rate, 2)
            })
    
    return {"strategies": strategies}


# ==================== 手动交易 ====================

class ManualBuyRequest(BaseModel):
    """手动买入请求"""
    ca: str  # 代币合约地址
    amount: Optional[float] = 0.2  # 买入金额 (SOL)


class ManualBuyResponse(BaseModel):
    """手动买入响应"""
    success: bool
    order_id: Optional[int] = None
    message: str
    # 详细结果 (可选)
    token_name: Optional[str] = None
    buy_price: Optional[float] = None
    buy_amount: Optional[float] = None
    balance_after: Optional[float] = None


@router.post("/manual", response_model=ManualBuyResponse)
async def create_manual_order(req: ManualBuyRequest):
    """
    提交手动买入订单
    
    订单会被添加到队列中，由后台 Worker 处理。
    API 会等待最多 10秒 获取处理结果。
    """
    # 验证 CA 格式 (SOL 地址通常为 32-44 字符)
    if not req.ca or len(req.ca) < 30 or len(req.ca) > 50:
        raise HTTPException(status_code=400, detail="无效的合约地址")
    
    # 验证金额
    if req.amount <= 0 or req.amount > 10:
        raise HTTPException(status_code=400, detail="买入金额必须在 0.01 - 10 SOL 之间")
    
    try:
        # 写入队列
        order_id = db.add_manual_order(req.ca, req.amount)
        
        # 等待处理结果 (最多 10秒)
        for _ in range(20):  # 20 * 0.5s = 10s
            time.sleep(0.5)
            order = db.get_manual_order(order_id)
            if not order:
                continue
            
            status = order['status']
            if status == 'DONE':
                # 解析结果
                result = {}
                try:
                    if order['result_info']:
                        result = json.loads(order['result_info'])
                except:
                    pass
                
                return ManualBuyResponse(
                    success=True,
                    order_id=order_id,
                    message="交易成功！",
                    token_name=result.get('token_name'),
                    buy_price=result.get('buy_price'),
                    buy_amount=result.get('buy_amount'),
                    balance_after=result.get('balance_after')
                )
            elif status == 'FAILED':
                return ManualBuyResponse(
                    success=False,
                    order_id=order_id,
                    message=f"交易失败: {order.get('error_msg')}"
                )
        
        # 超时
        return ManualBuyResponse(
            success=True,
            order_id=order_id,
            message=f"订单已提交 (ID: {order_id})，正在后台处理中 (请稍后查看交易历史)"
        )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建订单失败: {str(e)}")


# ==================== 手动卖出 ====================

class ManualSellRequest(BaseModel):
    """手动卖出请求"""
    strategy_type: str  # 策略类型
    token_id: int       # 代币 ID


class ManualSellResponse(BaseModel):
    """手动卖出响应"""
    success: bool
    order_id: Optional[int] = None
    message: str
    # 详细结果
    token_name: Optional[str] = None
    sell_price: Optional[float] = None
    sell_amount: Optional[float] = None
    pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    balance_after: Optional[float] = None


@router.post("/manual-sell", response_model=ManualSellResponse)
async def create_manual_sell_order(req: ManualSellRequest):
    """
    提交手动卖出订单
    
    订单会被添加到队列中，由后台 Worker 处理。
    API 会等待最多 10秒 获取处理结果。
    """
    # 验证策略类型 (允许 'M' 作为手动交易策略标识)
    valid_strategies = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'ALPHA', 'MANUAL', 'M']
    if req.strategy_type.upper() not in valid_strategies:
        raise HTTPException(status_code=400, detail=f"无效的策略类型: {req.strategy_type}")
    
    # 验证 token_id
    if req.token_id <= 0:
        raise HTTPException(status_code=400, detail="无效的代币 ID")
    
    try:
        # 写入队列
        order_id = db.add_manual_sell_order(req.strategy_type.upper(), req.token_id)
        
        # 等待处理结果 (最多 10秒)
        for _ in range(20):  # 20 * 0.5s = 10s
            time.sleep(0.5)
            order = db.get_manual_sell_order(order_id)
            if not order:
                continue
            
            status = order['status']
            if status == 'DONE':
                # 解析结果
                result = {}
                try:
                    if order['result_info']:
                        result = json.loads(order['result_info'])
                except:
                    pass
                
                return ManualSellResponse(
                    success=True,
                    order_id=order_id,
                    message="卖出成功！",
                    token_name=result.get('token_name'),
                    sell_price=result.get('sell_price'),
                    sell_amount=result.get('sell_amount'),
                    pnl=result.get('pnl'),
                    pnl_percent=result.get('pnl_percent'),
                    balance_after=result.get('balance_after')
                )
            elif status == 'FAILED':
                return ManualSellResponse(
                    success=False,
                    order_id=order_id,
                    message=f"卖出失败: {order.get('error_msg')}"
                )
        
        # 超时
        return ManualSellResponse(
            success=True,
            order_id=order_id,
            message=f"订单已提交 (ID: {order_id})，正在后台处理中 (请稍后查看交易历史)"
        )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建卖出订单失败: {str(e)}")

