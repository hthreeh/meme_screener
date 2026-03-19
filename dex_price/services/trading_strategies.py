"""
DEX 价格监控 - 多策略交易执行器
实现 5 种独立的交易策略，每种策略有独立的资金池和规则
"""

import logging
import threading  # 添加 threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any

from core.database import DatabaseManager
from core.api_client import DexScreenerAPI


_logger = logging.getLogger(__name__)
_trades_logger = logging.getLogger('trades')      # 交易记录专用日志
_positions_logger = logging.getLogger('positions')  # 持仓状态专用日志


class StrategyType(Enum):
    """策略类型"""
    # 基础/信号策略
    A = "A"  # 热度策略：热度>=150
    B = "B"  # 信号策略：5m+20m组合
    C = "C"  # 5m信号：任意5m信号
    D = "D"  # API暴涨：涨幅>=50%
    E = "E"  # 20m信号：任意20m信号
    F = "F"  # 1h信号：任意1h信号
    G = "G"  # 4h信号：任意4h信号
    # 高级策略
    H = "H"  # 金狗狙击：5m放量突破
    I = "I"  # 钻石手趋势：20m/1h/4h稳步爬坡
    # 智能策略
    ALPHA = "Alpha"  # 阿尔法评分：加权评分系统
    # 手动交易
    MANUAL = "M"  # 手动交易：用户手动输入CA买入


@dataclass
class StrategyConfig:
    """策略配置"""
    name: str
    trade_amount_sol: float
    initial_balance_sol: float = 100.0
    description: str = ""


@dataclass
class Position:
    """持仓记录（基于市值的模拟交易）"""
    token_id: int
    token_ca: str
    token_name: str
    strategy: StrategyType
    buy_market_cap: float  # 买入时的市值
    buy_amount_sol: float  # 买入金额 (SOL)
    buy_time: datetime
    remaining_ratio: float = 1.0  # 剩余仓位比例
    take_profit_level: int = 0    # 已触发的止盈级别
    # 移动止损追踪字段
    trailing_stop_multiplier: float = 0.7  # 当前止损倍数 (0.7 = -30%，与基类 STOP_LOSS_PERCENT 同步)
    highest_multiplier: float = 1.0  # 历史最高倍数
    check_count: int = 0  # 检查次数（用于超时规则）
    loss_check_count: int = 0  # 亏损次数（倍数 < 1.0 的检查次数）
    
    # 分段止损相关字段
    staged_stop_level: int = 0  # 已触发的分段止损级别 (0=未触发, 1=已触发level_1, 2=已触发level_2)
    
    # 趋势延期相关字段
    trend_extensions_count: int = 0  # 趋势延期次数
    
    def get_market_cap_multiplier(self, current_market_cap: float) -> float:
        """计算市值倍数"""
        if self.buy_market_cap <= 0:
            return 0.0
        return current_market_cap / self.buy_market_cap
    
    def get_current_value_sol(self, current_market_cap: float) -> float:
        """计算当前持仓价值（SOL）"""
        multiplier = self.get_market_cap_multiplier(current_market_cap)
        return self.buy_amount_sol * self.remaining_ratio * multiplier
    
    def update_trailing_stop(self, current_multiplier: float) -> None:
        """更新移动止损和追踪统计"""
        self.check_count += 1
        
        # 更新历史最高倍数
        if current_multiplier > self.highest_multiplier:
            self.highest_multiplier = current_multiplier
        
        # 追踪亏损次数（倍数 < 1.0）
        if current_multiplier < 1.0:
            self.loss_check_count += 1
        
        # 移动止损规则：
        # 涨幅 > 80% (1.8x) -> 止损移至 1.5x
        # 涨幅 > 30% (1.3x) -> 止损移至 1.0x (保本)
        if current_multiplier >= 1.8:
            self.trailing_stop_multiplier = max(self.trailing_stop_multiplier, 1.5)
        elif current_multiplier >= 1.3:
            self.trailing_stop_multiplier = max(self.trailing_stop_multiplier, 1.0)
    
    def get_stop_loss_percent(self) -> float:
        """获取当前止损百分比"""
        return (self.trailing_stop_multiplier - 1.0) * 100
    
    def should_time_exit(self, poll_interval_seconds: int = 60,
                         trend_extension_enabled: bool = False,
                         trend_extension_threshold: float = 0.10,
                         trend_extension_minutes: int = 30,
                         trend_extension_max_times: int = 2) -> tuple[bool, str]:
        """检查是否应该基于时间规则离场
        
        参数:
            poll_interval_seconds: 轮询间隔（秒）
            trend_extension_enabled: 是否启用趋势延期
            trend_extension_threshold: 触发延期的涨幅阈值（如 0.10 = 10%）
            trend_extension_minutes: 每次延期的分钟数
            trend_extension_max_times: 最大延期次数
        
        返回: (是否离场, 离场原因)
        """
        # 每次检查间隔约60秒，30分钟 = 30次检查
        base_timeout_checks = 30 * 60 // poll_interval_seconds  # 基础超时：30分钟
        checks_for_60min = 60 * 60 // poll_interval_seconds
        extension_checks = trend_extension_minutes * 60 // poll_interval_seconds
        
        # 计算当前有效超时阈值（基于已延期次数）
        effective_timeout_checks = base_timeout_checks + self.trend_extensions_count * extension_checks
        
        # 检查是否达到超时边界
        if self.check_count >= effective_timeout_checks:
            # 尝试趋势延期：如果满足条件且未达上限，延期而不是退出
            if trend_extension_enabled:
                current_multiplier = self.highest_multiplier
                if current_multiplier >= (1.0 + trend_extension_threshold):
                    if self.trend_extensions_count < trend_extension_max_times:
                        self.trend_extensions_count += 1
                        # 不返回 True，继续持有
                        return False, ""
            
            # 无法延期，检查是否达到亏损出场条件
            loss_ratio = self.loss_check_count / self.check_count if self.check_count > 0 else 0
            if loss_ratio >= 0.8:
                # Issue #5 修复：计算实际分钟数
                actual_minutes = self.check_count * poll_interval_seconds // 60
                return True, f"{actual_minutes}分钟内{loss_ratio*100:.0f}%时间亏损"
        
        # 规则2: 60分钟后（不受趋势延期影响），若一直在 -10% ~ +10% 震荡，强制离场
        # 但如果曾经上涨过 30% (已触发保本止损)，则不适用此规则
        if self.check_count >= checks_for_60min:
            if self.highest_multiplier < 1.1 and self.trailing_stop_multiplier < 1.0:
                return True, "60分钟无明显涨幅"
        
        return False, ""
    
    def try_extend_timeout(self, trend_extension_threshold: float = 0.10,
                           trend_extension_max_times: int = 2) -> bool:
        """尝试延期超时
        
        返回: 是否成功延期
        """
        current_multiplier = self.highest_multiplier
        if current_multiplier >= (1.0 + trend_extension_threshold):
            if self.trend_extensions_count < trend_extension_max_times:
                self.trend_extensions_count += 1
                return True
        return False


@dataclass
class StrategyState:
    """策略状态"""
    strategy_type: StrategyType
    balance_sol: float
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    positions: Dict[int, Position] = field(default_factory=dict)  # token_id -> Position
    
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100.0


