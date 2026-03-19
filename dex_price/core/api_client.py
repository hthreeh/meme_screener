"""
DEX 价格监控 - DexScreener API 客户端
获取代币详细数据
"""

import json
import logging
import time
import random
import threading
from collections import deque
from typing import Dict, List, Optional, Any, Tuple
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

_logger = logging.getLogger(__name__)


class APIRateLimiter:
    """
    API 速率限制器 - 滑动窗口算法
    
    限制 API 请求频率，防止超过限制（默认：300次/分钟）
    """
    
    def __init__(self, max_requests: int = 300, window_seconds: int = 60):
        """
        初始化速率限制器
        
        参数:
            max_requests: 窗口内最大请求数（默认 300）
            window_seconds: 时间窗口大小，秒（默认 60）
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: deque = deque()
        self._lock = threading.Lock()
        
        # 统计
        self._total_requests = 0
        self._throttled_count = 0
        self._logger = logging.getLogger(__name__)
    
    def wait_for_slot(self) -> float:
        """
        等待可用的请求槽位
        
        返回：等待时间（秒），0 表示无需等待
        """
        wait_time = 0.0
        
        with self._lock:
            now = time.time()
            
            # 清理过期记录（超出窗口的请求）
            while self._requests and now - self._requests[0] > self.window_seconds:
                self._requests.popleft()
            
            # 检查是否达到限制
            if len(self._requests) >= self.max_requests:
                # 计算需要等待的时间
                wait_time = self._requests[0] + self.window_seconds - now + 0.1
                self._throttled_count += 1
                self._logger.warning(
                    f"[限流] 达到速率限制 ({self.max_requests}/{self.window_seconds}s)，"
                    f"等待 {wait_time:.1f}s"
                )
        
        # 在锁外等待
        if wait_time > 0:
            time.sleep(wait_time)
            
            # 等待后重新清理
            with self._lock:
                now = time.time()
                while self._requests and now - self._requests[0] > self.window_seconds:
                    self._requests.popleft()
                self._requests.append(now)
                self._total_requests += 1
        else:
            with self._lock:
                self._requests.append(time.time())
                self._total_requests += 1
        
        return wait_time
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        with self._lock:
            return {
                "total_requests": self._total_requests,
                "throttled_count": self._throttled_count,
                "current_window_count": len(self._requests),
                "remaining_slots": max(0, self.max_requests - len(self._requests)),
            }


# 全局限流器实例（所有 API 客户端共享）
_global_rate_limiter = APIRateLimiter(max_requests=300, window_seconds=60)


class DexScreenerAPI:
    """
    DexScreener API 客户端
    
    获取代币交易对数据、价格、交易量等信息
    支持多链：Solana, BSC 等
    """
    
    BASE_URL = "https://api.dexscreener.com"
    
    # 支持的链及其 API 路径
    SUPPORTED_CHAINS = {
        "solana": "solana",
        "bsc": "bsc",
        "ethereum": "ethereum",
        "base": "base",
        "arbitrum": "arbitrum",
    }
    DEFAULT_CHAIN = "solana"
    
    # 请求配置
    TIMEOUT = 30
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    MAX_RETRIES = 3  # 最大重试次数
    
    def __init__(self):
        self._logger = logging.getLogger(__name__)
        self._rate_limiter = _global_rate_limiter  # 使用全局限流器
    
    def get_rate_limit_stats(self) -> dict:
        """获取 API 限流统计信息"""
        return self._rate_limiter.get_stats()
    
    @staticmethod
    def detect_chain_from_href(href: str) -> str:
        """
        从 href 路径中检测链类型
        
        示例:
            /solana/0x123... -> solana
            /bsc/0x123... -> bsc
        """
        if not href:
            return DexScreenerAPI.DEFAULT_CHAIN
        
        # 移除开头的斜杠并分割
        parts = href.strip("/").split("/")
        if len(parts) >= 1:
            chain = parts[0].lower()
            if chain in DexScreenerAPI.SUPPORTED_CHAINS:
                return chain
        
        return DexScreenerAPI.DEFAULT_CHAIN
    
    def _get_token_endpoint(self, chain: str) -> str:
        """获取指定链的 token API 端点"""
        chain_path = self.SUPPORTED_CHAINS.get(chain, self.DEFAULT_CHAIN)
        return f"/tokens/v1/{chain_path}"
    
    def _get_pair_endpoint(self, chain: str) -> str:
        """获取指定链的 pair API 端点"""
        chain_path = self.SUPPORTED_CHAINS.get(chain, self.DEFAULT_CHAIN)
        return f"/latest/dex/pairs/{chain_path}"
    
    def _make_request_with_retry(self, url: str) -> Optional[Dict]:
        """带重试机制和速率限制的通用请求方法"""
        for attempt in range(self.MAX_RETRIES):
            try:
                # 限流检查 - 确保不超过速率限制
                self._rate_limiter.wait_for_slot()
                
                self._logger.debug(f"请求 API: {url} (尝试 {attempt+1}/{self.MAX_RETRIES})")
                
                request = Request(url)
                request.add_header("User-Agent", self.USER_AGENT)
                
                with urlopen(request, timeout=self.TIMEOUT) as response:
                    return json.loads(response.read().decode('utf-8'))
                    
            except HTTPError as e:
                self._logger.error(f"API HTTP 错误 {e.code}: {url}")
                # 429 Too Many Requests 需要等待更久
                if e.code == 429:
                    time.sleep(5 + attempt * 2)
                    continue
                return None
            except URLError as e:
                self._logger.warning(f"API 网络错误 (尝试 {attempt+1}): {e.reason}")
                # 随机延迟重试
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(1 + random.random() * 2)
                    continue
                return None
            except Exception as e:
                self._logger.error(f"API 请求失败: {e}", exc_info=True)
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(1)
                    continue
                return None
        return None

    def get_token_ca_from_pair(self, pair_address: str, chain: str = "solana") -> Tuple[Optional[str], Optional[Dict]]:
        """
        通过交易对地址获取代币的合约地址和原始数据
        
        参数:
            pair_address: 交易对地址
            chain: 链类型
            
        返回:
            (ca, pair_data) 元组
        """
        endpoint = self._get_pair_endpoint(chain)
        url = f"{self.BASE_URL}{endpoint}/{pair_address}"
        
        data = self._make_request_with_retry(url)
        if not data:
            return None, None
            
        try:
            # API 可能返回 "pair" 或 "pairs" 格式
            pair = data.get("pair")
            if not pair and data.get("pairs"):
                pair = data["pairs"][0] if data["pairs"] else None
            
            if pair:
                base_token = pair.get("baseToken", {})
                token_ca = base_token.get("address", "")
                if token_ca:
                    self._logger.info(f"成功获取 token CA: {token_ca[:20]}...")
                    return token_ca, pair
            
            self._logger.warning(f"无法从 API 响应中提取 CA: {pair_address}")
            return None, None
            
        except Exception as e:
            self._logger.error(f"解析 CA 数据失败: {e}")
            return None, None
    
    def get_token_data(self, ca: str, chain: str = "solana") -> Optional[Dict[str, Any]]:
        """
        获取代币的交易对数据
        
        参数:
            ca: 代币合约地址
            chain: 链类型 (solana, bsc, etc.)
            
        返回:
            主交易对数据字典，失败返回 None
        """
        endpoint = self._get_token_endpoint(chain)
        url = f"{self.BASE_URL}{endpoint}/{ca}"
        
        try:
            data = self._make_request_with_retry(url)
                
            if not data or not isinstance(data, list):
                # DexScreener 现在的 API 格式好像变了，有时候返回 {"schemaVersion": "1.0.0", "pairs": [...]}
                # 我们检查是否是列表，或者是否包含 pairs 键
                if isinstance(data, dict) and "pairs" in data:
                    pairs = data["pairs"]
                    if not pairs:
                        self._logger.warning(f"API 返回空 pairs: {ca}")
                        return None
                    main_pair = pairs[0]
                    return self._parse_pair_data(main_pair)
                
                self._logger.warning(f"API 返回数据格式不符: {ca}")
                return None
            
            # 兼容旧列表格式
            main_pair = data[0]
            
            # 解析并返回标准化数据
            return self._parse_pair_data(main_pair)
            
        except Exception as e:
            self._logger.error(f"处理代币数据失败: {e}")
            return None
    
    def get_token_data_raw(self, ca: str, chain: str = "solana") -> Optional[List[Dict]]:
        """
        获取代币的原始 API 数据（所有交易对）
        
        参数:
            ca: 代币合约地址
            chain: 链类型 (solana, bsc, etc.)
        """
        endpoint = self._get_token_endpoint(chain)
        url = f"{self.BASE_URL}{endpoint}/{ca}"
        return self._make_request_with_retry(url)
    
    def _parse_pair_data(self, pair: Dict) -> Dict[str, Any]:
        """
        解析交易对数据为标准格式
        
        参数:
            pair: 原始交易对数据
            
        返回:
            标准化的数据字典
        """
        # 基础信息
        base_token = pair.get("baseToken", {})
        
        # 交易统计
        txns = pair.get("txns", {})
        txns_m5 = txns.get("m5", {})
        txns_h1 = txns.get("h1", {})
        txns_h6 = txns.get("h6", {})
        txns_h24 = txns.get("h24", {})
        
        # 交易量
        volume = pair.get("volume", {})
        
        # 价格变化
        price_change = pair.get("priceChange", {})
        
        # 流动性
        liquidity = pair.get("liquidity", {})
        
        return {
            # 代币信息
            "ca": base_token.get("address", ""),
            "name": base_token.get("name", ""),
            "symbol": base_token.get("symbol", ""),
            
            # 价格信息
            "price_usd": self._safe_float(pair.get("priceUsd")),
            "price_native": self._safe_float(pair.get("priceNative")),
            
            # 5分钟交易
            "txns_m5_buys": txns_m5.get("buys", 0),
            "txns_m5_sells": txns_m5.get("sells", 0),
            
            # 1小时交易
            "txns_h1_buys": txns_h1.get("buys", 0),
            "txns_h1_sells": txns_h1.get("sells", 0),
            
            # 6小时交易
            "txns_h6_buys": txns_h6.get("buys", 0),
            "txns_h6_sells": txns_h6.get("sells", 0),
            
            # 24小时交易
            "txns_h24_buys": txns_h24.get("buys", 0),
            "txns_h24_sells": txns_h24.get("sells", 0),
            
            # 交易量
            "volume_m5": volume.get("m5", 0.0),
            "volume_h1": volume.get("h1", 0.0),
            "volume_h6": volume.get("h6", 0.0),
            "volume_h24": volume.get("h24", 0.0),
            
            # 价格变化
            "price_change_m5": price_change.get("m5", 0.0),
            "price_change_h1": price_change.get("h1", 0.0),
            "price_change_h6": price_change.get("h6", 0.0),
            "price_change_h24": price_change.get("h24", 0.0),
            
            # 流动性和市值
            "liquidity_usd": liquidity.get("usd", 0.0),
            "fdv": pair.get("fdv", 0),
            "market_cap": pair.get("marketCap", 0),
            
            # 交易对信息
            "pair_address": pair.get("pairAddress", ""),
            "dex_id": pair.get("dexId", ""),
            "pair_created_at": pair.get("pairCreatedAt", 0),
        }
    
    def _safe_float(self, value) -> float:
        """安全转换为浮点数"""
        if value is None:
            return 0.0
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0
    
    def get_signal_tracking_data(self, ca: str) -> Optional[Dict[str, Any]]:
        """
        获取用于信号跟踪的简化数据
        
        专为信号触发后的快速采集设计
        
        参数:
            ca: 代币合约地址
            
        返回:
            跟踪所需的关键数据
        """
        data = self.get_token_data(ca)
        if not data:
            return None
        
        return {
            "price": data["price_usd"],
            "volume_5m": data["volume_m5"],
            "txns_5m_buys": data["txns_m5_buys"],
            "txns_5m_sells": data["txns_m5_sells"],
            "liquidity": data["liquidity_usd"],
            "market_cap": data["market_cap"],
            "price_change_m5": data["price_change_m5"],
        }
