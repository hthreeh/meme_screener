"""
DEX 价格监控 - 智能信号引擎
信号触发、验证和过滤逻辑
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Callable
from pathlib import Path

from core.api_client import DexScreenerAPI
from core.database import DatabaseManager


_logger = logging.getLogger(__name__)


class SignalType(Enum):
    """信号类型"""
    PRICE_ALERT_5M = "5M_PRICE_ALERT"      # 5分钟价格预警
    PRICE_ALERT_1H = "1H_PRICE_ALERT"      # 1小时价格预警
    VOLUME_SPIKE = "VOLUME_SPIKE"           # 交易量激增
    WALLET_SURGE = "WALLET_SURGE"           # 钱包数激增


class SignalVerdict(Enum):
    """信号验证结果"""
    VALID = "VALID"             # 有效信号
    FALSE_SIGNAL = "FALSE"      # 虚假信号（可能是拉高出货）
    PENDING = "PENDING"         # 等待验证
    EXPIRED = "EXPIRED"         # 验证超时


@dataclass
class SignalValidationResult:
    """信号验证结果"""
    verdict: SignalVerdict
    reason: str
    price_trend: str            # 'UP', 'DOWN', 'STABLE'
    volume_trend: str           # 'INCREASING', 'DECREASING', 'STABLE'
    wallet_trend: str           # 'INCREASING', 'DECREASING', 'STABLE'
    confidence: float           # 0.0 - 1.0
    should_trade: bool          # 是否应该交易
    

class SignalEngine:
    """
    智能信号引擎
    
    负责：
    1. 信号触发后的快速数据采集（前5分钟每分钟一次）
    2. 多维度信号验证
    3. 虚假信号过滤
    """
    
    # 快速采集配置
    RAPID_COLLECT_MINUTES = 5       # 快速采集持续时间
    RAPID_COLLECT_INTERVAL = 60     # 采集间隔（秒）
    
    # 信号验证阈值
    PRICE_CONTINUE_THRESHOLD = 0.5   # 价格继续上涨阈值 %
    VOLUME_GROWTH_THRESHOLD = 10     # 交易量增长阈值 %
    WALLET_GROWTH_THRESHOLD = 5      # 钱包数增长阈值 %
    
    # 虚假信号检测
    DUMP_DETECTION_THRESHOLD = -10   # 大跌检测阈值 %
    BUY_SELL_RATIO_THRESHOLD = 0.7   # 买卖比例阈值（低于此值为卖压过大）
    
    def __init__(self, db: DatabaseManager, api: DexScreenerAPI = None):
        """
        初始化信号引擎
        
        参数:
            db: 数据库管理器
            api: API 客户端（可选，默认创建新实例）
        """
        self.db = db
        self.api = api or DexScreenerAPI()
        self._logger = logging.getLogger(__name__)
        self._active_validations = {}  # signal_id -> validation task
    
    def on_signal_triggered(self, token_id: int, token_ca: str,
                            signal_type: SignalType, trigger_value: float,
                            market_cap: float, price: float,
                            callback: Callable = None) -> int:
        """
        当信号触发时调用
        
        参数:
            token_id: 代币 ID
            token_ca: 代币 CA
            signal_type: 信号类型
            trigger_value: 触发值（如涨幅）
            market_cap: 触发时市值
            price: 触发时价格
            callback: 验证完成后的回调函数
            
        返回:
            信号事件 ID
        """
        # 创建信号事件记录
        signal_id = self.db.create_signal_event(
            token_id=token_id,
            signal_type=signal_type.value,
            trigger_value=trigger_value,
            market_cap=market_cap,
            price=price
        )
        
        self._logger.info(
            f"信号触发 #{signal_id}: {signal_type.value}, "
            f"涨幅={trigger_value:.1f}%, 价格=${price:.6f}"
        )
        
        # 启动快速采集和验证
        if token_ca and token_ca != "Unknown":
            self._start_rapid_collection(signal_id, token_ca, price, callback)
        else:
            self._logger.warning(f"信号 #{signal_id} 缺少 CA，跳过快速采集")
        
        return signal_id
    
    def _start_rapid_collection(self, signal_id: int, token_ca: str,
                                 initial_price: float, callback: Callable = None):
        """
        启动快速数据采集
        
        在独立线程中运行，每分钟采集一次数据
        """
        import threading
        
        def collect_loop():
            tracking_data = []
            
            for minute in range(self.RAPID_COLLECT_MINUTES):
                try:
                    # 等待采集间隔
                    if minute > 0:
                        time.sleep(self.RAPID_COLLECT_INTERVAL)
                    
                    # 获取 API 数据
                    data = self.api.get_signal_tracking_data(token_ca)
                    
                    if data:
                        # 计算价格变化
                        current_price = data.get('price', 0)
                        price_change = 0.0
                        if initial_price > 0 and current_price > 0:
                            price_change = ((current_price - initial_price) / initial_price) * 100
                        
                        data['price_change'] = price_change
                        
                        # 保存到数据库
                        self.db.add_signal_tracking(signal_id, data, minute)
                        tracking_data.append(data)
                        
                        self._logger.debug(
                            f"信号 #{signal_id} 采集 #{minute + 1}: "
                            f"价格=${current_price:.6f} ({price_change:+.2f}%)"
                        )
                    
                except Exception as e:
                    self._logger.error(f"快速采集出错: {e}")
            
            # 采集完成，进行验证
            result = self._validate_signal(signal_id, tracking_data, initial_price)
            
            # 更新数据库
            self.db.update_signal_validation(
                signal_id, 
                result.verdict == SignalVerdict.VALID,
                result.reason
            )
            
            # 回调通知
            if callback:
                try:
                    callback(signal_id, result)
                except Exception as e:
                    self._logger.error(f"回调执行出错: {e}")
            
            # 清理
            if signal_id in self._active_validations:
                del self._active_validations[signal_id]
        
        # 启动线程
        thread = threading.Thread(target=collect_loop, daemon=True)
        thread.start()
        self._active_validations[signal_id] = thread
    
    def _validate_signal(self, signal_id: int, tracking_data: List[Dict],
                          initial_price: float) -> SignalValidationResult:
        """
        验证信号有效性
        
        参数:
            signal_id: 信号 ID
            tracking_data: 采集的跟踪数据列表
            initial_price: 初始价格
            
        返回:
            验证结果
        """
        if not tracking_data or len(tracking_data) < 2:
            return SignalValidationResult(
                verdict=SignalVerdict.PENDING,
                reason="数据不足，无法验证",
                price_trend="UNKNOWN",
                volume_trend="UNKNOWN",
                wallet_trend="UNKNOWN",
                confidence=0.0,
                should_trade=False
            )
        
        # 分析价格趋势
        prices = [d.get('price', 0) for d in tracking_data if d.get('price', 0) > 0]
        price_trend = self._analyze_trend(prices)
        
        # 分析交易量趋势
        volumes = [d.get('volume_5m', 0) for d in tracking_data]
        volume_trend = self._analyze_trend(volumes)
        
        # 分析买卖比例
        total_buys = sum(d.get('txns_5m_buys', 0) for d in tracking_data)
        total_sells = sum(d.get('txns_5m_sells', 0) for d in tracking_data)
        
        # 检测虚假信号
        is_false_signal, false_reason = self._detect_false_signal(
            tracking_data, initial_price, total_buys, total_sells
        )
        
        if is_false_signal:
            return SignalValidationResult(
                verdict=SignalVerdict.FALSE_SIGNAL,
                reason=false_reason,
                price_trend=price_trend,
                volume_trend=volume_trend,
                wallet_trend="N/A",
                confidence=0.2,
                should_trade=False
            )
        
        # 计算信号有效性分数
        score = self._calculate_signal_score(
            tracking_data, price_trend, volume_trend, 
            total_buys, total_sells
        )
        
        # 判断是否应该交易
        should_trade = score >= 0.6 and price_trend == "UP"
        
        verdict = SignalVerdict.VALID if score >= 0.5 else SignalVerdict.FALSE_SIGNAL
        reason = self._generate_validation_reason(
            price_trend, volume_trend, score, total_buys, total_sells
        )
        
        return SignalValidationResult(
            verdict=verdict,
            reason=reason,
            price_trend=price_trend,
            volume_trend=volume_trend,
            wallet_trend="N/A",
            confidence=score,
            should_trade=should_trade
        )
    
    def _analyze_trend(self, values: List[float]) -> str:
        """分析数值趋势"""
        if not values or len(values) < 2:
            return "UNKNOWN"
        
        # 比较首尾
        first = values[0]
        last = values[-1]
        
        if first == 0:
            return "UNKNOWN"
        
        change = ((last - first) / first) * 100
        
        if change > 5:
            return "UP"
        elif change < -5:
            return "DOWN"
        else:
            return "STABLE"
    
    def _detect_false_signal(self, tracking_data: List[Dict], 
                              initial_price: float,
                              total_buys: int, total_sells: int) -> tuple:
        """
        检测虚假信号
        
        返回: (是否虚假信号, 原因)
        """
        if not tracking_data:
            return False, ""
        
        # 检测1: 价格快速下跌（可能是拉高出货）
        last_data = tracking_data[-1]
        current_price = last_data.get('price', 0)
        
        if initial_price > 0 and current_price > 0:
            price_change = ((current_price - initial_price) / initial_price) * 100
            if price_change < self.DUMP_DETECTION_THRESHOLD:
                return True, f"价格快速下跌 {price_change:.1f}%，疑似拉高出货"
        
        # 检测2: 卖压过大
        if total_buys + total_sells > 5:  # 至少有一定交易量
            buy_ratio = total_buys / (total_buys + total_sells)
            if buy_ratio < self.BUY_SELL_RATIO_THRESHOLD:
                return True, f"卖压过大，买入占比仅 {buy_ratio:.1%}"
        
        # 检测3: 交易量骤降
        if len(tracking_data) >= 3:
            volumes = [d.get('volume_5m', 0) for d in tracking_data]
            if volumes[0] > 0 and volumes[-1] > 0:
                volume_change = ((volumes[-1] - volumes[0]) / volumes[0]) * 100
                if volume_change < -50:
                    return True, f"交易量骤降 {volume_change:.1f}%"
        
        return False, ""
    
    def _calculate_signal_score(self, tracking_data: List[Dict],
                                  price_trend: str, volume_trend: str,
                                  total_buys: int, total_sells: int) -> float:
        """
        计算信号有效性分数（0.0-1.0）
        """
        score = 0.5  # 基础分
        
        # 价格趋势加分
        if price_trend == "UP":
            score += 0.2
        elif price_trend == "DOWN":
            score -= 0.2
        
        # 交易量趋势加分
        if volume_trend == "UP":
            score += 0.15
        elif volume_trend == "DOWN":
            score -= 0.1
        
        # 买卖比例加分
        total_txns = total_buys + total_sells
        if total_txns > 0:
            buy_ratio = total_buys / total_txns
            if buy_ratio > 0.6:
                score += 0.15
            elif buy_ratio > 0.5:
                score += 0.05
            elif buy_ratio < 0.4:
                score -= 0.15
        
        return max(0.0, min(1.0, score))
    
    def _generate_validation_reason(self, price_trend: str, volume_trend: str,
                                     score: float, total_buys: int, 
                                     total_sells: int) -> str:
        """生成验证结果说明"""
        parts = []
        
        trend_map = {"UP": "上涨", "DOWN": "下跌", "STABLE": "稳定", "UNKNOWN": "未知"}
        
        parts.append(f"价格趋势: {trend_map.get(price_trend, price_trend)}")
        parts.append(f"交易量趋势: {trend_map.get(volume_trend, volume_trend)}")
        
        if total_buys + total_sells > 0:
            buy_ratio = total_buys / (total_buys + total_sells)
            parts.append(f"买入占比: {buy_ratio:.1%}")
        
        parts.append(f"信号评分: {score:.2f}")
        
        return ", ".join(parts)
    
    def get_active_validations_count(self) -> int:
        """获取正在进行的验证数量"""
        return len(self._active_validations)