class TradingStrategy(ABC):
    """交易策略基类"""
    
    # 止盈止损配置（优化后）
    TAKE_PROFIT_LEVELS = [
        (1.5, 0.5),   # 1.5倍卖一半（提前锁定利润）
        (3.0, 0.3),   # 3倍再卖30%
        (10.0, 1.0),  # 10倍清仓
    ]
    STOP_LOSS_PERCENT = -30.0  # 从 -50% 收紧到 -30%
    
    # 移动止损阈值
    TRAILING_STOP_BREAKEVEN = 1.3  # 涨30%后保本
    TRAILING_STOP_LOCK_PROFIT = 1.8  # 涨80%后锁定1.5x
    
    def __init__(self, strategy_type: StrategyType, config: StrategyConfig,
                 db: DatabaseManager, api: DexScreenerAPI):
        self.strategy_type = strategy_type
        self.config = config
        self.db = db
        self.api = api
        self._logger = logging.getLogger(f"{__name__}.{strategy_type.value}")
        self._lock = threading.Lock()  # 添加锁
        
        # 加载或初始化状态
        self.state = self._load_or_init_state()
    
    def _load_or_init_state(self) -> StrategyState:
        """从数据库加载或初始化策略状态"""
        strategy_name = self.strategy_type.value
        
        # 尝试从数据库加载状态
        saved_state = self.db.load_strategy_state(strategy_name)
        
        if saved_state:
            state = StrategyState(
                strategy_type=self.strategy_type,
                balance_sol=saved_state.get("balance_sol", self.config.initial_balance_sol),
                total_trades=saved_state.get("total_trades", 0),
                winning_trades=saved_state.get("winning_trades", 0),
                losing_trades=saved_state.get("losing_trades", 0),
                total_pnl=saved_state.get("total_pnl", 0.0),
            )
            
            # 加载持仓
            positions_data = self.db.load_positions(strategy_name)
            for pos_data in positions_data:
                try:
                    # 解析买入时间
                    buy_time_str = pos_data.get("buy_time")
                    if isinstance(buy_time_str, str):
                        buy_time = datetime.fromisoformat(buy_time_str)
                    else:
                        buy_time = buy_time_str or datetime.now()
                    
                    position = Position(
                        token_id=pos_data["token_id"],
                        token_ca=pos_data["token_ca"],
                        token_name=pos_data.get("token_name", "Unknown"),
                        strategy=self.strategy_type,
                        buy_market_cap=pos_data["buy_market_cap"],
                        buy_amount_sol=pos_data["buy_amount_sol"],
                        buy_time=buy_time,
                        remaining_ratio=pos_data.get("remaining_ratio", 1.0),
                        take_profit_level=pos_data.get("take_profit_level", 0),
                        highest_multiplier=pos_data.get("highest_multiplier", 1.0),
                        check_count=pos_data.get("poll_count", 0),
                        loss_check_count=pos_data.get("loss_check_count", 0),
                        trailing_stop_multiplier=pos_data.get("trailing_stop_multiplier", 0.7),
                        staged_stop_level=pos_data.get("staged_stop_level", 0),
                        trend_extensions_count=pos_data.get("trend_extensions_count", 0),
                    )
                    state.positions[position.token_id] = position
                except Exception as e:
                    self._logger.error(f"加载持仓失败: {e}")
            
            self._logger.info(
                f"[{strategy_name}] 从数据库加载状态: 余额={state.balance_sol:.2f} SOL, "
                f"持仓={len(state.positions)} 个"
            )
            return state
        else:
            # 初始化新状态
            return StrategyState(
                strategy_type=self.strategy_type,
                balance_sol=self.config.initial_balance_sol,
            )
    
    def _save_state(self) -> None:
        """保存策略状态到数据库"""
        state_dict = {
            "balance_sol": self.state.balance_sol,
            "total_trades": self.state.total_trades,
            "winning_trades": self.state.winning_trades,
            "losing_trades": self.state.losing_trades,
            "total_pnl": self.state.total_pnl,
        }
        self.db.save_strategy_state(self.strategy_type.value, state_dict)
    
    def _save_position(self, position: Position) -> None:
        """保存持仓到数据库"""
        position_data = {
            "token_id": position.token_id,
            "token_ca": position.token_ca,
            "token_name": position.token_name,
            "buy_market_cap": position.buy_market_cap,
            "buy_amount_sol": position.buy_amount_sol,
            "buy_time": position.buy_time.isoformat(),
            "remaining_ratio": position.remaining_ratio,
            "highest_multiplier": position.highest_multiplier,
            "take_profit_level": position.take_profit_level,
            "poll_count": position.check_count,
            "loss_check_count": position.loss_check_count,
            "trailing_stop_multiplier": position.trailing_stop_multiplier,
            "staged_stop_level": position.staged_stop_level,
            "trend_extensions_count": position.trend_extensions_count,
        }
        self.db.save_position(self.strategy_type.value, position_data)
    
    def _delete_position(self, token_id: int) -> None:
        """从数据库删除持仓"""
        self.db.delete_position(self.strategy_type.value, token_id)
    
    @abstractmethod
    def should_buy(self, token_id: int, token_ca: str, session_data: Dict) -> bool:
        """判断是否应该买入（子类实现具体逻辑）"""
        pass
    
    def execute_buy(self, token_id: int, token_ca: str, token_name: str,
                    current_market_cap: float, session_data: Dict = None) -> Optional[Position]:
        """
        执行买入（基于市值）
        
        全局要求:
        1. 5m买入次数 >= 10
        2. 如果上次交易是30%止损且距今<30分钟，拒绝买入
        """
        current_time = datetime.now()
        
        with self._lock:  # 加锁
            # === 全局检查 1: 5m买入次数 >= 10 ===
            if session_data:
                api_data = session_data.get("api_data", {})
                txns_5m_buys = api_data.get("txns_m5_buys", 0)
                
                if txns_5m_buys < 10:
                    self._logger.debug(
                        f"[{self.strategy_type.value}] 全局检查失败: 5m买入次数 {txns_5m_buys} < 10"
                    )
                    return None
            
            # === 全局检查 2: 30分钟止损冷却期 ===
            # 注意：使用 token_ca 直接查询，避免因 token_id 变化导致匹配失败
            try:
                recent_trades = self.db.get_recent_trades_by_ca(
                    strategy_type=self.strategy_type.value,
                    token_ca=token_ca,
                    limit=1
                )

                
                if recent_trades:
                    last_trade = recent_trades[0]
                    action = last_trade.get("action", "")
                    pnl = last_trade.get("pnl", 0)
                    trade_time_str = last_trade.get("created_at")
                    
                    # 检查是否是止损退出（亏损且action=SELL）
                    if action == "SELL" and pnl < 0:
                        if isinstance(trade_time_str, str):
                            trade_time = datetime.fromisoformat(trade_time_str)
                        else:
                            trade_time = trade_time_str
                        
                        time_diff = (current_time - trade_time).total_seconds()
                        
                        # 30分钟内止损过的代币，拒绝买入
                        if time_diff < 1800:  # 30 * 60 = 1800 秒
                            self._logger.info(
                                f"[{self.strategy_type.value}] 全局冷却期: {token_name} 距上次止损仅 {time_diff/60:.0f} 分钟"
                            )
                            return None
            except Exception as e:
                self._logger.warning(f"[{self.strategy_type.value}] 冷却期检查失败: {e}")
            
            # 检查余额
            if self.state.balance_sol < self.config.trade_amount_sol:
                self._logger.warning(f"[{self.strategy_type.value}] 余额不足: {self.state.balance_sol:.2f} SOL")
                return None
            
            # 检查是否已持有
            if token_id in self.state.positions:
                self._logger.info(f"[{self.strategy_type.value}] 已持有代币 {token_name}，跳过买入")
                return None
            
            # 使用固定金额 SOL 买入
            amount_sol = self.config.trade_amount_sol
            
            # 创建持仓记录（记录买入时的市值）
            position = Position(
                token_id=token_id,
                token_ca=token_ca,
                token_name=token_name,
                strategy=self.strategy_type,
                buy_market_cap=current_market_cap,  # 记录市值
                buy_amount_sol=amount_sol,
                buy_time=current_time
            )
            
            # 更新状态
            self.state.balance_sol -= amount_sol
            self.state.total_trades += 1
            self.state.positions[token_id] = position
            
            # 记录交易到数据库
            self.db.record_multi_strategy_trade(
                strategy_type=self.strategy_type.value,
                token_ca=token_ca,
                token_name=token_name,
                action="BUY",
                price=current_market_cap,  # 记录市值
                amount=amount_sol,
                pnl=0.0
            )
            
            # 保存持仓和策略状态到数据库（持久化）
            self._save_position(position)
            self._save_state()
        
        # 格式化市值显示
        if current_market_cap >= 1_000_000:
            mc_str = f"${current_market_cap/1_000_000:.2f}M"
        elif current_market_cap >= 1_000:
            mc_str = f"${current_market_cap/1_000:.1f}K"
        else:
            mc_str = f"${current_market_cap:.0f}"
        
        self._logger.info(
            f"✅ [{self.strategy_type.value}] 买入 {token_name}: "
            f"市值={mc_str}, 花费={amount_sol} SOL, 余额={self.state.balance_sol:.2f} SOL"
        )
        
        # 记录到交易日志
        _trades_logger.info(
            f"BUY | 策略{self.strategy_type.value} | {token_name} | "
            f"市值={mc_str} | 金额={amount_sol} SOL | 余额={self.state.balance_sol:.2f} SOL"
        )
        
        return position
    
    def check_and_execute_exits(self, current_market_caps: Dict[int, float],
                                staged_stop_loss_enabled: bool = True,
                                staged_stop_loss_level_1: tuple = (-0.15, 0.5),
                                staged_stop_loss_level_2: tuple = (-0.30, 1.0),
                                trend_extension_enabled: bool = False,
                                trend_extension_threshold: float = 0.10,
                                trend_extension_minutes: int = 30,
                                trend_extension_max_times: int = 2) -> List[Dict]:
        """检查并执行止盈止损
        
        支持: 分段止损、移动止损、趋势延期、超时离场
        
        参数:
            staged_stop_loss_enabled: 是否启用分段止损
            staged_stop_loss_level_1: 第一级止损 (触发百分比, 卖出比例)
            staged_stop_loss_level_2: 第二级止损 (触发百分比, 卖出比例)
            trend_extension_enabled: 是否启用趋势延期
            trend_extension_threshold: 触发延期的涨幅阈值
            trend_extension_minutes: 每次延期分钟数
            trend_extension_max_times: 最大延期次数
        """
        results = []
        
        with self._lock:  # 加锁
            if not self.state.positions:
                return results
                
            self._logger.debug(f"[{self.strategy_type.value}] 检查 {len(self.state.positions)} 个持仓...")
            
            # 使用 list() 创建副本进行迭代，因为可能会在循环中修改字典
            for token_id, position in list(self.state.positions.items()):
                if token_id not in current_market_caps:
                    continue
                
                current_mc = current_market_caps[token_id]
                if current_mc <= 0:
                    continue
                
                # 计算市值倍数
                multiplier = position.get_market_cap_multiplier(current_mc)
                pnl_percent = (multiplier - 1) * 100
                
                # 更新移动止损状态（每次检查都调用）
                position.update_trailing_stop(multiplier)
                
                # 获取当前动态止损线
                dynamic_stop_loss = position.get_stop_loss_percent()
                
                # 格式化市值显示
                def fmt_mc(mc):
                    if mc >= 1_000_000:
                        return f"${mc/1_000_000:.2f}M"
                    elif mc >= 1_000:
                        return f"${mc/1_000:.1f}K"
                    return f"${mc:.0f}"
                
                # 持仓状态日志（增加分段止损信息）
                self._logger.info(
                    f"  📊 [{self.strategy_type.value}] {position.token_name}: "
                    f"买入市值={fmt_mc(position.buy_market_cap)} → 当前={fmt_mc(current_mc)} | "
                    f"倍数={multiplier:.2f}x (历史最高={position.highest_multiplier:.2f}x) | "
                    f"盈亏={pnl_percent:+.1f}% | 止损线={dynamic_stop_loss:+.0f}% | "
                    f"剩余仓位={position.remaining_ratio*100:.0f}% | 分段止损级别={position.staged_stop_level}"
                )
                
                # === 1. 超时离场检查（优先级最高） ===
                should_exit, exit_reason = position.should_time_exit(
                    poll_interval_seconds=60,
                    trend_extension_enabled=trend_extension_enabled,
                    trend_extension_threshold=trend_extension_threshold,
                    trend_extension_minutes=trend_extension_minutes,
                    trend_extension_max_times=trend_extension_max_times
                )
                if should_exit:
                    result = self._execute_time_exit(position, current_mc, exit_reason)
                    results.append(result)
                    continue
                
                # === 2. 分段止损检查（优先于动态止损） ===
                if staged_stop_loss_enabled:
                    staged_result = self._check_staged_stop_loss(
                        position, current_mc, multiplier,
                        staged_stop_loss_level_1, staged_stop_loss_level_2
                    )
                    if staged_result:
                        results.append(staged_result)
                        # Issue #3 修复：分段止损后（无论减仓还是清仓）都跳过后续止损检查
                        continue
                
                # === 3. 动态止损检查（使用移动后的止损线）===
                # 注意：仅当未启用分段止损或分段止损未触发清仓时才执行
                if pnl_percent <= dynamic_stop_loss:
                    result = self._execute_stop_loss(position, current_mc, dynamic_stop_loss)
                    results.append(result)
                    continue
                
                # === 4. 分段止盈检查（基于市值倍数）===
                for level, (target_mult, sell_ratio) in enumerate(self.TAKE_PROFIT_LEVELS):
                    if position.take_profit_level > level:
                        continue  # 已触发过该级别
                    
                    if multiplier >= target_mult:
                        result = self._execute_take_profit(position, current_mc, level, sell_ratio)
                        results.append(result)
                        break  # 每次只触发一个级别
                else:
                    # 没有触发任何止盈/止损，保存更新后的持仓状态
                    if token_id in self.state.positions:
                        self._save_position(position)
        
        return results
    
    def _check_staged_stop_loss(self, position: Position, current_market_cap: float,
                                 multiplier: float,
                                 level_1: tuple, level_2: tuple) -> Optional[Dict]:
        """检查并执行分段止损
        
        参数:
            position: 持仓对象
            current_market_cap: 当前市值
            multiplier: 当前倍数
            level_1: (触发百分比, 卖出比例) 如 (-0.15, 0.5)
            level_2: (触发百分比, 卖出比例) 如 (-0.30, 1.0)
        
        返回:
            卖出结果字典 或 None
        """
        trigger_1, sell_ratio_1 = level_1
        trigger_2, sell_ratio_2 = level_2
        
        # 检查第二级止损（跌30%清仓）
        if multiplier <= (1.0 + trigger_2):
            if position.staged_stop_level < 2:
                return self._execute_staged_stop_loss(
                    position, current_market_cap, 2, sell_ratio_2,
                    trigger_2, is_full_exit=True
                )
        
        # 检查第一级止损（跌15%减仓50%）
        elif multiplier <= (1.0 + trigger_1):
            if position.staged_stop_level < 1 and position.remaining_ratio > 0.5:
                return self._execute_staged_stop_loss(
                    position, current_market_cap, 1, sell_ratio_1,
                    trigger_1, is_full_exit=False
                )
        
        return None
    
    def _execute_staged_stop_loss(self, position: Position, current_market_cap: float,
                                   level: int, sell_ratio: float,
                                   trigger_percent: float, is_full_exit: bool) -> Dict:
        """执行分段止损
        
        参数:
            position: 持仓对象
            current_market_cap: 当前市值
            level: 止损级别 (1 或 2)
            sell_ratio: 卖出比例 (如 0.5 = 50%)
            trigger_percent: 触发百分比 (如 -15)
            is_full_exit: 是否清仓
        """
        # 计算当前倍数
        multiplier = position.get_market_cap_multiplier(current_market_cap)
        
        # 计算卖出金额
        sell_amount = position.buy_amount_sol * position.remaining_ratio * sell_ratio
        sell_value = sell_amount * multiplier
        pnl = sell_value - sell_amount
        pnl_percent = (multiplier - 1) * 100
        
        # 更新状态
        self.state.balance_sol += sell_value
        if is_full_exit:
            self.state.total_trades += 1  # Issue #4 修复：更新 total_trades
            if pnl < 0:
                self.state.losing_trades += 1
            else:
                self.state.winning_trades += 1
        self.state.total_pnl += pnl
        
        # 更新持仓
        position.staged_stop_level = level
        if is_full_exit:
            # 清仓
            del self.state.positions[position.token_id]
            self._delete_position(position.token_id)
        else:
            # 减仓
            position.remaining_ratio *= (1 - sell_ratio)
            self._save_position(position)
        
        self._save_state()
        
        # 日志记录
        action_text = f"分段止损L{level}" + ("(清仓)" if is_full_exit else f"(减仓{sell_ratio*100:.0f}%)")
        self._logger.info(
            f"⚠️ [{self.strategy_type.value}] {action_text} {position.token_name}: "
            f"PNL={pnl:+.4f} SOL ({pnl_percent:+.1f}%), 余额={self.state.balance_sol:.2f} SOL"
        )
        
        _trades_logger.info(
            f"SELL | 策略{self.strategy_type.value} | {position.token_name} | "
            f"{action_text} | PNL={pnl:+.4f} SOL ({pnl_percent:+.1f}%) | 余额={self.state.balance_sol:.2f} SOL"
        )
        
        # 写入数据库记录
        try:
            self.db.record_multi_strategy_trade(
                strategy_type=self.strategy_type.value,
                token_ca=position.token_ca,
                token_name=position.token_name,
                action="SELL",
                price=current_market_cap,
                amount=sell_value,
                pnl=pnl
            )
        except Exception as e:
            self._logger.error(f"写入交易记录失败: {e}")
        
        return {
            "action": f"STAGED_STOP_L{level}",
            "strategy": self.strategy_type.value,
            "token_name": position.token_name,
            "token_ca": position.token_ca,
            "pnl": pnl,
            "pnl_percent": pnl_percent,
            "sell_ratio": sell_ratio,
            "is_full_exit": is_full_exit,
        }
    
    def _execute_stop_loss(self, position: Position, current_market_cap: float,
                           stop_loss_percent: float = None) -> Dict:
        """执行止损（支持动态止损）"""
        # 如果未指定止损百分比，使用默认值
        if stop_loss_percent is None:
            stop_loss_percent = self.STOP_LOSS_PERCENT
        
        # 计算止损倍数: -30% = 0.7x, 0% = 1.0x, +50% = 1.5x
        stop_multiplier = 1.0 + (stop_loss_percent / 100)
        
        # 止损时返回的金额 = 买入金额 * 剩余比例 * 止损倍数
        sell_value = position.buy_amount_sol * position.remaining_ratio * stop_multiplier
        pnl = sell_value - position.buy_amount_sol * position.remaining_ratio
        
        # 更新状态
        self.state.balance_sol += sell_value
        if pnl < 0:
            self.state.losing_trades += 1
        else:
            self.state.winning_trades += 1  # 保本或盈利止损算赢
        self.state.total_pnl += pnl
        
        # 移除持仓
        del self.state.positions[position.token_id]
        
        # 从数据库删除持仓并保存策略状态
        self._delete_position(position.token_id)
        self._save_state()
        
        # 判断是保本止损还是亏损止损
        if stop_loss_percent >= 0:
            action_text = "保本止损" if stop_loss_percent == 0 else f"盈利止损(+{stop_loss_percent:.0f}%)"
        else:
            action_text = f"止损({stop_loss_percent:.0f}%)"
        
        self._logger.info(
            f"❌ [{self.strategy_type.value}] {action_text} {position.token_name}: "
            f"PNL={pnl:+.4f} SOL ({stop_loss_percent:+.0f}%), 余额={self.state.balance_sol:.2f} SOL"
        )
        
        # 记录到交易日志
        _trades_logger.info(
            f"SELL | 策略{self.strategy_type.value} | {position.token_name} | "
            f"{action_text} | PNL={pnl:+.4f} SOL ({stop_loss_percent:+.0f}%) | 余额={self.state.balance_sol:.2f} SOL"
        )
        
        # 写入数据库记录
        try:
            self.db.record_multi_strategy_trade(
                strategy_type=self.strategy_type.value,
                token_ca=position.token_ca,
                token_name=position.token_name,
                action="SELL",
                price=current_market_cap,
                amount=sell_value,  # 注意这里是 sell_value (回笼资金)，而不是 buy_amount_sol
                pnl=pnl
            )
        except Exception as e:
            self._logger.error(f"写入交易记录失败: {e}")
        
        return {
            "action": "STOP_LOSS",
            "strategy": self.strategy_type.value,
            "token_name": position.token_name,
            "token_ca": position.token_ca,
            "pnl": pnl,
            "pnl_percent": stop_loss_percent,
        }
    
    def _execute_time_exit(self, position: Position, current_market_cap: float,
                           reason: str) -> Dict:
        """执行超时离场（按当前市值计算）"""
        # 计算当前倍数
        multiplier = position.get_market_cap_multiplier(current_market_cap)
        
        # 按当前市值卖出
        sell_value = position.buy_amount_sol * position.remaining_ratio * multiplier
        pnl = sell_value - position.buy_amount_sol * position.remaining_ratio
        pnl_percent = (multiplier - 1) * 100
        
        # 更新状态
        self.state.balance_sol += sell_value
        if pnl >= 0:
            self.state.winning_trades += 1
        else:
            self.state.losing_trades += 1
        self.state.total_pnl += pnl
        
        # 移除持仓
        del self.state.positions[position.token_id]
        
        # 从数据库删除持仓并保存策略状态
        self._delete_position(position.token_id)
        self._save_state()
        
        self._logger.info(
            f"⏰ [{self.strategy_type.value}] 超时离场 {position.token_name}: "
            f"原因={reason} | PNL={pnl:+.4f} SOL ({pnl_percent:+.1f}%), 余额={self.state.balance_sol:.2f} SOL"
        )
        
        # 记录到交易日志
        _trades_logger.info(
            f"SELL | 策略{self.strategy_type.value} | {position.token_name} | "
            f"超时离场({reason}) | PNL={pnl:+.4f} SOL ({pnl_percent:+.1f}%) | 余额={self.state.balance_sol:.2f} SOL"
        )
        
        # 写入数据库记录
        try:
            self.db.record_multi_strategy_trade(
                strategy_type=self.strategy_type.value,
                token_ca=position.token_ca,
                token_name=position.token_name,
                action="SELL",
                price=current_market_cap,
                amount=sell_value,
                pnl=pnl
            )
        except Exception as e:
            self._logger.error(f"写入交易记录失败: {e}")
        
        return {
            "action": "TIME_EXIT",
            "strategy": self.strategy_type.value,
            "token_name": position.token_name,
            "token_ca": position.token_ca,
            "pnl": pnl,
            "pnl_percent": pnl_percent,
            "reason": reason,
        }
    
    def _execute_take_profit(self, position: Position, current_market_cap: float,
                              level: int, sell_ratio: float) -> Dict:
        """执行分段止盈（理想化：按目标倍数计算）"""
        target_mult = self.TAKE_PROFIT_LEVELS[level][0]
        
        # 计算卖出部分的价值（基于目标倍数）
        # 卖出的 SOL = 买入SOL * 剩余比例 * 卖出比例 * 目标倍数
        sell_sol_amount = position.buy_amount_sol * position.remaining_ratio * sell_ratio
        sell_value = sell_sol_amount * target_mult
        
        # 计算盈亏
        pnl = sell_value - sell_sol_amount
        pnl_percent = (target_mult - 1) * 100
        
        # 更新状态
        self.state.balance_sol += sell_value
        self.state.total_pnl += pnl
        
        # 更新持仓
        position.remaining_ratio *= (1 - sell_ratio)
        position.take_profit_level = level + 1
        
        # 动态生成级别名称（基于实际倍数）
        level_name = f"{target_mult}x"
        self._logger.info(
            f"🎉 [{self.strategy_type.value}] 止盈{level_name} {position.token_name}: "
            f"卖出{sell_ratio*100:.0f}%, PNL=+{pnl:.4f} SOL (+{pnl_percent:.0f}%), "
            f"余额={self.state.balance_sol:.2f} SOL"
        )
        
        # 记录到交易日志
        _trades_logger.info(
            f"SELL | 策略{self.strategy_type.value} | {position.token_name} | "
            f"止盈{level_name} | 卖出{sell_ratio*100:.0f}% | "
            f"PNL={pnl:+.4f} SOL (+{pnl_percent:.0f}%) | 余额={self.state.balance_sol:.2f} SOL"
        )
        
        # 写入数据库记录
        try:
            self.db.record_multi_strategy_trade(
                strategy_type=self.strategy_type.value,
                token_ca=position.token_ca,
                token_name=position.token_name,
                action="SELL",
                price=current_market_cap,
                amount=sell_sol_amount,
                pnl=pnl
            )
        except Exception as e:
            self._logger.error(f"写入交易记录失败: {e}")
        
        # 如果清仓，记录为盈利交易并移除持仓
        if position.remaining_ratio < 0.01:
            self.state.winning_trades += 1
            del self.state.positions[position.token_id]
            # 从数据库删除持仓
            self._delete_position(position.token_id)
        else:
            # 部分卖出，更新数据库中的持仓
            self._save_position(position)
        
        # 保存策略状态
        self._save_state()
        
        return {
            "action": f"TAKE_PROFIT_{level_name}",
            "strategy": self.strategy_type.value,
            "token_name": position.token_name,
            "token_ca": position.token_ca,
            "pnl": pnl,
            "pnl_percent": pnl_percent,
            "sell_ratio": sell_ratio,
        }
    
    def manual_sell(self, token_id: int, current_market_cap: float) -> Optional[Dict]:
        """
        执行手动卖出
        
        参数:
            token_id: 代币 ID
            current_market_cap: 当前市值 (从 API 实时获取)
            
        返回:
            卖出结果字典 (成功) 或 None (失败)
        """
        with self._lock:
            if token_id not in self.state.positions:
                self._logger.warning(f"[{self.strategy_type.value}] 手动卖出失败: 未找到该持仓")
                return None
            
            position = self.state.positions[token_id]
            
            # 计算当前倍数和盈亏
            multiplier = position.get_market_cap_multiplier(current_market_cap)
            sell_value = position.buy_amount_sol * position.remaining_ratio * multiplier
            pnl = sell_value - position.buy_amount_sol * position.remaining_ratio
            pnl_percent = (multiplier - 1) * 100
            
            # 更新状态
            self.state.balance_sol += sell_value
            if pnl >= 0:
                self.state.winning_trades += 1
            else:
                self.state.losing_trades += 1
            self.state.total_pnl += pnl
            
            # 格式化市值显示
            def fmt_mc(mc):
                if mc >= 1_000_000:
                    return f"${mc/1_000_000:.2f}M"
                elif mc >= 1_000:
                    return f"${mc/1_000:.1f}K"
                return f"${mc:.0f}"
            
            # 移除持仓
            del self.state.positions[token_id]
            self._delete_position(token_id)
            self._save_state()
            
            self._logger.info(
                f"🔴 [{self.strategy_type.value}] 手动卖出 {position.token_name}: "
                f"买入市值={fmt_mc(position.buy_market_cap)} → 卖出市值={fmt_mc(current_market_cap)} | "
                f"PNL={pnl:+.4f} SOL ({pnl_percent:+.1f}%), 余额={self.state.balance_sol:.2f} SOL"
            )
            
            # 记录到交易日志
            _trades_logger.info(
                f"SELL | 策略{self.strategy_type.value} | {position.token_name} | "
                f"手动卖出 | PNL={pnl:+.4f} SOL ({pnl_percent:+.1f}%) | 余额={self.state.balance_sol:.2f} SOL"
            )
            
            # 写入数据库记录
            try:
                self.db.record_multi_strategy_trade(
                    strategy_type=self.strategy_type.value,
                    token_ca=position.token_ca,
                    token_name=position.token_name,
                    action="SELL",
                    price=current_market_cap,
                    amount=sell_value,
                    pnl=pnl
                )
            except Exception as e:
                self._logger.error(f"写入交易记录失败: {e}")
            
            return {
                "action": "MANUAL_SELL",
                "strategy": self.strategy_type.value,
                "token_name": position.token_name,
                "token_ca": position.token_ca,
                "buy_market_cap": position.buy_market_cap,
                "sell_market_cap": current_market_cap,
                "sell_value": sell_value,
                "pnl": pnl,
                "pnl_percent": pnl_percent,
                "balance_after": self.state.balance_sol,
            }
    
    def get_summary(self) -> str:
        """获取策略摘要"""
        s = self.state
        return (
            f"【策略{self.strategy_type.value}】{self.config.name}\n"
            f"  余额: {s.balance_sol:.2f} SOL | 初始: {self.config.initial_balance_sol} SOL\n"
            f"  总交易: {s.total_trades} | 盈: {s.winning_trades} | 亏: {s.losing_trades}\n"
            f"  胜率: {s.win_rate():.1f}% | 总PNL: {s.total_pnl:+.4f} SOL\n"
            f"  当前持仓: {len(s.positions)} 个"
        )


