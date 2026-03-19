"""
DEX 价格监控 - 持仓追踪器
独立于 Session 追踪所有策略的持仓，确保会话结束后仍能执行止盈止损

v3.1 新增模块
"""

import logging
import threading
import time
from typing import Dict, List, Callable, Optional

from core.api_client import DexScreenerAPI

_logger = logging.getLogger(__name__)
_positions_logger = logging.getLogger('positions')
_manual_logger = logging.getLogger('manual_trades')


class PositionTracker:
    """
    独立持仓追踪器
    
    - 从所有策略收集持仓
    - 独立线程轮询 API 获取市值
    - 触发止盈止损检查
    - 不依赖 Session 生命周期
    """
    
    POLL_INTERVAL = 60  # 轮询间隔（秒）
    
    def __init__(self, strategies: Dict, api: DexScreenerAPI,
                 db=None, on_exit_callback: Callable = None, settings=None):
        """
        初始化持仓追踪器
        
        参数:
            strategies: 策略字典 {StrategyType -> TradingStrategy}
            api: API 客户端
            db: 数据库管理器（用于缓存市值数据）
            on_exit_callback: 止盈止损触发时的回调函数
            settings: 应用配置 (AppSettings)
        """
        self.strategies = strategies
        self.api = api
        self.db = db
        self.on_exit_callback = on_exit_callback
        self.settings = settings  # 保存配置
        
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._chain_cache = {}  # 缓存 token_id -> chain
    
    def start(self):
        """启动持仓追踪器"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        _logger.info("PositionTracker 已启动")
    
    def stop(self):
        """停止持仓追踪器"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        _logger.info("PositionTracker 已停止")
    
    def _run_loop(self):
        """主循环"""
        while self._running:
            try:
                start_time = time.time()
                
                # 轮询持仓 (耗时操作)
                self._poll_all_positions()
                
                # 计算需要等待的时间
                elapsed = time.time() - start_time
                wait_time = max(0, self.POLL_INTERVAL - elapsed)
                
                # 等待期间每秒检查一次手动订单
                steps = int(wait_time)
                for _ in range(steps):
                    if not self._running:
                        break
                    
                    # 快速处理手动买入订单
                    self._process_manual_orders()
                    # 快速处理手动卖出订单
                    self._process_manual_sell_orders()
                    time.sleep(1)
                    
            except Exception as e:
                _logger.error(f"持仓轮询出错: {e}", exc_info=True)
                time.sleep(5)  # 出错后短暂等待
    
    def _get_chain_for_token(self, token_id: int) -> str:
        """获取代币的链类型（带缓存）"""
        if token_id in self._chain_cache:
            return self._chain_cache[token_id]
        
        chain = "solana"  # 默认
        if self.db:
            try:
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT href FROM tokens WHERE id = ?", (token_id,))
                    row = cursor.fetchone()
                    if row and row['href']:
                        chain = DexScreenerAPI.detect_chain_from_href(row['href'])
            except Exception:
                pass
        
        self._chain_cache[token_id] = chain
        return chain

    def _poll_all_positions(self):
        """轮询所有持仓的市值"""
        # 1. 收集所有策略的持仓
        all_positions = self._collect_all_positions()
        
        if not all_positions:
            return
        
        _logger.debug(f"[持仓追踪] 开始轮询 {len(all_positions)} 个持仓...")
        
        # 2. 获取所有持仓的当前市值
        current_market_caps = {}
        for token_id, position in all_positions.items():
            try:
                # 获取链类型并请求数据
                chain = self._get_chain_for_token(token_id)
                token_data = self.api.get_token_data_raw(position.token_ca, chain=chain)
                if token_data and isinstance(token_data, list) and len(token_data) > 0:
                    market_cap = token_data[0].get("marketCap", 0)
                    if market_cap > 0:
                        current_market_caps[token_id] = market_cap
                        
                        # 记录持仓状态到日志
                        multiplier = position.get_market_cap_multiplier(market_cap)
                        pnl_percent = (multiplier - 1) * 100
                        
                        # 格式化市值
                        if market_cap >= 1_000_000:
                            mc_str = f"${market_cap/1_000_000:.2f}M"
                        elif market_cap >= 1_000:
                            mc_str = f"${market_cap/1_000:.1f}K"
                        else:
                            mc_str = f"${market_cap:.0f}"
                        
                        buy_mc = position.buy_market_cap
                        if buy_mc >= 1_000_000:
                            buy_mc_str = f"${buy_mc/1_000_000:.2f}M"
                        elif buy_mc >= 1_000:
                            buy_mc_str = f"${buy_mc/1_000:.1f}K"
                        else:
                            buy_mc_str = f"${buy_mc:.0f}"
                        
                        _positions_logger.info(
                            f"策略{position.strategy.value} | {position.token_name} | "
                            f"持仓={position.remaining_ratio*100:.0f}% | "
                            f"买入市值={buy_mc_str} | 当前={mc_str} | "
                            f"{pnl_percent:+.1f}%"
                        )
                        
                        # 缓存市值到数据库（供前端查询）
                        if self.db:
                            try:
                                # 1. 更新最新缓存
                                self.db.cache_api_data(position.token_ca, {
                                    'market_cap': market_cap,
                                    'price_usd': token_data[0].get('priceUsd'),
                                    'price_native': token_data[0].get('priceNative'),
                                    'liquidity_usd': token_data[0].get('liquidity', {}).get('usd'),
                                })
                                
                                # 2. 插入历史记录 (修复持仓代币历史数据中断问题)
                                self.db.insert_api_history(position.token_id, token_data[0])
                                
                            except Exception as cache_err:
                                _logger.debug(f"保存API数据失败: {cache_err}")
            except Exception as e:
                _logger.debug(f"获取 {position.token_name} 市值失败: {e}")
        
        if not current_market_caps:
            return
        
        _logger.info(f"[持仓追踪] 获取到 {len(current_market_caps)}/{len(all_positions)} 个持仓市值")
        
        # 3. 检查止盈止损（传递配置参数）
        # 从 settings 读取分段止损和趋势延期配置
        ssl_enabled = True
        ssl_level_1 = (-0.15, 0.5)
        ssl_level_2 = (-0.30, 1.0)
        te_enabled = False
        te_threshold = 0.10
        te_minutes = 30
        te_max_times = 2
        
        if self.settings:
            if hasattr(self.settings, 'staged_stop_loss') and self.settings.staged_stop_loss:
                ssl = self.settings.staged_stop_loss
                ssl_enabled = ssl.enabled
                ssl_level_1 = (ssl.level_1.trigger, ssl.level_1.sell_ratio)
                ssl_level_2 = (ssl.level_2.trigger, ssl.level_2.sell_ratio)
            if hasattr(self.settings, 'trend_extension') and self.settings.trend_extension:
                te = self.settings.trend_extension
                te_enabled = te.enabled
                te_threshold = te.threshold
                te_minutes = te.extension_minutes
                te_max_times = te.max_times
        
        for st_type, strategy in self.strategies.items():
            try:
                results = strategy.check_and_execute_exits(
                    current_market_caps,
                    staged_stop_loss_enabled=ssl_enabled,
                    staged_stop_loss_level_1=ssl_level_1,
                    staged_stop_loss_level_2=ssl_level_2,
                    trend_extension_enabled=te_enabled,
                    trend_extension_threshold=te_threshold,
                    trend_extension_minutes=te_minutes,
                    trend_extension_max_times=te_max_times
                )
                if results and self.on_exit_callback:
                    for result in results:
                        self.on_exit_callback(st_type, result)
            except Exception as e:
                _logger.error(f"策略{st_type.value}止盈止损检查失败: {e}")
    
    def _collect_all_positions(self) -> Dict[int, any]:
        """收集所有策略的持仓"""
        all_positions = {}
        
        for st_type, strategy in self.strategies.items():
            with strategy._lock:
                for token_id, position in strategy.state.positions.items():
                    # 用 token_id 作为键，避免重复
                    if token_id not in all_positions:
                        all_positions[token_id] = position
        
        return all_positions
    
    def get_position_count(self) -> int:
        """获取当前持仓总数"""
        return len(self._collect_all_positions())
    
    def _process_manual_orders(self):
        """检查并处理手动买入订单"""
        if not self.db:
            return
        
        # 获取手动策略
        from services.trading_strategies import StrategyType
        manual_strategy = self.strategies.get(StrategyType.MANUAL)
        if not manual_strategy:
            return
        
        # 获取待处理订单
        try:
            orders = self.db.get_pending_manual_orders()
        except Exception as e:
            # 避免日志刷新过快，仅debug记录
            return
        
        if not orders:
            return
        
        # 获取当前账户状态
        import json
        
        for order in orders:
            order_id = order['id']
            token_ca = order['token_ca']
            amount_sol = order['amount_sol']
            
            _manual_logger.info(f"开始处理手动订单 #{order_id}: CA={token_ca}, Amount={amount_sol} SOL")
            
            try:
                # 获取代币数据
                token_data = self.api.get_token_data_raw(token_ca)
                
                if not token_data or not isinstance(token_data, list) or len(token_data) == 0:
                    self.db.mark_manual_order_failed(order_id, "无法获取代币数据")
                    _manual_logger.error(f"订单 #{order_id} 失败: API未返回代币数据")
                    continue
                
                # 执行买入
                position = manual_strategy.manual_buy(
                    token_ca=token_ca,
                    amount_sol=amount_sol,
                    token_data=token_data[0]
                )
                
                if position:
                    # 获取最新账户余额
                    account_state = self.db.get_account_state()
                    balance = account_state['balance_sol'] if account_state else 0.0
                    
                    # 构建结果信息
                    result_info = json.dumps({
                        "token_name": position.token_name,
                        "buy_price": position.buy_market_cap,
                        "buy_amount": position.buy_amount_sol,
                        "balance_after": balance
                    })
                    
                    self.db.mark_manual_order_done(order_id, result_info)
                    
                    _manual_logger.info(
                        f"✅ 订单 #{order_id} 成功: "
                        f"{position.token_name} | 市值 ${position.buy_market_cap:,.0f} | "
                        f"投入 {position.buy_amount_sol:.2f} SOL | 余额 {balance:.2f} SOL"
                    )
                else:
                    self.db.mark_manual_order_failed(order_id, "买入失败 (余额不足或已持有)")
                    _manual_logger.warning(f"订单 #{order_id} 失败: 买入返回 None (可能余额不足或已持仓)")
                    
            except Exception as e:
                error_msg = str(e)
                self.db.mark_manual_order_failed(order_id, error_msg[:200])
                _manual_logger.error(f"订单 #{order_id} 异常: {error_msg}", exc_info=True)

    def _process_manual_sell_orders(self):
        """检查并处理手动卖出订单"""
        if not self.db:
            return
        
        # 获取待处理的卖出订单
        try:
            orders = self.db.get_pending_manual_sell_orders()
        except Exception:
            return
        
        if not orders:
            return
        
        import json
        from services.trading_strategies import StrategyType
        
        for order in orders:
            order_id = order['id']
            strategy_type_str = order['strategy_type']
            token_id = order['token_id']
            
            _manual_logger.info(f"开始处理手动卖出订单 #{order_id}: 策略={strategy_type_str}, TokenID={token_id}")
            
            try:
                # 查找对应策略
                strategy_type = None
                for st in StrategyType:
                    if st.value == strategy_type_str:
                        strategy_type = st
                        break
                
                if strategy_type is None or strategy_type not in self.strategies:
                    self.db.mark_manual_sell_order_failed(order_id, f"无效的策略类型: {strategy_type_str}")
                    _manual_logger.error(f"订单 #{order_id} 失败: 无效的策略类型 {strategy_type_str}")
                    continue
                
                strategy = self.strategies[strategy_type]
                
                # 检查持仓是否存在
                if token_id not in strategy.state.positions:
                    self.db.mark_manual_sell_order_failed(order_id, "持仓不存在")
                    _manual_logger.error(f"订单 #{order_id} 失败: 持仓不存在")
                    continue
                
                position = strategy.state.positions[token_id]
                
                # 获取当前市值
                chain = self._get_chain_for_token(token_id)
                token_data = self.api.get_token_data_raw(position.token_ca, chain=chain)
                
                if not token_data or not isinstance(token_data, list) or len(token_data) == 0:
                    self.db.mark_manual_sell_order_failed(order_id, "无法获取代币数据")
                    _manual_logger.error(f"订单 #{order_id} 失败: API未返回代币数据")
                    continue
                
                current_market_cap = token_data[0].get("marketCap", 0) or 0
                if current_market_cap <= 0:
                    self.db.mark_manual_sell_order_failed(order_id, "无法获取有效市值")
                    _manual_logger.error(f"订单 #{order_id} 失败: 市值为0")
                    continue
                
                # 执行卖出
                result = strategy.manual_sell(token_id, current_market_cap)
                
                if result:
                    # 构建结果信息
                    result_info = json.dumps({
                        "token_name": result.get("token_name"),
                        "sell_price": result.get("sell_market_cap"),
                        "sell_amount": result.get("sell_value"),
                        "pnl": result.get("pnl"),
                        "pnl_percent": result.get("pnl_percent"),
                        "balance_after": result.get("balance_after")
                    })
                    
                    self.db.mark_manual_sell_order_done(order_id, result_info)
                    
                    _manual_logger.info(
                        f"✅ 卖出订单 #{order_id} 成功: "
                        f"{result.get('token_name')} | 市值 ${current_market_cap:,.0f} | "
                        f"PNL {result.get('pnl', 0):+.4f} SOL ({result.get('pnl_percent', 0):+.1f}%) | "
                        f"余额 {result.get('balance_after', 0):.2f} SOL"
                    )
                else:
                    self.db.mark_manual_sell_order_failed(order_id, "卖出失败")
                    _manual_logger.warning(f"订单 #{order_id} 失败: manual_sell 返回 None")
                    
            except Exception as e:
                error_msg = str(e)
                self.db.mark_manual_sell_order_failed(order_id, error_msg[:200])
                _manual_logger.error(f"卖出订单 #{order_id} 异常: {error_msg}", exc_info=True)

