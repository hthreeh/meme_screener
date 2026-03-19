"""
Currency data models for DEX Price Monitor.
Uses dataclasses for type safety and clean serialization.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, Optional, Any


@dataclass
class GrowthRates:
    """Price change rates across different time frames."""
    m5: float = 0.0   # 5 minutes
    h1: float = 0.0   # 1 hour
    h6: float = 0.0   # 6 hours
    h24: float = 0.0  # 24 hours

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary with original key format."""
        return {
            "5M": self.m5,
            "1H": self.h1,
            "6H": self.h6,
            "24H": self.h24,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "GrowthRates":
        """Create from dictionary with original key format."""
        return cls(
            m5=data.get("5M", 0.0),
            h1=data.get("1H", 0.0),
            h6=data.get("6H", 0.0),
            h24=data.get("24H", 0.0),
        )


@dataclass
class MarketData:
    """市场数据：价格、流动性、交易量等"""
    price: float = 0.0
    price_str: str = ""
    liquidity: float = 0.0
    liquidity_str: str = ""
    volume_24h: float = 0.0
    volume_24h_str: str = ""
    txns_24h: int = 0
    makers_24h: int = 0
    pair_age: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "price": self.price,
            "price_str": self.price_str,
            "liquidity": self.liquidity,
            "liquidity_str": self.liquidity_str,
            "volume_24h": self.volume_24h,
            "volume_24h_str": self.volume_24h_str,
            "txns_24h": self.txns_24h,
            "makers_24h": self.makers_24h,
            "pair_age": self.pair_age,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MarketData":
        return cls(
            price=data.get("price", 0.0),
            price_str=data.get("price_str", ""),
            liquidity=data.get("liquidity", 0.0),
            liquidity_str=data.get("liquidity_str", ""),
            volume_24h=data.get("volume_24h", 0.0),
            volume_24h_str=data.get("volume_24h_str", ""),
            txns_24h=data.get("txns_24h", 0),
            makers_24h=data.get("makers_24h", 0),
            pair_age=data.get("pair_age", ""),
        )


@dataclass
class CurrencyData:
    """Represents a cryptocurrency's data from DexScreener."""
    href: str
    currency_name: str
    contract_address: str
    market_value: str
    market_value_num: float
    growth_rates: GrowthRates
    source_file: str = ""
    # 新增市场数据字段
    market_data: Optional[MarketData] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "currency_name": self.currency_name,
            "ca": self.contract_address,
            "market_value": self.market_value,
            "growth_rates": self.growth_rates.to_dict(),
            "source_file": self.source_file,
        }
        if self.market_data:
            result["market_data"] = self.market_data.to_dict()
        return result

    def to_db_snapshot(self) -> Dict[str, Any]:
        """转换为数据库快照格式"""
        data = {
            "market_cap": self.market_value_num,
            "market_cap_str": self.market_value,
            "growth_5m": self.growth_rates.m5,
            "growth_1h": self.growth_rates.h1,
            "growth_6h": self.growth_rates.h6,
            "growth_24h": self.growth_rates.h24,
            "source_file": self.source_file,
        }
        if self.market_data:
            data.update({
                "price": self.market_data.price,
                "liquidity": self.market_data.liquidity,
                "liquidity_str": self.market_data.liquidity_str,
                "volume_24h": self.market_data.volume_24h,
                "volume_24h_str": self.market_data.volume_24h_str,
                "txns_24h": self.market_data.txns_24h,
                "makers_24h": self.market_data.makers_24h,
                "pair_age": self.market_data.pair_age,
            })
        return data

    @classmethod
    def from_dict(cls, href: str, data: Dict[str, Any]) -> "CurrencyData":
        """Create from dictionary (JSON deserialization)."""
        from ..utils.helpers import convert_value_to_number

        growth_rates = GrowthRates.from_dict(data.get("growth_rates", {}))
        market_value = data.get("market_value", "N/A")
        
        market_data = None
        if "market_data" in data:
            market_data = MarketData.from_dict(data["market_data"])

        return cls(
            href=href,
            currency_name=data.get("currency_name", "Unknown"),
            contract_address=data.get("ca", "Unknown"),
            market_value=market_value,
            market_value_num=convert_value_to_number(market_value),
            growth_rates=growth_rates,
            source_file=data.get("source_file", ""),
            market_data=market_data,
        )


@dataclass
class Alert:
    """Represents a price change alert."""
    currency: CurrencyData
    period_name: str
    change_rate: float
    previous_value: str
    current_value: str
    history_count: int = 0

    @property
    def is_significant(self) -> bool:
        """Check if the change rate is significant (> 50%)."""
        return self.change_rate > 50.0

    def get_append_str(self) -> str:
        """Get history count string for notifications."""
        if self.history_count > 0:
            return f"（历史第 {self.history_count + 1} 次记录）"
        return ""


@dataclass
class SignalEvent:
    """信号事件模型"""
    id: int
    token_id: int
    signal_type: str
    trigger_value: float
    market_cap_at_trigger: float
    price_at_trigger: float
    is_validated: bool = False
    validation_result: str = ""
    created_at: datetime = None

    # 关联数据（可选）
    token_name: str = ""
    token_symbol: str = ""
    token_href: str = ""
    token_ca: str = ""


@dataclass
class SimulatedTrade:
    """模拟交易记录"""
    id: int
    token_id: int
    signal_event_id: int
    action: str  # 'BUY' or 'SELL'
    amount_sol: float
    price_at_trade: float
    token_amount: float
    fee_percent: float = 3.0
    fee_sol: float = 0.0
    pnl_sol: float = 0.0
    pnl_percent: float = 0.0
    balance_after: float = 0.0
    notes: str = ""
    timestamp: datetime = None


@dataclass
class AccountState:
    """模拟账户状态"""
    balance_sol: float = 100.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0

    def calculate_win_rate(self) -> float:
        """计算胜率"""
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100.0

    def to_summary_str(self) -> str:
        """生成账户汇总字符串"""
        return (
            f"💰 余额: {self.balance_sol:.2f} SOL\n"
            f"📊 总交易: {self.total_trades} 次\n"
            f"✅ 盈利: {self.winning_trades} | ❌ 亏损: {self.losing_trades}\n"
            f"📈 胜率: {self.calculate_win_rate():.1f}%\n"
            f"💵 总盈亏: {self.total_pnl:+.4f} SOL"
        )