# 具体策略实现

class StrategyA(TradingStrategy):
    """
    策略A：优化版5m策略 (Optimized 5m Strategy)
    基于C策略优化，增加更多入场条件限制
    核心: 降低交易频率，提高胜率
    """
    
    # 市值区间
    MIN_MARKET_CAP = 50_000
    MAX_MARKET_CAP = 2_000_000
    
    # API 验证阈值
    MIN_5M_BUYS = 20
    MIN_5M_VOLUME = 2_000  # $2K
    
    # 冷静期（秒）
    LOSS_COOLDOWN_SINGLE = 3600      # 单次亏损后冷静1小时
    LOSS_COOLDOWN_CONSECUTIVE = 14400  # 连续两次亏损后冷静4小时
    PROFIT_TRAILING_COOLDOWN = 1800   # 移动止盈后冷静30分钟
    
    def should_buy(self, token_id: int, token_ca: str, session_data: Dict) -> bool:
        # 1. 检查**当前触发的信号**是否是 5m 信号
        current_signal = session_data.get("current_signal_type", "")
        if current_signal != "5m":
            return False

        
        # 2. 检查市值区间
        market_cap = session_data.get("current_market_cap", 0)
        if not (self.MIN_MARKET_CAP <= market_cap <= self.MAX_MARKET_CAP):
            self._logger.debug(f"[A] 市值 ${market_cap:.0f} 不在目标区间")
            return False
        
        # 3. API 验证
        api_data = session_data.get("api_data", {})
        if not api_data:
            self._logger.debug("[A] 无 API 数据，跳过")
            return False
        
        txns_5m_buys = api_data.get("txns_m5_buys", 0)
        volume_5m = api_data.get("volume_m5", 0)
        
        # 3.1 5m买入次数 > 20
        if txns_5m_buys <= self.MIN_5M_BUYS:
            self._logger.debug(f"[A] 5m买入笔数 {txns_5m_buys} <= {self.MIN_5M_BUYS}，不满足")
            return False
        
        # 3.2 5m交易量 > $2K
        if volume_5m < self.MIN_5M_VOLUME:
            self._logger.debug(f"[A] 5m交易量 ${volume_5m:.0f} < ${self.MIN_5M_VOLUME}，不满足")
            return False
        
        # 4. 冷静期检查（查询数据库）
        if not self._check_cooldown(token_id):
            return False
        
        self._logger.info(
            f"[A] 优化版5m条件满足! 5m买入={txns_5m_buys}, 5m交易量=${volume_5m:.0f}"
        )
        return True
    
    def _check_cooldown(self, token_id: int) -> bool:
        """检查冷静期"""
        # datetime 已在文件顶部导入
        
        try:
            # 获取该代币在本策略的最近交易记录
            recent_trades = self.db.get_recent_trades_for_token(
                strategy_type=self.strategy_type.value,
                token_id=token_id,
                limit=2
            )
            
            if not recent_trades:
                return True  # 无历史交易，允许买入
            
            now = datetime.now()
            last_trade = recent_trades[0]
            
            # 解析时间
            trade_time_str = last_trade.get("created_at")
            if isinstance(trade_time_str, str):
                trade_time = datetime.fromisoformat(trade_time_str)
            else:
                trade_time = trade_time_str
            
            time_diff = (now - trade_time).total_seconds()
            
            # 检查是否是止损退出
            action = last_trade.get("action", "")
            pnl = last_trade.get("pnl", 0)
            
            # 追跌冷静期：亏损后1小时内不买入
            if action == "SELL" and pnl < 0:
                if time_diff < self.LOSS_COOLDOWN_SINGLE:
                    self._logger.debug(f"[A] 追跌冷静期: {time_diff/60:.0f}分钟 < 60分钟")
                    return False
                
                # 检查是否连续两次亏损
                if len(recent_trades) >= 2:
                    second_trade = recent_trades[1]
                    second_pnl = second_trade.get("pnl", 0)
                    if second_pnl < 0:
                        # 连续亏损：从第二次（较早的）亏损时间开始计算冷静期
                        second_time_str = second_trade.get("created_at")
                        if isinstance(second_time_str, str):
                            second_time = datetime.fromisoformat(second_time_str)
                        else:
                            second_time = second_time_str
                        
                        time_diff_from_first_loss = (now - second_time).total_seconds()
                        if time_diff_from_first_loss < self.LOSS_COOLDOWN_CONSECUTIVE:
                            self._logger.debug(f"[A] 连续亏损冷静期: {time_diff_from_first_loss/3600:.1f}小时 < 4小时")
                            return False
            
            # 追涨冷静期：盈利退出后30分钟内不买入
            # (简化判断：只检查盈利退出)
            if action == "SELL" and pnl > 0:
                if time_diff < self.PROFIT_TRAILING_COOLDOWN:
                    self._logger.debug(f"[A] 追涨冷静期: {time_diff/60:.0f}分钟 < 30分钟")
                    return False
            
            return True
            
        except Exception as e:
            self._logger.warning(f"[A] 冷静期检查失败: {e}")
            return True  # 失败时允许买入


