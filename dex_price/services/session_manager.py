"""
DEX 价格监控 - 动态会话管理器
负责管理活跃代币的 API 追踪会话，独立于主循环运行
支持多周期信号触发和基于市值的动态参数调整
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from enum import Enum

from core.api_client import DexScreenerAPI
from core.database import DatabaseManager


_logger = logging.getLogger(__name__)


class SignalType(Enum):
    """信号类型"""
    SIGNAL_5M = "5m"
    SIGNAL_20M = "20m"
    SIGNAL_1H = "1h"
    SIGNAL_4H = "4h"


# === 参数配置 ===
# 统一轮询间隔（秒）
UNIFIED_POLL_INTERVAL = 60  # 统一 60 秒轮询

# 寿命增量（秒）- 根据信号类型
SIGNAL_BASE_PARAMS = {
    SignalType.SIGNAL_5M: {"life": 900},      # +15分钟寿命
    SignalType.SIGNAL_20M: {"life": 2700},    # +45分钟寿命
    SignalType.SIGNAL_1H: {"life": 14400},    # +4小时寿命
    SignalType.SIGNAL_4H: {"life": 28800},    # +8小时寿命
}

# 市值区间寿命修正系数
MARKET_CAP_MODIFIERS = [
    # (max_market_cap, life_modifier)
    (50_000, 0.5),        # < $50K: 更短寿命
    (500_000, 1.0),       # $50K - $500K: 标准
    (float('inf'), 1.5),  # > $500K: 更长寿命
]

# 热度增量
SIGNAL_HEAT_MAP = {
    SignalType.SIGNAL_5M: 10,
    SignalType.SIGNAL_20M: 30,
    SignalType.SIGNAL_1H: 50,
    SignalType.SIGNAL_4H: 80,
}

def _get_life_modifier(market_cap: float) -> float:
    """根据市值获取寿命修正系数"""
    for max_mc, life_mod in MARKET_CAP_MODIFIERS:
        if market_cap < max_mc:
            return life_mod
    return 1.0


def calculate_session_params(signal_type: SignalType, market_cap: float) -> tuple:
    """
    计算会话参数
    
    参数:
        signal_type: 信号类型
        market_cap: 当前市值
        
    返回:
        (poll_interval, life_add, heat_add)
    """
    base = SIGNAL_BASE_PARAMS.get(signal_type, {"life": 900})
    life_mod = _get_life_modifier(market_cap)
    
    poll_interval = UNIFIED_POLL_INTERVAL  # 统一 60 秒
    life_add = int(base["life"] * life_mod)
    heat_add = SIGNAL_HEAT_MAP.get(signal_type, 10)
    
    return poll_interval, life_add, heat_add


@dataclass
class SignalRecord:
    """信号记录"""
    signal_type: SignalType
    trigger_time: datetime
    trigger_value: float  # 涨幅
    price_at_trigger: float
    market_cap_at_trigger: float


@dataclass
class MonitoringSession:
    """
    监控会话
    
    每个代币在触发信号后创建一个会话，持续 API 追踪直到会话结束
    支持动态轮询间隔
    """
    token_id: int
    token_ca: str
    token_name: str
    token_href: str
    
    # 状态
    is_active: bool = True
    start_time: datetime = field(default_factory=datetime.now)
    last_update: datetime = field(default_factory=datetime.now)
    
    # 热度与寿命
    heat_score: float = 100.0
    remaining_life_seconds: int = 900  # 初始 15 分钟
    
    # 动态轮询参数
    poll_interval: int = 60  # 当前轮询间隔（秒）
    next_poll_time: datetime = field(default_factory=datetime.now)
    last_signal_type: SignalType = SignalType.SIGNAL_5M  # 最后一个信号类型
    
    # 信号历史
    signals: List[SignalRecord] = field(default_factory=list)
    
    # API 追踪数据（基于市值）
    initial_market_cap: float = 0.0
    current_market_cap: float = 0.0
    highest_market_cap: float = 0.0
    api_samples: List[Dict] = field(default_factory=list)
    
    # 计算属性
    @property
    def api_gain_5m(self) -> float:
        """计算 API 追踪期间的最大市值涨幅（相对于初始市值）"""
        if self.initial_market_cap <= 0:
            return 0.0
        return ((self.highest_market_cap - self.initial_market_cap) / self.initial_market_cap) * 100
    
    @property
    def current_gain(self) -> float:
        """当前市值涨幅"""
        if self.initial_market_cap <= 0:
            return 0.0
        return ((self.current_market_cap - self.initial_market_cap) / self.initial_market_cap) * 100
    
    def to_session_data(self) -> Dict[str, Any]:
        """转换为策略判断所需的数据格式"""
        return {
            "token_id": self.token_id,
            "token_ca": self.token_ca,
            "token_name": self.token_name,
            "heat_score": self.heat_score,
            "signals": [
                {"type": s.signal_type.value, "time": s.trigger_time, "value": s.trigger_value}
                for s in self.signals
            ],
            "api_gain_5m": self.api_gain_5m,
            "current_market_cap": self.current_market_cap,
            "initial_market_cap": self.initial_market_cap,
            "api_samples": self.api_samples,  # 暴露API历史数据
        }
    
    def update_with_signal(self, signal_type: SignalType, trigger_value: float,
                           price: float, market_cap: float):
        """
        添加信号并更新会话参数（动态调整轮询频率和寿命）
        """
        # 记录信号
        record = SignalRecord(
            signal_type=signal_type,
            trigger_time=datetime.now(),
            trigger_value=trigger_value,
            price_at_trigger=price,
            market_cap_at_trigger=market_cap,
        )
        self.signals.append(record)
        
        # 计算动态参数
        poll_interval, life_add, heat_add = calculate_session_params(signal_type, market_cap)
        
        # 更新轮询间隔（最新信号决定节奏）
        old_poll = self.poll_interval
        self.poll_interval = poll_interval
        self.last_signal_type = signal_type
        
        # 更新热度和寿命
        self.heat_score += heat_add
        self.remaining_life_seconds += life_add
        self.last_update = datetime.now()
        
        # 格式化市值
        if market_cap >= 1_000_000:
            mc_str = f"${market_cap/1_000_000:.2f}M"
        elif market_cap >= 1_000:
            mc_str = f"${market_cap/1_000:.1f}K"
        else:
            mc_str = f"${market_cap:.0f}"
        
        _logger.info(
            f"会话更新 [{self.token_name}]: +{signal_type.value} 信号 | "
            f"市值={mc_str} | 轮询={old_poll}s→{poll_interval}s | "
            f"热度={self.heat_score:.0f} | 剩余寿命={self.remaining_life_seconds//60}分钟"
        )
    
    # 向后兼容别名
    def add_signal(self, signal_type: SignalType, trigger_value: float,
                   price: float, market_cap: float):
        """添加信号（向后兼容，内部调用 update_with_signal）"""
        self.update_with_signal(signal_type, trigger_value, price, market_cap)


class SessionManager:
    """
    会话管理器
    
    - 独立线程运行，支持每个会话独立的轮询间隔
    - 调用 API 获取最新价格
    - 更新会话状态
    - 通知策略引擎进行交易决策
    """
    
    LOOP_INTERVAL = 5  # 主循环检查间隔（秒）
    
    def __init__(self, db: DatabaseManager, api: DexScreenerAPI,
                 on_session_update: Callable = None,
                 on_session_end: Callable = None,
                 on_poll_complete: Callable = None):
        """
        初始化会话管理器
        
        参数:
            db: 数据库管理器
            api: API 客户端
            on_session_update: 会话更新时的回调
            on_session_end: 会话结束时的回调
            on_poll_complete: 轮询完成时的回调（用于触发止盈止损）
        """
        self.db = db
        self.api = api
        self.on_session_update = on_session_update
        self.on_session_end = on_session_end
        self.on_poll_complete = on_poll_complete
        
        self._sessions: Dict[int, MonitoringSession] = {}  # token_id -> session
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._logger = logging.getLogger(__name__)
    
    def start(self):
        """启动会话管理器"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._logger.info("SessionManager 已启动 (动态轮询模式)")
    
    def stop(self):
        """停止会话管理器"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        self._logger.info("SessionManager 已停止")
    
    def _run_loop(self):
        """主循环 - 支持每个会话独立的轮询间隔"""
        while self._running:
            try:
                now = datetime.now()
                sessions_polled = []
                current_market_caps = {}
                
                with self._lock:
                    sessions_to_check = list(self._sessions.values())
                
                for session in sessions_to_check:
                    # 检查是否到达轮询时间
                    if now >= session.next_poll_time:
                        result = self._poll_single_session(session)
                        if result:
                            current_market_caps[session.token_id] = result
                            sessions_polled.append(session.token_name)
                        
                        # 更新下次轮询时间
                        session.next_poll_time = now + timedelta(seconds=session.poll_interval)
                        
                        # 减少寿命（按实际轮询间隔）
                        session.remaining_life_seconds -= session.poll_interval
                        
                        # 检查是否应该结束会话
                        if session.remaining_life_seconds <= 0:
                            self._end_session(session, "寿命耗尽")
                
                # 如果有会话被轮询，触发回调
                if sessions_polled and self.on_poll_complete and current_market_caps:
                    try:
                        self.on_poll_complete(current_market_caps)
                    except Exception as e:
                        self._logger.error(f"止盈止损检查失败: {e}", exc_info=True)
                
                # 如果有轮询发生，记录日志
                if sessions_polled:
                    self._logger.debug(f"[轮询] 本轮处理: {', '.join(sessions_polled)}")
                        
            except Exception as e:
                self._logger.error(f"会话轮询出错: {e}", exc_info=True)
            
            # 短间隔睡眠，以便及时检查各会话的轮询时间
            time.sleep(self.LOOP_INTERVAL)
    
    def _poll_single_session(self, session: MonitoringSession) -> Optional[float]:
        """
        轮询单个会话
        
        返回:
            当前市值，失败返回 None
        """
        try:
            # 从 href 检测链类型
            from core.api_client import DexScreenerAPI
            chain = DexScreenerAPI.detect_chain_from_href(session.token_href)
            
            # 获取原始 API 数据
            raw_data = self.api.get_token_data_raw(session.token_ca, chain=chain)
            if not raw_data or not isinstance(raw_data, list) or len(raw_data) == 0:
                self._logger.warning(f"  [{session.token_name}] API 返回空数据")
                return None
            
            main_pair = raw_data[0]
            
            # 保存原始数据到数据库（用于 ML 训练）
            self.db.insert_api_history(session.token_id, main_pair)
            
            # 获取市值
            market_cap = main_pair.get("marketCap", 0) or 0
            volume = main_pair.get("volume", {})
            volume_5m = volume.get("m5", 0) or 0
            
            if market_cap <= 0:
                return None
            
            old_mc = session.current_market_cap
            session.current_market_cap = market_cap
            
            # 计算市值变动
            mc_change = 0
            if old_mc > 0:
                mc_change = ((market_cap - old_mc) / old_mc) * 100
            
            # 更新最高市值
            is_new_high = False
            if market_cap > session.highest_market_cap:
                session.highest_market_cap = market_cap
                is_new_high = True
            
            # 记录样本
            session.api_samples.append({
                "time": datetime.now().isoformat(),
                "market_cap": market_cap,
                "volume_5m": volume_5m,
            })
            
            # 热度微调（市值上涨加热）
            if session.current_gain > 0:
                session.heat_score += 2
            
            session.last_update = datetime.now()
            
            # 格式化市值显示
            def fmt_mc(mc):
                if mc >= 1_000_000:
                    return f"${mc/1_000_000:.2f}M"
                elif mc >= 1_000:
                    return f"${mc/1_000:.1f}K"
                return f"${mc:.0f}"
            
            # 详细日志记录
            high_marker = " 📈新高" if is_new_high else ""
            self._logger.info(
                f"  [{session.token_name}] "
                f"市值={fmt_mc(market_cap)} ({mc_change:+.2f}%) | "
                f"涨幅={session.current_gain:.1f}% | "
                f"热度={session.heat_score:.0f} | "
                f"轮询={session.poll_interval}s | "
                f"剩余={session.remaining_life_seconds//60}分钟{high_marker}"
            )
            
            # 回调
            if self.on_session_update:
                self.on_session_update(session)
            
            return market_cap
                
        except Exception as e:
            self._logger.error(f"  [{session.token_name}] 轮询失败: {e}")
            return None
    
    def create_or_update_session(self, token_id: int, token_ca: str,
                                  token_name: str, token_href: str,
                                  signal_type: SignalType, trigger_value: float,
                                  price: float, market_cap: float) -> MonitoringSession:
        """创建或更新会话"""
        with self._lock:
            if token_id in self._sessions:
                # 更新现有会话
                session = self._sessions[token_id]
                session.update_with_signal(signal_type, trigger_value, price, market_cap)
            else:
                # 计算初始参数
                poll_interval, life_add, heat_add = calculate_session_params(signal_type, market_cap)
                
                # 创建新会话
                session = MonitoringSession(
                    token_id=token_id,
                    token_ca=token_ca,
                    token_name=token_name,
                    token_href=token_href,
                    initial_market_cap=market_cap,
                    current_market_cap=market_cap,
                    highest_market_cap=market_cap,
                    poll_interval=poll_interval,
                    next_poll_time=datetime.now() + timedelta(seconds=poll_interval),
                    last_signal_type=signal_type,
                    remaining_life_seconds=life_add,
                    heat_score=100.0 + heat_add,
                )
                
                # 记录首个信号
                record = SignalRecord(
                    signal_type=signal_type,
                    trigger_time=datetime.now(),
                    trigger_value=trigger_value,
                    price_at_trigger=price,
                    market_cap_at_trigger=market_cap,
                )
                session.signals.append(record)
                
                self._sessions[token_id] = session
                
                # 格式化市值显示
                if market_cap >= 1_000_000:
                    mc_str = f"${market_cap/1_000_000:.2f}M"
                elif market_cap >= 1_000:
                    mc_str = f"${market_cap/1_000:.1f}K"
                else:
                    mc_str = f"${market_cap:.0f}"
                
                self._logger.info(
                    f"🎯 新建会话 [{token_name}] ({signal_type.value}): "
                    f"市值={mc_str} | 轮询={poll_interval}s | "
                    f"热度={session.heat_score:.0f} | 寿命={life_add//60}分钟"
                )
            
            return session
    
    def _end_session(self, session: MonitoringSession, reason: str):
        """结束会话"""
        session.is_active = False
        
        with self._lock:
            if session.token_id in self._sessions:
                del self._sessions[session.token_id]
        
        self._logger.info(
            f"📋 会话结束 [{session.token_name}]: {reason}, "
            f"持续时间={(datetime.now() - session.start_time).seconds//60}分钟, "
            f"最终热度={session.heat_score:.0f}, 最大涨幅={session.api_gain_5m:.1f}%"
        )
        
        if self.on_session_end:
            self.on_session_end(session)
    
    def get_session(self, token_id: int) -> Optional[MonitoringSession]:
        """获取指定代币的会话"""
        with self._lock:
            return self._sessions.get(token_id)
    
    def get_all_sessions(self) -> List[MonitoringSession]:
        """获取所有活跃会话"""
        with self._lock:
            return list(self._sessions.values())
    
    def get_session_count(self) -> int:
        """获取活跃会话数量"""
        with self._lock:
            return len(self._sessions)
    
    def get_current_market_caps(self) -> Dict[int, float]:
        """获取所有会话的当前市值"""
        with self._lock:
            return {
                sid: s.current_market_cap
                for sid, s in self._sessions.items()
            }
