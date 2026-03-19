"""
DEX 价格监控 - 交易模拟器
模拟交易执行和盈亏计算
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from core.database import DatabaseManager
from core.api_client import DexScreenerAPI
from models.currency import AccountState


_logger = logging.getLogger(__name__)


@dataclass
class TradeResult:
    """交易结果"""
    success: bool
    trade_id: int
    action: str
    amount_sol: float
    price: float
    token_amount: float
    fee_sol: float
    balance_after: float
    message: str


class TradingSimulator:
    """
    交易模拟器
    
    模拟买入和卖出操作，计算盈亏
    """
    
    # 交易配置
    INITIAL_BALANCE = 100.0     # 初始余额 (SOL)
    TRADE_AMOUNT = 0.1          # 每次交易金额 (SOL)
    FEE_PERCENT = 3.0           # 手续费 (%)
    
    # 上涨成功定义
    SUCCESS_THRESHOLDS = {
        "below_1m": 100.0,      # 市值 < 1M, 涨幅 100%
        "above_1m": 50.0,       # 市值 >= 1M, 涨幅 50%
    }
    
    # 持仓管理
    MAX_HOLD_TIME_HOURS = 72    # 最大持仓时间 (3天)
    STOP_LOSS_PERCENT = -30.0   # 止损线 (%)
    TAKE_PROFIT_PERCENT = 50.0  # 止盈线 (%)
    
    def __init__(self, db: DatabaseManager, api: DexScreenerAPI = None):
        """
        初始化交易模拟器
        
        参数:
            db: 数据库管理器
            api: API 客户端（可选）
        """
        self.db = db
        self.api = api or DexScreenerAPI()
        self._logger = logging.getLogger(__name__)
        self._holdings: Dict[int, Dict] = {}  # token_id -> holding info
    
    def get_account_state(self) -> AccountState:
        """获取模拟账户状态"""
        state_dict = self.db.get_account_state()
        return AccountState(
            balance_sol=state_dict.get('balance_sol', self.INITIAL_BALANCE),
            total_trades=state_dict.get('total_trades', 0),
            winning_trades=state_dict.get('winning_trades', 0),
            losing_trades=state_dict.get('losing_trades', 0),
            total_pnl=state_dict.get('total_pnl', 0.0),
        )
    
    def buy(self, token_id: int, signal_event_id: int,
            price: float, market_cap: float = 0,
            notes: str = "") -> TradeResult:
        """
        执行模拟买入
        
        参数:
            token_id: 代币 ID
            signal_event_id: 关联的信号事件 ID
            price: 当前价格
            market_cap: 当前市值（用于计算成功阈值）
            notes: 备注
            
        返回:
            交易结果
        """
        # 检查余额
        account = self.get_account_state()
        if account.balance_sol < self.TRADE_AMOUNT:
            return TradeResult(
                success=False,
                trade_id=0,
                action="BUY",
                amount_sol=0,
                price=price,
                token_amount=0,
                fee_sol=0,
                balance_after=account.balance_sol,
                message=f"余额不足: {account.balance_sol:.4f} SOL"
            )
        
        # 计算交易
        amount_sol = self.TRADE_AMOUNT
        fee_sol = amount_sol * (self.FEE_PERCENT / 100)
        effective_amount = amount_sol - fee_sol
        token_amount = effective_amount / price if price > 0 else 0
        
        # 新余额
        new_balance = account.balance_sol - amount_sol
        
        # 记录交易
        trade_id = self.db.record_trade(
            token_id=token_id,
            signal_event_id=signal_event_id,
            action="BUY",
            amount_sol=amount_sol,
            price=price,
            token_amount=token_amount,
            fee_sol=fee_sol,
            pnl_sol=None,  # 买入时没有盈亏
            pnl_percent=None,
            balance_after=new_balance,
            notes=notes
        )
        
        # 更新账户（买入不影响盈亏统计，只扣余额）
        # 这里需要直接更新余额
        self._update_balance(new_balance)
        
        # 记录持仓
        self._holdings[token_id] = {
            "trade_id": trade_id,
            "signal_event_id": signal_event_id,
            "buy_price": price,
            "token_amount": token_amount,
            "amount_sol": amount_sol,
            "fee_sol": fee_sol,
            "buy_time": datetime.now(),
            "market_cap": market_cap,
        }
        
        self._logger.info(
            f"模拟买入: 代币#{token_id}, 价格=${price:.8f}, "
            f"数量={token_amount:.2f}, 费用={fee_sol:.4f} SOL"
        )
        
        return TradeResult(
            success=True,
            trade_id=trade_id,
            action="BUY",
            amount_sol=amount_sol,
            price=price,
            token_amount=token_amount,
            fee_sol=fee_sol,
            balance_after=new_balance,
            message=f"买入成功，获得 {token_amount:.2f} 代币"
        )
    
    def sell(self, token_id: int, current_price: float,
             reason: str = "手动卖出") -> TradeResult:
        """
        执行模拟卖出
        
        参数:
            token_id: 代币 ID
            current_price: 当前价格
            reason: 卖出原因
            
        返回:
            交易结果
        """
        # 检查是否持有
        if token_id not in self._holdings:
            return TradeResult(
                success=False,
                trade_id=0,
                action="SELL",
                amount_sol=0,
                price=current_price,
                token_amount=0,
                fee_sol=0,
                balance_after=self.get_account_state().balance_sol,
                message="未持有该代币"
            )
        
        holding = self._holdings[token_id]
        token_amount = holding["token_amount"]
        buy_price = holding["buy_price"]
        
        # 计算卖出收益
        gross_value = token_amount * current_price
        fee_sol = gross_value * (self.FEE_PERCENT / 100)
        net_value = gross_value - fee_sol
        
        # 计算盈亏
        cost = holding["amount_sol"]
        pnl_sol = net_value - cost
        pnl_percent = (pnl_sol / cost * 100) if cost > 0 else 0
        
        is_win = pnl_sol > 0
        
        # 更新余额
        account = self.get_account_state()
        new_balance = account.balance_sol + net_value
        
        # 记录交易
        trade_id = self.db.record_trade(
            token_id=token_id,
            signal_event_id=holding["signal_event_id"],
            action="SELL",
            amount_sol=net_value,
            price=current_price,
            token_amount=token_amount,
            fee_sol=fee_sol,
            pnl_sol=pnl_sol,
            pnl_percent=pnl_percent,
            balance_after=new_balance,
            notes=reason
        )
        
        # 更新账户状态
        self.db.update_account_state(new_balance, pnl_sol, is_win)
        
        # 移除持仓
        del self._holdings[token_id]
        
        result_emoji = "✅" if is_win else "❌"
        self._logger.info(
            f"{result_emoji} 模拟卖出: 代币#{token_id}, "
            f"PNL={pnl_sol:+.4f} SOL ({pnl_percent:+.1f}%), 原因: {reason}"
        )
        
        return TradeResult(
            success=True,
            trade_id=trade_id,
            action="SELL",
            amount_sol=net_value,
            price=current_price,
            token_amount=token_amount,
            fee_sol=fee_sol,
            balance_after=new_balance,
            message=f"卖出完成，{'盈利' if is_win else '亏损'} {abs(pnl_sol):.4f} SOL ({pnl_percent:+.1f}%)"
        )
    
    def _update_balance(self, new_balance: float):
        """直接更新余额（用于买入）"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE account_state SET balance_sol = ?, last_updated = CURRENT_TIMESTAMP
                WHERE id = (SELECT MAX(id) FROM account_state)
            """, (new_balance,))
    
    def check_positions(self) -> List[TradeResult]:
        """
        检查所有持仓，执行止盈止损
        
        返回:
            自动平仓的交易结果列表
        """
        results = []
        current_time = datetime.now()
        
        for token_id, holding in list(self._holdings.items()):
            # 获取当前价格
            token_info = self.db.get_token_by_href(holding.get("href", ""))
            if not token_info or not token_info.get("ca"):
                continue
            
            api_data = self.api.get_token_data(token_info["ca"])
            if not api_data:
                continue
            
            current_price = api_data.get("price_usd", 0)
            if current_price <= 0:
                continue
            
            buy_price = holding["buy_price"]
            price_change = ((current_price - buy_price) / buy_price * 100) if buy_price > 0 else 0
            hold_time = current_time - holding["buy_time"]
            
            # 检查止盈
            if price_change >= self.TAKE_PROFIT_PERCENT:
                result = self.sell(token_id, current_price, f"止盈 ({price_change:.1f}%)")
                results.append(result)
                continue
            
            # 检查止损
            if price_change <= self.STOP_LOSS_PERCENT:
                result = self.sell(token_id, current_price, f"止损 ({price_change:.1f}%)")
                results.append(result)
                continue
            
            # 检查超时
            if hold_time > timedelta(hours=self.MAX_HOLD_TIME_HOURS):
                result = self.sell(token_id, current_price, f"持仓超时 ({hold_time.days}天)")
                results.append(result)
                continue
        
        return results
    
    def is_success_by_market_cap(self, market_cap: float, price_change: float) -> bool:
        """
        根据市值判断是否达到成功标准
        
        参数:
            market_cap: 市值
            price_change: 价格变化百分比
            
        返回:
            是否成功
        """
        if market_cap < 1_000_000:  # < 1M
            return price_change >= self.SUCCESS_THRESHOLDS["below_1m"]
        else:  # >= 1M
            return price_change >= self.SUCCESS_THRESHOLDS["above_1m"]
    
    def get_holdings_count(self) -> int:
        """获取当前持仓数量"""
        return len(self._holdings)
    
    def get_holdings_summary(self) -> str:
        """获取持仓汇总"""
        if not self._holdings:
            return "当前无持仓"
        
        lines = ["当前持仓:"]
        for token_id, holding in self._holdings.items():
            buy_price = holding["buy_price"]
            amount = holding["token_amount"]
            hold_time = datetime.now() - holding["buy_time"]
            lines.append(
                f"  - 代币#{token_id}: {amount:.2f} @ ${buy_price:.8f} "
                f"(持有 {hold_time.seconds // 3600}小时)"
            )
        
        return "\n".join(lines)
    
    def get_trade_stats(self) -> Dict:
        """获取交易统计"""
        account = self.get_account_state()
        history = self.db.get_trade_history(100)
        
        # 计算额外统计
        sells = [t for t in history if t['action'] == 'SELL']
        avg_pnl = sum(t.get('pnl_sol', 0) or 0 for t in sells) / len(sells) if sells else 0
        
        return {
            "balance": account.balance_sol,
            "initial_balance": self.INITIAL_BALANCE,
            "total_pnl": account.total_pnl,
            "total_trades": account.total_trades,
            "winning_trades": account.winning_trades,
            "losing_trades": account.losing_trades,
            "win_rate": account.calculate_win_rate(),
            "average_pnl": avg_pnl,
            "current_holdings": self.get_holdings_count(),
        }