class StrategyB(TradingStrategy):
    """策略B：5m+20m信号组合（当前20m信号 + 历史5m信号）"""
    
    def should_buy(self, token_id: int, token_ca: str, session_data: Dict) -> bool:
        # 当前必须是 20m 信号触发
        current_signal = session_data.get("current_signal_type", "")
        if current_signal != "20m":
            return False
        
        # 同时需要历史上有过 5m 信号
        signals = session_data.get("signals", [])
        has_5m = any(s.get("type") == "5m" for s in signals)
        return has_5m


class StrategyC(TradingStrategy):
    """策略C：任意5m信号（当前触发）"""
    
    def should_buy(self, token_id: int, token_ca: str, session_data: Dict) -> bool:
        current_signal = session_data.get("current_signal_type", "")
        return current_signal == "5m"


class StrategyD(TradingStrategy):
    """策略D：API暴涨（涨幅>=50%）"""
    
    GAIN_THRESHOLD = 50.0
    
    def should_buy(self, token_id: int, token_ca: str, session_data: Dict) -> bool:
        # 获取API历史数据
        api_samples = session_data.get("api_samples", [])
        if not api_samples or len(api_samples) < 2:
            return False
            
        # 获取最新的两个样本
        # 样本格式: {"time": str(isoformat), "market_cap": float, ...}
        # datetime 已在文件顶部导入
        current_sample = api_samples[-1]
        prev_sample = api_samples[-2]
        
        current_mc = current_sample.get("market_cap", 0)
        prev_mc = prev_sample.get("market_cap", 0)
        
        if prev_mc <= 0 or current_mc <= 0:
            return False
            
        # 检查时间间隔（必须 <= 3分钟）
        try:
            current_time = datetime.fromisoformat(current_sample.get("time"))
            prev_time = datetime.fromisoformat(prev_sample.get("time"))
            diff_seconds = (current_time - prev_time).total_seconds()
            
            # 如果间隔超过3分钟（180秒），说明是断档数据（例如重启或长轮询），不进行比较
            if diff_seconds > 180:
                # self._logger.debug(f"[D] 样本间隔过大 ({diff_seconds:.0f}s > 180s)，跳过")
                return False
                
        except Exception:
            # 时间解析失败
            return False
            
        # 计算涨幅 (相邻两次)
        gain = ((current_mc - prev_mc) / prev_mc) * 100
        
        if gain >= self.GAIN_THRESHOLD:
            self._logger.info(
                f"[D] 暴涨检测: {prev_mc:,.0f} -> {current_mc:,.0f} "
                f"(+{gain:.1f}%) in {diff_seconds:.0f}s"
            )
            return True
            
        return False


class StrategyE(TradingStrategy):
    """策略E：任意20m信号（当前触发）+ 5m买入次数>=50"""
    
    MIN_5M_BUYS = 50
    
    def should_buy(self, token_id: int, token_ca: str, session_data: Dict) -> bool:
        # 当前必须是 20m 信号触发
        current_signal = session_data.get("current_signal_type", "")
        if current_signal != "20m":
            return False
        
        # 检查 5m 买入次数
        api_data = session_data.get("api_data", {})
        txns_5m_buys = api_data.get("txns_m5_buys", 0)
        if txns_5m_buys < self.MIN_5M_BUYS:
            self._logger.debug(f"[E] 5m买入次数 {txns_5m_buys} < {self.MIN_5M_BUYS}，不满足")
            return False
        
        return True


class StrategyF(TradingStrategy):
    """策略F：任意1h信号（当前触发）+ 1h买入次数>=300"""
    
    MIN_1H_BUYS = 300
    
    def should_buy(self, token_id: int, token_ca: str, session_data: Dict) -> bool:
        # 当前必须是 1h 信号触发
        current_signal = session_data.get("current_signal_type", "")
        if current_signal != "1h":
            return False
        
        # 检查 1h 买入次数
        api_data = session_data.get("api_data", {})
        txns_1h_buys = api_data.get("txns_h1_buys", 0)
        if txns_1h_buys < self.MIN_1H_BUYS:
            self._logger.debug(f"[F] 1h买入次数 {txns_1h_buys} < {self.MIN_1H_BUYS}，不满足")
            return False
        
        return True


class StrategyG(TradingStrategy):
    """策略G：任意4h信号（当前触发）+ 1h买入次数>=500"""
    
    MIN_1H_BUYS = 500
    
    def should_buy(self, token_id: int, token_ca: str, session_data: Dict) -> bool:
        # 当前必须是 4h 信号触发
        current_signal = session_data.get("current_signal_type", "")
        if current_signal != "4h":
            return False
        
        # 检查 1h 买入次数
        api_data = session_data.get("api_data", {})
        txns_1h_buys = api_data.get("txns_h1_buys", 0)
        if txns_1h_buys < self.MIN_1H_BUYS:
            self._logger.debug(f"[G] 1h买入次数 {txns_1h_buys} < {self.MIN_1H_BUYS}，不满足")
            return False
        
        return True


class StrategyH(TradingStrategy):
    """
    策略H：金狗狙击 (Golden Dog Sniper)
    风格: 高频、爆发、激进
    核心: 放量突破
    """
    
    # 自定义止盈止损（覆盖基类）
    TAKE_PROFIT_LEVELS = [
        (1.5, 0.5),   # TP1: 1.5x 卖 50%
        (3.0, 0.3),   # TP2: 3x 卖 30%
        (20.0, 0.1),  # TP3: 20x 卖 10%
        (50.0, 0.1),  # TP4: 50x 卖 10%
    ]
    STOP_LOSS_PERCENT = -30.0
    
    # 市值区间
    MIN_MARKET_CAP = 50_000
    MAX_MARKET_CAP = 2_000_000
    
    # API 验证阈值
    MIN_5M_BUYS = 20
    MIN_BUY_SELL_RATIO = 1.5
    
    def should_buy(self, token_id: int, token_ca: str, session_data: Dict) -> bool:
        # 1. 检查**当前触发的信号**是否是 5m 信号
        current_signal = session_data.get("current_signal_type", "")
        if current_signal != "5m":
            return False
        
        # 2. 检查市值区间
        market_cap = session_data.get("current_market_cap", 0)
        if not (self.MIN_MARKET_CAP <= market_cap <= self.MAX_MARKET_CAP):
            self._logger.debug(f"[H] 市值 ${market_cap:.0f} 不在目标区间")
            return False
        
        # 3. API 验证
        api_data = session_data.get("api_data", {})
        if not api_data:
            self._logger.debug("[H] 无 API 数据，跳过")
            return False
        
        txns_5m_buys = api_data.get("txns_m5_buys", 0)
        txns_5m_sells = api_data.get("txns_m5_sells", 0)
        
        # 3.1 买单压制
        if txns_5m_buys <= self.MIN_5M_BUYS:
            self._logger.debug(f"[H] 5m买入笔数 {txns_5m_buys} <= {self.MIN_5M_BUYS}，不满足")
            return False
        
        # 3.2 买卖比
        if txns_5m_sells > 0:
            ratio = txns_5m_buys / txns_5m_sells
            if ratio < self.MIN_BUY_SELL_RATIO:
                self._logger.debug(f"[H] 买卖比 {ratio:.2f} < {self.MIN_BUY_SELL_RATIO}，不满足")
                return False
        
        self._logger.info(
            f"[H] 金狗狙击条件满足! 5m买入={txns_5m_buys}, "
            f"买卖比={txns_5m_buys/max(1,txns_5m_sells):.2f}"
        )
        return True


class StrategyI(TradingStrategy):
    """
    策略I：钻石手趋势 (Diamond Hand Trend)
    风格: 中长线、稳健
    核心: 稳步爬坡，跟随庄家
    """
    
    # 自定义止盈止损
    TAKE_PROFIT_LEVELS = [
        (3.0, 0.3),   # 3x 卖 30% - 晚止盈，吃主升浪
        (10.0, 0.4),  # 10x 卖 40% - 主力出货区
        (50.0, 0.3),  # 50x 卖 30% - 梦想单
    ]
    STOP_LOSS_PERCENT = -50.0  # 宽止损
    
    # 条件阈值（更新）
    MIN_MARKET_CAP = 100_000  # 从300K改为100K
    MIN_HEAT_SCORE = 150  # 从200改为150
    MIN_DRAWDOWN_RATIO = 0.8  # 当前市值 > 最高市值的 80%
    MIN_1H_BUYS = 1000  # 从50改为1000
    
    def should_buy(self, token_id: int, token_ca: str, session_data: Dict) -> bool:
        # 1. 检查**当前触发的信号**是否是 20m、1h 或 4h 信号
        current_signal = session_data.get("current_signal_type", "")
        if current_signal not in ("20m", "1h", "4h"):
            return False

        
        # 2. 市值要求
        market_cap = session_data.get("current_market_cap", 0)
        if market_cap < self.MIN_MARKET_CAP:
            self._logger.debug(f"[I] 市值 ${market_cap:.0f} < ${self.MIN_MARKET_CAP}")
            return False
        
        # 3. 热度累积
        heat_score = session_data.get("heat_score", 0)
        if heat_score < self.MIN_HEAT_SCORE:
            self._logger.debug(f"[I] 热度 {heat_score} < {self.MIN_HEAT_SCORE}")
            return False
        
        # 4. 拒绝回撤
        highest_mc = session_data.get("highest_market_cap", market_cap)
        if highest_mc > 0 and market_cap / highest_mc < self.MIN_DRAWDOWN_RATIO:
            drawdown = (1 - market_cap / highest_mc) * 100
            self._logger.debug(f"[I] 回撤 {drawdown:.1f}% > 20%")
            return False
        
        # 5. 筹码交换 (1h 买入笔数)
        api_data = session_data.get("api_data", {})
        txns_1h_buys = api_data.get("txns_h1_buys", 0)
        if txns_1h_buys < self.MIN_1H_BUYS:
            self._logger.debug(f"[I] 1h买入笔数 {txns_1h_buys} < {self.MIN_1H_BUYS}")
            return False
        
        self._logger.info(
            f"[I] 钻石手条件满足! 热度={heat_score}, 1h买入={txns_1h_buys}"
        )
        return True


class StrategyAlpha(TradingStrategy):
    """
    策略Alpha：阿尔法评分 (Alpha Score System)
    风格: 综合评估、智能筛选
    核心: 多维度加权评分，只买高质量标的
    
    评分公式:
    AlphaScore = (0.3 * WalletScore) + (0.3 * TxnMomentum) + (0.2 * LiqSafety) + (0.2 * SocialHeat)
    """
    
    # 评分阈值
    SCORE_THRESHOLD = 80  # 总分阈值 (满分100)
    
    # 权重配置
    WEIGHT_WALLET = 0.3
    WEIGHT_TXN = 0.3
    WEIGHT_LIQ = 0.2
    WEIGHT_HEAT = 0.2
    
    # 各指标阈值
    WALLET_FULL_SCORE = 500  # 500个钱包 = 满分
    WALLET_ZERO_SCORE = 100  # <100个钱包 = 0分
    TXN_5M_THRESHOLD = 50   # 从100改为50
    BUY_RATIO_THRESHOLD = 1.5  # 买卖比阈值
    LIQ_HIGH_RATIO = 0.15    # 高流动性比 (>15%)
    LIQ_LOW_RATIO = 0.05     # 低流动性比 (<5% 扣分)
    
    def should_buy(self, token_id: int, token_ca: str, session_data: Dict) -> bool:
        # 必须是当前5m信号触发
        current_signal = session_data.get("current_signal_type", "")
        if current_signal != "5m":
            return False

        
        # 计算各维度分数
        api_data = session_data.get("api_data", {})
        
        # 1. WalletScore (30%)
        wallet_count = session_data.get("wallet_count", 0)
        if wallet_count < self.WALLET_ZERO_SCORE:
            wallet_score = 0
        elif wallet_count >= self.WALLET_FULL_SCORE:
            wallet_score = 100
        else:
            wallet_score = ((wallet_count - self.WALLET_ZERO_SCORE) / 
                          (self.WALLET_FULL_SCORE - self.WALLET_ZERO_SCORE)) * 100
        
        # 2. TxnMomentum (30%)
        txns_m5_buys = api_data.get("txns_m5_buys", 0)
        txns_m5_sells = api_data.get("txns_m5_sells", 0)
        buy_ratio = txns_m5_buys / max(1, txns_m5_sells)
        
        txn_score = 0
        if txns_m5_buys >= self.TXN_5M_THRESHOLD and buy_ratio >= self.BUY_RATIO_THRESHOLD:
            txn_score = 100
        elif txns_m5_buys >= self.TXN_5M_THRESHOLD * 0.5:
            txn_score = 50
        
        # 3. LiqSafety (20%)
        liquidity = api_data.get("liquidity_usd", 0)
        market_cap = session_data.get("current_market_cap", 0)
        liq_ratio = liquidity / max(1, market_cap)
        
        if liq_ratio >= self.LIQ_HIGH_RATIO:
            liq_score = 100
        elif liq_ratio >= self.LIQ_LOW_RATIO:
            liq_score = 50
        else:
            liq_score = 0  # 流动性过低，直接0分
        
        # 4. SocialHeat (20%)
        heat_score = session_data.get("heat_score", 0)
        # 热度归一化 (假设300为满分)
        normalized_heat = min(100, (heat_score / 300) * 100)
        
        # 计算总分
        total_score = (
            self.WEIGHT_WALLET * wallet_score +
            self.WEIGHT_TXN * txn_score +
            self.WEIGHT_LIQ * liq_score +
            self.WEIGHT_HEAT * normalized_heat
        )
        
        self._logger.info(
            f"[Alpha] 评分明细: 钱包={wallet_score:.0f} | 动能={txn_score:.0f} | "
            f"流动性={liq_score:.0f} | 热度={normalized_heat:.0f} => 总分={total_score:.1f}"
        )
        
        return total_score >= self.SCORE_THRESHOLD


class ManualStrategy(TradingStrategy):
    """
    手动交易策略 (M)
    
    用户通过 Web 界面手动输入 CA 地址触发买入。
    该策略不参与自动评估，只在手动调用时执行买入。
    止盈止损规则与基础策略相同。
    """
    
    def should_buy(self, token_id: int, token_ca: str, session_data: Dict) -> bool:
        """手动策略不参与自动评估，始终返回 False"""
        return False
    
    def manual_buy(self, token_ca: str, amount_sol: float, 
                   token_data: Dict) -> Optional[Position]:
        """
        执行手动买入
        
        参数:
            token_ca: 代币合约地址
            amount_sol: 买入金额 (SOL)
            token_data: 从 API 获取的代币数据
            
        返回:
            Position 对象 (成功) 或 None (失败)
        """
        # 解析代币信息
        token_name = token_data.get("baseToken", {}).get("name", "Unknown")
        token_symbol = token_data.get("baseToken", {}).get("symbol", "UNKNOWN")
        market_cap = token_data.get("marketCap", 0) or 0
        
        if market_cap <= 0:
            self._logger.warning(f"[Manual] 无法获取市值: {token_ca[:20]}...")
            return None
        
        # 生成临时 href (格式: /solana/{ca})
        chain_id = token_data.get("chainId", "solana")
        href = f"/{chain_id}/{token_ca}"
        
        # 获取或创建代币记录
        token_id = self.db.get_or_create_token(
            href=href,
            name=token_name,
            symbol=token_symbol,
            ca=token_ca
        )
        
        # 临时覆盖交易金额
        original_amount = self.config.trade_amount_sol
        self.config.trade_amount_sol = amount_sol
        
        # 执行买入
        position = self.execute_buy(token_id, token_ca, token_name, market_cap)
        
        # 恢复原配置
        self.config.trade_amount_sol = original_amount
        
        return position


def create_all_strategies(db: DatabaseManager, api: DexScreenerAPI,
                          strategy_configs: Dict[str, Dict]) -> Dict[StrategyType, TradingStrategy]:
    """创建所有策略实例"""
    strategy_classes = {
        # 基础/信号策略
        StrategyType.A: StrategyA,
        StrategyType.B: StrategyB,
        StrategyType.C: StrategyC,
        StrategyType.D: StrategyD,
        StrategyType.E: StrategyE,
        StrategyType.F: StrategyF,
        StrategyType.G: StrategyG,
        # 高级策略
        StrategyType.H: StrategyH,
        StrategyType.I: StrategyI,
        # 智能策略
        StrategyType.ALPHA: StrategyAlpha,
        # 手动交易
        StrategyType.MANUAL: ManualStrategy,
    }
    
    strategies = {}
    for st_type, st_class in strategy_classes.items():
        cfg_dict = strategy_configs.get(st_type.value, {})
        config = StrategyConfig(
            name=cfg_dict.get("name", st_type.value),
            trade_amount_sol=cfg_dict.get("trade_amount_sol", 0.1),
            initial_balance_sol=cfg_dict.get("initial_balance_sol", 100.0),
            description=cfg_dict.get("description", ""),
        )
        strategies[st_type] = st_class(st_type, config, db, api)
    
    return strategies


