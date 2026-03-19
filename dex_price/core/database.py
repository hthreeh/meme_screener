"""
DEX 价格监控 - SQLite 数据库管理模块
处理所有数据持久化操作
"""

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    SQLite 数据库管理器

    管理代币数据、价格快照、信号事件、模拟交易等数据的存储
    """

    def __init__(self, db_path: Path):
        """
        初始化数据库管理器

        参数:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self._logger = logging.getLogger(__name__)
        
        # 确保父目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化数据库表
        self._init_tables()
        self._logger.info(f"数据库初始化完成: {self.db_path}")

    @contextmanager
    def get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            self._logger.error(f"数据库操作失败: {e}")
            raise
        finally:
            conn.close()

    def _init_tables(self) -> None:
        """初始化所有数据库表"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 代币基础信息表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ca TEXT UNIQUE,
                    href TEXT UNIQUE NOT NULL,
                    name TEXT,
                    symbol TEXT,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 价格快照表 (5分钟周期)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS price_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token_id INTEGER NOT NULL,
                    price REAL,
                    market_cap REAL,
                    market_cap_str TEXT,
                    liquidity REAL,
                    liquidity_str TEXT,
                    volume_24h REAL,
                    volume_24h_str TEXT,
                    txns_24h INTEGER,
                    makers_24h INTEGER,
                    pair_age TEXT,
                    growth_5m REAL DEFAULT 0.0,
                    growth_1h REAL DEFAULT 0.0,
                    growth_6h REAL DEFAULT 0.0,
                    growth_24h REAL DEFAULT 0.0,
                    source_file TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (token_id) REFERENCES tokens(id)
                )
            """)
            
            # 信号事件表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signal_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token_id INTEGER NOT NULL,
                    signal_type TEXT NOT NULL,
                    trigger_value REAL,
                    market_cap_at_trigger REAL,
                    price_at_trigger REAL,
                    is_validated INTEGER DEFAULT 0,
                    validation_result TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (token_id) REFERENCES tokens(id)
                )
            """)
            
            # 信号跟踪表 (信号触发后的快速采集)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signal_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_event_id INTEGER NOT NULL,
                    price REAL,
                    price_change_from_trigger REAL,
                    volume_5m REAL,
                    txns_5m_buys INTEGER,
                    txns_5m_sells INTEGER,
                    liquidity REAL,
                    market_cap REAL,
                    minute_offset INTEGER,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (signal_event_id) REFERENCES signal_events(id)
                )
            """)
            
            # 模拟交易表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS simulated_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token_id INTEGER NOT NULL,
                    signal_event_id INTEGER,
                    action TEXT CHECK(action IN ('BUY', 'SELL')) NOT NULL,
                    amount_sol REAL DEFAULT 0.1,
                    price_at_trade REAL NOT NULL,
                    token_amount REAL,
                    fee_percent REAL DEFAULT 3.0,
                    fee_sol REAL,
                    pnl_sol REAL,
                    pnl_percent REAL,
                    balance_after REAL,
                    notes TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (token_id) REFERENCES tokens(id),
                    FOREIGN KEY (signal_event_id) REFERENCES signal_events(id)
                )
            """)
            
            # 模拟账户状态表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS account_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    balance_sol REAL DEFAULT 100.0,
                    total_trades INTEGER DEFAULT 0,
                    winning_trades INTEGER DEFAULT 0,
                    losing_trades INTEGER DEFAULT 0,
                    total_pnl REAL DEFAULT 0.0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 策略状态表 - 各策略的余额和统计数据
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS strategy_states (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_type TEXT UNIQUE NOT NULL,
                    balance_sol REAL NOT NULL,
                    total_trades INTEGER DEFAULT 0,
                    winning_trades INTEGER DEFAULT 0,
                    losing_trades INTEGER DEFAULT 0,
                    total_pnl REAL DEFAULT 0.0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 策略持仓表 - 各策略的持仓信息
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS strategy_positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_type TEXT NOT NULL,
                    token_id INTEGER NOT NULL,
                    token_ca TEXT NOT NULL,
                    token_name TEXT,
                    buy_market_cap REAL NOT NULL,
                    buy_amount_sol REAL NOT NULL,
                    buy_time TIMESTAMP NOT NULL,
                    remaining_ratio REAL DEFAULT 1.0,
                    highest_multiplier REAL DEFAULT 1.0,
                    take_profit_level INTEGER DEFAULT 0,
                    poll_count INTEGER DEFAULT 0,
                    loss_check_count INTEGER DEFAULT 0,
                    trailing_stop_multiplier REAL DEFAULT 0.7,
                    FOREIGN KEY (token_id) REFERENCES tokens(id),
                    UNIQUE(strategy_type, token_id)
                )
            """)
            
            # API 数据缓存表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_data_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token_ca TEXT NOT NULL,
                    price_usd REAL,
                    price_native REAL,
                    txns_m5_buys INTEGER,
                    txns_m5_sells INTEGER,
                    txns_h1_buys INTEGER,
                    txns_h1_sells INTEGER,
                    txns_h24_buys INTEGER,
                    txns_h24_sells INTEGER,
                    volume_m5 REAL,
                    volume_h1 REAL,
                    volume_h6 REAL,
                    volume_h24 REAL,
                    price_change_m5 REAL,
                    price_change_h1 REAL,
                    price_change_h6 REAL,
                    price_change_h24 REAL,
                    liquidity_usd REAL,
                    fdv REAL,
                    market_cap REAL,
                    pair_created_at INTEGER,
                    raw_json TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # API 历史数据表 (用于 ML 训练，永久保存)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token_id INTEGER NOT NULL,
                    token_address TEXT NOT NULL,
                    token_name TEXT,
                    token_symbol TEXT,
                    
                    -- 价格数据
                    price_usd REAL,
                    
                    -- 交易笔数
                    txns_m5_buys INTEGER DEFAULT 0,
                    txns_m5_sells INTEGER DEFAULT 0,
                    txns_h1_buys INTEGER DEFAULT 0,
                    txns_h1_sells INTEGER DEFAULT 0,
                    txns_h6_buys INTEGER DEFAULT 0,
                    txns_h6_sells INTEGER DEFAULT 0,
                    txns_h24_buys INTEGER DEFAULT 0,
                    txns_h24_sells INTEGER DEFAULT 0,
                    
                    -- 成交量
                    volume_m5 REAL DEFAULT 0,
                    volume_h1 REAL DEFAULT 0,
                    volume_h6 REAL DEFAULT 0,
                    volume_h24 REAL DEFAULT 0,
                    
                    -- 价格变化 (%)
                    price_change_h1 REAL DEFAULT 0,
                    price_change_h6 REAL DEFAULT 0,
                    price_change_h24 REAL DEFAULT 0,
                    
                    -- 流动性和市值
                    liquidity_usd REAL DEFAULT 0,
                    market_cap REAL DEFAULT 0,
                    
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (token_id) REFERENCES tokens(id)
                )
            """)
            
            # 手动买入队列表 (用于 Web 手动下单)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS manual_buy_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token_ca TEXT NOT NULL,
                    amount_sol REAL DEFAULT 0.2,
                    status TEXT DEFAULT 'PENDING',
                    error_msg TEXT,
                    result_info TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP
                )
            """)
            
            # 手动卖出队列表 (用于 Web 手动平仓)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS manual_sell_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_type TEXT NOT NULL,
                    token_id INTEGER NOT NULL,
                    status TEXT DEFAULT 'PENDING',
                    error_msg TEXT,
                    result_info TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP
                )
            """)
            
            # 创建索引以提高查询性能
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tokens_ca ON tokens(ca)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tokens_href ON tokens(href)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_token_time ON price_snapshots(token_id, timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_token ON signal_events(token_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_token ON simulated_trades(token_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_cache_ca ON api_data_cache(token_ca)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_history_token_time ON api_history(token_id, timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_history_address ON api_history(token_address)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_manual_queue_status ON manual_buy_queue(status)")
            
            # 初始化账户状态 (如果不存在)
            cursor.execute("SELECT COUNT(*) FROM account_state")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO account_state (balance_sol, total_trades, winning_trades, losing_trades, total_pnl)
                    VALUES (100.0, 0, 0, 0, 0.0)
                """)
            
            conn.commit()

    # ==================== 代币操作 ====================
    
    def get_or_create_token(self, href: str, name: str = None, symbol: str = None, ca: str = None) -> int:
        """
        获取或创建代币记录 (Safe & Robust)
        
        优化逻辑：
        1. 优先按 CA 查找（如果提供了 CA）- 避免因 href 变更导致的重复创建
        2. 其次按 Href 查找
        3. 处理并发和唯一性冲突
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            token_id = None
            
            # 1. 尝试按 CA 查找 (唯一性更强)
            if ca:
                cursor.execute("SELECT id FROM tokens WHERE ca = ?", (ca,))
                row = cursor.fetchone()
                if row:
                    token_id = row[0]
                    # 安全更新信息 (尝试更新 href, name, symbol)
                    self._update_token_safe(cursor, token_id, href=href, 
                                          name=name, symbol=symbol, ca=None)
                    return token_id
            
            # 2. 尝试按 Href 查找
            cursor.execute("SELECT id FROM tokens WHERE href = ?", (href,))
            row = cursor.fetchone()
            if row:
                token_id = row[0]
                # 安全更新信息 (尝试更新 ca)
                self._update_token_safe(cursor, token_id, href=None, 
                                      name=name, symbol=symbol, ca=ca)
                return token_id
            
            # 3. 创建新记录
            try:
                cursor.execute("""
                    INSERT INTO tokens (href, name, symbol, ca)
                    VALUES (?, ?, ?, ?)
                """, (href, name, symbol, ca))
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                # 4. 冲突处理
                # 可能在检查和插入之间被其他线程插入了，或者 href/ca 冲突
                cursor.execute("SELECT id FROM tokens WHERE href = ?", (href,))
                row = cursor.fetchone()
                if row: return row[0]
                
                if ca:
                    cursor.execute("SELECT id FROM tokens WHERE ca = ?", (ca,))
                    row = cursor.fetchone()
                    if row: return row[0]
                
                raise

    def _update_token_safe(self, cursor, token_id: int, 
                          href: str = None, name: str = None, 
                          symbol: str = None, ca: str = None) -> None:
        """辅助方法：安全更新代币信息，忽略唯一性冲突"""
        updates = []
        params = []
        
        if href:
            updates.append("href = ?")
            params.append(href)
        if ca:
            updates.append("ca = ?")
            params.append(ca)
        if name:
            updates.append("name = ?")
            params.append(name)
        if symbol:
            updates.append("symbol = ?")
            params.append(symbol)
        
        if not updates:
            return

        updates.append("last_updated = CURRENT_TIMESTAMP")
        params.append(token_id)
        
        try:
            sql = f"UPDATE tokens SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(sql, params)
        except sqlite3.IntegrityError as e:
            # 忽略冲突，只记录警告
            _logger.warning(f"更新Token[{token_id}]字段冲突: {e}. 跳过冲突字段.")
            
            # 降级：只更新非唯一字段
            if name or symbol:
                try:
                    safe_updates = ["last_updated = CURRENT_TIMESTAMP"]
                    safe_params = [token_id]
                    if name:
                        safe_updates.insert(0, "name = ?")
                        safe_params.insert(0, name)
                    if symbol:
                        safe_updates.insert(0, "symbol = ?")
                        safe_params.insert(0, symbol)
                    
                    sql_safe = f"UPDATE tokens SET {', '.join(safe_updates)} WHERE id = ?"
                    cursor.execute(sql_safe, safe_params)
                except Exception:
                    pass

    def update_token_ca(self, token_id: int, ca: str) -> bool:
        """
        更新代币的 CA 地址
        
        参数:
            token_id: 代币 ID
            ca: 合约地址
            
        返回:
            是否更新成功
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tokens SET ca = ?, last_updated = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (ca, token_id))
            return cursor.rowcount > 0

    def get_token_by_href(self, href: str) -> Optional[Dict]:
        """通过 href 获取代币信息"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tokens WHERE href = ?", (href,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_token_by_ca(self, ca: str) -> Optional[Dict]:
        """通过 CA 获取代币信息"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tokens WHERE ca = ?", (ca,))
            row = cursor.fetchone()
            return dict(row) if row else None

    # ==================== 价格快照操作 ====================
    
    def save_price_snapshot(self, token_id: int, data: Dict) -> int:
        """
        保存价格快照
        
        参数:
            token_id: 代币 ID
            data: 快照数据字典
            
        返回:
            快照 ID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO price_snapshots (
                    token_id, price, market_cap, market_cap_str,
                    liquidity, liquidity_str, volume_24h, volume_24h_str,
                    txns_24h, makers_24h, pair_age,
                    growth_5m, growth_1h, growth_6h, growth_24h, source_file
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                token_id,
                data.get('price'),
                data.get('market_cap'),
                data.get('market_cap_str'),
                data.get('liquidity'),
                data.get('liquidity_str'),
                data.get('volume_24h'),
                data.get('volume_24h_str'),
                data.get('txns_24h'),
                data.get('makers_24h'),
                data.get('pair_age'),
                data.get('growth_5m', 0.0),
                data.get('growth_1h', 0.0),
                data.get('growth_6h', 0.0),
                data.get('growth_24h', 0.0),
                data.get('source_file', '')
            ))
            return cursor.lastrowid

    def get_latest_snapshot(self, token_id: int) -> Optional[Dict]:
        """获取代币最新的价格快照"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM price_snapshots 
                WHERE token_id = ? 
                ORDER BY timestamp DESC LIMIT 1
            """, (token_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_snapshots_in_range(self, token_id: int, 
                                start_time: datetime, 
                                end_time: datetime = None) -> List[Dict]:
        """获取指定时间范围内的价格快照"""
        if end_time is None:
            end_time = datetime.now()
            
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM price_snapshots 
                WHERE token_id = ? AND timestamp BETWEEN ? AND ?
                ORDER BY timestamp ASC
            """, (token_id, start_time.isoformat(), end_time.isoformat()))
            return [dict(row) for row in cursor.fetchall()]

    # ==================== 信号事件操作 ====================
    
    def create_signal_event(self, token_id: int, signal_type: str,
                            trigger_value: float, market_cap_at_trigger: float,
                            price_at_trigger: float) -> int:
        """
        创建信号事件
        
        参数:
            token_id: 代币 ID
            signal_type: 信号类型 (如 '5M_PRICE_ALERT')
            trigger_value: 触发值 (如涨跌幅)
            market_cap_at_trigger: 触发时市值
            price_at_trigger: 触发时价格
            
        返回:
            信号事件 ID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO signal_events (
                    token_id, signal_type, trigger_value,
                    market_cap_at_trigger, price_at_trigger
                ) VALUES (?, ?, ?, ?, ?)
            """, (token_id, signal_type, trigger_value, market_cap_at_trigger, price_at_trigger))
            return cursor.lastrowid

    def update_signal_validation(self, signal_id: int, 
                                  is_validated: bool, 
                                  result: str) -> None:
        """更新信号验证结果"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE signal_events 
                SET is_validated = ?, validation_result = ?
                WHERE id = ?
            """, (1 if is_validated else 0, result, signal_id))

    def get_recent_signals(self, hours: int = 24) -> List[Dict]:
        """获取最近的信号事件"""
        cutoff = datetime.now() - timedelta(hours=hours)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.*, t.name, t.symbol, t.href, t.ca
                FROM signal_events s
                JOIN tokens t ON s.token_id = t.id
                WHERE s.created_at >= ?
                ORDER BY s.created_at DESC
            """, (cutoff.isoformat(),))
            return [dict(row) for row in cursor.fetchall()]

    def has_historical_signals(self, token_id: int, hours_ago: int = 4) -> bool:
        """
        检查代币是否有超过指定小时前的信号记录（用于策略R的"老用户"判断）
        
        参数:
            token_id: 代币 ID
            hours_ago: 时间阈值（默认4小时前）
            
        返回:
            如果有历史信号返回 True
        """
        cutoff = datetime.now() - timedelta(hours=hours_ago)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM signal_events 
                WHERE token_id = ? AND created_at < ?
            """, (token_id, cutoff.isoformat()))
            count = cursor.fetchone()[0]
            return count > 0

    # ==================== 信号跟踪操作 ====================
    
    def add_signal_tracking(self, signal_event_id: int, data: Dict, 
                            minute_offset: int) -> int:
        """添加信号跟踪数据点"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO signal_tracking (
                    signal_event_id, price, price_change_from_trigger,
                    volume_5m, txns_5m_buys, txns_5m_sells,
                    liquidity, market_cap, minute_offset
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal_event_id,
                data.get('price'),
                data.get('price_change'),
                data.get('volume_5m'),
                data.get('txns_5m_buys'),
                data.get('txns_5m_sells'),
                data.get('liquidity'),
                data.get('market_cap'),
                minute_offset
            ))
            return cursor.lastrowid

    def get_signal_tracking_data(self, signal_event_id: int) -> List[Dict]:
        """获取信号的所有跟踪数据"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM signal_tracking 
                WHERE signal_event_id = ?
                ORDER BY minute_offset ASC
            """, (signal_event_id,))
            return [dict(row) for row in cursor.fetchall()]

    # ==================== 模拟交易操作 ====================
    
    def get_account_state(self) -> Dict:
        """获取模拟账户状态"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM account_state ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            return dict(row) if row else {
                'balance_sol': 100.0,
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'total_pnl': 0.0
            }

    def update_account_state(self, balance: float, pnl: float, is_win: bool) -> None:
        """更新模拟账户状态"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE account_state SET
                    balance_sol = ?,
                    total_trades = total_trades + 1,
                    winning_trades = winning_trades + ?,
                    losing_trades = losing_trades + ?,
                    total_pnl = total_pnl + ?,
                    last_updated = CURRENT_TIMESTAMP
                WHERE id = (SELECT MAX(id) FROM account_state)
            """, (balance, 1 if is_win else 0, 0 if is_win else 1, pnl))

    def record_trade(self, token_id: int, signal_event_id: int,
                     action: str, amount_sol: float, price: float,
                     token_amount: float, fee_sol: float,
                     pnl_sol: float = None, pnl_percent: float = None,
                     balance_after: float = None, notes: str = None) -> int:
        """记录模拟交易"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO simulated_trades (
                    token_id, signal_event_id, action, amount_sol,
                    price_at_trade, token_amount, fee_percent, fee_sol,
                    pnl_sol, pnl_percent, balance_after, notes
                ) VALUES (?, ?, ?, ?, ?, ?, 3.0, ?, ?, ?, ?, ?)
            """, (
                token_id, signal_event_id, action, amount_sol,
                price, token_amount, fee_sol, pnl_sol, pnl_percent,
                balance_after, notes
            ))
            return cursor.lastrowid

    def get_trade_history(self, limit: int = 100) -> List[Dict]:
        """获取交易历史"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT st.*, t.name, t.symbol, t.href
                FROM simulated_trades st
                JOIN tokens t ON st.token_id = t.id
                ORDER BY st.timestamp DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def record_multi_strategy_trade(self, strategy_type: str, token_ca: str,
                                     token_name: str, action: str,
                                     price: float, amount: float, pnl: float = 0.0) -> int:
        """
        记录多策略交易
        
        参数:
            strategy_type: 策略类型 (A, B, C, D, F, G, H, R)
            token_ca: 代币合约地址
            token_name: 代币名称
            action: 交易动作 (BUY, SELL)
            price: 买入/卖出时的市值
            amount: 交易金额 (SOL)
            pnl: 盈亏 (SOL)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # 确保表存在
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS strategy_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_type TEXT NOT NULL,
                    token_ca TEXT NOT NULL,
                    token_name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    price REAL,
                    amount REAL,
                    pnl REAL DEFAULT 0,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                INSERT INTO strategy_trades (
                    strategy_type, token_ca, token_name, action, price, amount, pnl
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (strategy_type, token_ca, token_name, action, price, amount, pnl))
            conn.commit()
            return cursor.lastrowid

    # ==================== API 缓存操作 ====================
    
    def cache_api_data(self, token_ca: str, data: Dict, raw_json: str = None) -> int:
        """缓存 API 数据"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO api_data_cache (
                    token_ca, price_usd, price_native,
                    txns_m5_buys, txns_m5_sells,
                    txns_h1_buys, txns_h1_sells,
                    txns_h24_buys, txns_h24_sells,
                    volume_m5, volume_h1, volume_h6, volume_h24,
                    price_change_m5, price_change_h1, price_change_h6, price_change_h24,
                    liquidity_usd, fdv, market_cap, pair_created_at, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                token_ca,
                data.get('price_usd'),
                data.get('price_native'),
                data.get('txns_m5_buys'),
                data.get('txns_m5_sells'),
                data.get('txns_h1_buys'),
                data.get('txns_h1_sells'),
                data.get('txns_h24_buys'),
                data.get('txns_h24_sells'),
                data.get('volume_m5'),
                data.get('volume_h1'),
                data.get('volume_h6'),
                data.get('volume_h24'),
                data.get('price_change_m5'),
                data.get('price_change_h1'),
                data.get('price_change_h6'),
                data.get('price_change_h24'),
                data.get('liquidity_usd'),
                data.get('fdv'),
                data.get('market_cap'),
                data.get('pair_created_at'),
                raw_json
            ))
            return cursor.lastrowid

    def get_latest_api_cache(self, token_ca: str) -> Optional[Dict]:
        """获取最新的 API 缓存数据"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM api_data_cache 
                WHERE token_ca = ?
                ORDER BY timestamp DESC LIMIT 1
            """, (token_ca,))
            row = cursor.fetchone()
            return dict(row) if row else None

    # ==================== 数据清理操作 ====================
    
    def cleanup_old_data(self, days: int = 30) -> Dict[str, int]:
        """
        清理超过指定天数的旧数据
        
        参数:
            days: 保留天数（默认30天）
            
        返回:
            各表清理的记录数
        """
        cutoff = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff.isoformat()
        
        cleanup_stats = {}
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 清理价格快照
            cursor.execute(
                "DELETE FROM price_snapshots WHERE timestamp < ?", 
                (cutoff_str,)
            )
            cleanup_stats['price_snapshots'] = cursor.rowcount
            
            # 清理 API 缓存
            cursor.execute(
                "DELETE FROM api_data_cache WHERE timestamp < ?", 
                (cutoff_str,)
            )
            cleanup_stats['api_data_cache'] = cursor.rowcount
            
            # 清理信号跟踪数据
            cursor.execute(
                "DELETE FROM signal_tracking WHERE timestamp < ?", 
                (cutoff_str,)
            )
            cleanup_stats['signal_tracking'] = cursor.rowcount
            
            conn.commit()
        
        self._logger.info(f"数据清理完成: {cleanup_stats}")
        return cleanup_stats

    # ==================== API 历史数据操作 ====================
    
    def insert_api_history(self, token_id: int, api_data: Dict) -> Optional[int]:
        """
        插入 API 历史数据记录
        
        参数:
            token_id: 关联的代币 ID
            api_data: API 返回的原始数据（单个交易对）
            
        返回:
            插入的记录 ID
        """
        try:
            base_token = api_data.get("baseToken", {})
            txns = api_data.get("txns", {})
            volume = api_data.get("volume", {})
            price_change = api_data.get("priceChange", {})
            liquidity = api_data.get("liquidity", {})
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO api_history (
                        token_id, token_address, token_name, token_symbol,
                        price_usd,
                        txns_m5_buys, txns_m5_sells,
                        txns_h1_buys, txns_h1_sells,
                        txns_h6_buys, txns_h6_sells,
                        txns_h24_buys, txns_h24_sells,
                        volume_m5, volume_h1, volume_h6, volume_h24,
                        price_change_h1, price_change_h6, price_change_h24,
                        liquidity_usd, market_cap
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    token_id,
                    base_token.get("address", ""),
                    base_token.get("name", ""),
                    base_token.get("symbol", ""),
                    float(api_data.get("priceUsd", 0) or 0),
                    txns.get("m5", {}).get("buys", 0),
                    txns.get("m5", {}).get("sells", 0),
                    txns.get("h1", {}).get("buys", 0),
                    txns.get("h1", {}).get("sells", 0),
                    txns.get("h6", {}).get("buys", 0),
                    txns.get("h6", {}).get("sells", 0),
                    txns.get("h24", {}).get("buys", 0),
                    txns.get("h24", {}).get("sells", 0),
                    volume.get("m5", 0) or 0,
                    volume.get("h1", 0) or 0,
                    volume.get("h6", 0) or 0,
                    volume.get("h24", 0) or 0,
                    price_change.get("h1", 0) or 0,
                    price_change.get("h6", 0) or 0,
                    price_change.get("h24", 0) or 0,
                    liquidity.get("usd", 0) or 0,
                    api_data.get("marketCap", 0) or 0,
                ))
                return cursor.lastrowid
                
        except Exception as e:
            self._logger.error(f"插入 API 历史数据失败: {e}")
            return None

    def get_database_stats(self) -> Dict[str, int]:
        """获取数据库统计信息"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            stats = {}
            
            tables = ['tokens', 'price_snapshots', 'signal_events', 
                      'signal_tracking', 'simulated_trades', 'api_data_cache', 'api_history',
                      'strategy_states', 'strategy_positions']
            
            for table in tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    stats[table] = cursor.fetchone()[0]
                except:
                    stats[table] = 0
            
            return stats

    # ==================== 策略状态操作 ====================
    
    def save_strategy_state(self, strategy_type: str, state_dict: Dict) -> bool:
        """
        保存/更新策略状态
        
        参数:
            strategy_type: 策略类型 (A, B, C, D, F, G, H, R, Alpha)
            state_dict: 状态字典，包含 balance_sol, total_trades 等
            
        返回:
            是否保存成功
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO strategy_states (
                        strategy_type, balance_sol, total_trades,
                        winning_trades, losing_trades, total_pnl
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(strategy_type) DO UPDATE SET
                        balance_sol = excluded.balance_sol,
                        total_trades = excluded.total_trades,
                        winning_trades = excluded.winning_trades,
                        losing_trades = excluded.losing_trades,
                        total_pnl = excluded.total_pnl,
                        last_updated = CURRENT_TIMESTAMP
                """, (
                    strategy_type,
                    state_dict.get("balance_sol", 100.0),
                    state_dict.get("total_trades", 0),
                    state_dict.get("winning_trades", 0),
                    state_dict.get("losing_trades", 0),
                    state_dict.get("total_pnl", 0.0),
                ))
                return True
        except Exception as e:
            self._logger.error(f"保存策略 {strategy_type} 状态失败: {e}")
            return False
    
    def load_strategy_state(self, strategy_type: str) -> Optional[Dict]:
        """
        加载策略状态
        
        参数:
            strategy_type: 策略类型
            
        返回:
            状态字典，如果不存在则返回 None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT balance_sol, total_trades, winning_trades, 
                       losing_trades, total_pnl, last_updated
                FROM strategy_states WHERE strategy_type = ?
            """, (strategy_type,))
            row = cursor.fetchone()
            if row:
                return {
                    "balance_sol": row[0],
                    "total_trades": row[1],
                    "winning_trades": row[2],
                    "losing_trades": row[3],
                    "total_pnl": row[4],
                    "last_updated": row[5],
                }
            return None

    # ==================== 持仓操作 ====================
    
    def save_position(self, strategy_type: str, position_data: Dict) -> bool:
        """
        保存/更新持仓
        
        参数:
            strategy_type: 策略类型
            position_data: 持仓数据字典，包含 token_id, token_ca, token_name 等
            
        返回:
            是否保存成功
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO strategy_positions (
                        strategy_type, token_id, token_ca, token_name,
                        buy_market_cap, buy_amount_sol, buy_time,
                        remaining_ratio, highest_multiplier, take_profit_level, poll_count,
                        loss_check_count, trailing_stop_multiplier
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(strategy_type, token_id) DO UPDATE SET
                        remaining_ratio = excluded.remaining_ratio,
                        highest_multiplier = excluded.highest_multiplier,
                        take_profit_level = excluded.take_profit_level,
                        poll_count = excluded.poll_count,
                        loss_check_count = excluded.loss_check_count,
                        trailing_stop_multiplier = excluded.trailing_stop_multiplier
                """, (
                    strategy_type,
                    position_data.get("token_id"),
                    position_data.get("token_ca"),
                    position_data.get("token_name"),
                    position_data.get("buy_market_cap"),
                    position_data.get("buy_amount_sol"),
                    position_data.get("buy_time"),
                    position_data.get("remaining_ratio", 1.0),
                    position_data.get("highest_multiplier", 1.0),
                    position_data.get("take_profit_level", 0),
                    position_data.get("poll_count", 0),
                    position_data.get("loss_check_count", 0),
                    position_data.get("trailing_stop_multiplier", 0.7),
                ))
                return True
        except Exception as e:
            self._logger.error(f"保存持仓失败: {e}")
            return False
    
    def update_position(self, strategy_type: str, token_id: int, 
                        updates: Dict) -> bool:
        """
        更新持仓的部分字段
        
        参数:
            strategy_type: 策略类型
            token_id: 代币 ID
            updates: 要更新的字段字典
            
        返回:
            是否更新成功
        """
        if not updates:
            return False
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 构建更新语句
                set_parts = []
                values = []
                for key, value in updates.items():
                    if key in ("remaining_ratio", "highest_multiplier", 
                               "take_profit_level", "poll_count",
                               "loss_check_count", "trailing_stop_multiplier"):
                        set_parts.append(f"{key} = ?")
                        values.append(value)
                
                if not set_parts:
                    return False
                
                values.extend([strategy_type, token_id])
                cursor.execute(f"""
                    UPDATE strategy_positions 
                    SET {', '.join(set_parts)}
                    WHERE strategy_type = ? AND token_id = ?
                """, values)
                return cursor.rowcount > 0
        except Exception as e:
            self._logger.error(f"更新持仓失败: {e}")
            return False
    
    def delete_position(self, strategy_type: str, token_id: int) -> bool:
        """
        删除持仓
        
        参数:
            strategy_type: 策略类型
            token_id: 代币 ID
            
        返回:
            是否删除成功
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM strategy_positions 
                    WHERE strategy_type = ? AND token_id = ?
                """, (strategy_type, token_id))
                return cursor.rowcount > 0
        except Exception as e:
            self._logger.error(f"删除持仓失败: {e}")
            return False
    
    def load_positions(self, strategy_type: str) -> List[Dict]:
        """
        加载策略的所有持仓
        
        参数:
            strategy_type: 策略类型
            
        返回:
            持仓数据列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT token_id, token_ca, token_name,
                       buy_market_cap, buy_amount_sol, buy_time,
                       remaining_ratio, highest_multiplier, 
                       take_profit_level, poll_count,
                       loss_check_count, trailing_stop_multiplier
                FROM strategy_positions WHERE strategy_type = ?
            """, (strategy_type,))
            
            positions = []
            for row in cursor.fetchall():
                positions.append({
                    "token_id": row[0],
                    "token_ca": row[1],
                    "token_name": row[2],
                    "buy_market_cap": row[3],
                    "buy_amount_sol": row[4],
                    "buy_time": row[5],
                    "remaining_ratio": row[6],
                    "highest_multiplier": row[7],
                    "take_profit_level": row[8],
                    "poll_count": row[9],
                    "loss_check_count": row[10] if len(row) > 10 else 0,
                    "trailing_stop_multiplier": row[11] if len(row) > 11 else 0.7,
                })
            return positions
    
    def get_all_positions_count(self) -> Dict[str, int]:
        """获取各策略的持仓数量"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT strategy_type, COUNT(*) 
                FROM strategy_positions 
                GROUP BY strategy_type
            """)
            return {row[0]: row[1] for row in cursor.fetchall()}

    # ==================== 手动买入队列 ====================
    
    def add_manual_order(self, token_ca: str, amount_sol: float = 0.2) -> int:
        """
        添加手动买入订单到队列
        
        参数:
            token_ca: 代币合约地址
            amount_sol: 买入金额 (SOL)
            
        返回:
            订单 ID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO manual_buy_queue (token_ca, amount_sol, status)
                VALUES (?, ?, 'PENDING')
            """, (token_ca, amount_sol))
            return cursor.lastrowid
    
    def get_pending_manual_orders(self) -> List[Dict]:
        """获取所有待处理的手动买入订单"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, token_ca, amount_sol, created_at
                FROM manual_buy_queue
                WHERE status = 'PENDING'
                ORDER BY created_at ASC
            """)
            orders = []
            for row in cursor.fetchall():
                orders.append({
                    "id": row[0],
                    "token_ca": row[1],
                    "amount_sol": row[2],
                    "created_at": row[3]
                })
            return orders
    
    def mark_manual_order_done(self, order_id: int, result_info: str = None) -> None:
        """标记手动订单为已完成"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE manual_buy_queue 
                SET status = 'DONE', result_info = ?, processed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (result_info, order_id))
    
    def mark_manual_order_failed(self, order_id: int, error_msg: str) -> None:
        """标记手动订单为失败"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE manual_buy_queue 
                SET status = 'FAILED', error_msg = ?, processed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (error_msg, order_id))

    def get_manual_order(self, order_id: int) -> Optional[Dict]:
        """获取单个手动订单详情"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, token_ca, amount_sol, status, error_msg, result_info, created_at, processed_at
                FROM manual_buy_queue
                WHERE id = ?
            """, (order_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "token_ca": row[1],
                    "amount_sol": row[2],
                    "status": row[3],
                    "error_msg": row[4],
                    "result_info": row[5],
                    "created_at": row[6],
                    "processed_at": row[7]
                }
            return None

    # ==================== 手动卖出队列 ====================
    
    def add_manual_sell_order(self, strategy_type: str, token_id: int) -> int:
        """
        添加手动卖出订单到队列
        
        参数:
            strategy_type: 策略类型
            token_id: 代币 ID
            
        返回:
            订单 ID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO manual_sell_queue (strategy_type, token_id, status)
                VALUES (?, ?, 'PENDING')
            """, (strategy_type, token_id))
            return cursor.lastrowid
    
    def get_pending_manual_sell_orders(self) -> List[Dict]:
        """获取所有待处理的手动卖出订单"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, strategy_type, token_id, created_at
                FROM manual_sell_queue
                WHERE status = 'PENDING'
                ORDER BY created_at ASC
            """)
            orders = []
            for row in cursor.fetchall():
                orders.append({
                    "id": row[0],
                    "strategy_type": row[1],
                    "token_id": row[2],
                    "created_at": row[3]
                })
            return orders
    
    def mark_manual_sell_order_done(self, order_id: int, result_info: str = None) -> None:
        """标记手动卖出订单为已完成"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE manual_sell_queue 
                SET status = 'DONE', result_info = ?, processed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (result_info, order_id))
    
    def mark_manual_sell_order_failed(self, order_id: int, error_msg: str) -> None:
        """标记手动卖出订单为失败"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE manual_sell_queue 
                SET status = 'FAILED', error_msg = ?, processed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (error_msg, order_id))

    def get_manual_sell_order(self, order_id: int) -> Optional[Dict]:
        """获取单个手动卖出订单详情"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, strategy_type, token_id, status, error_msg, result_info, created_at, processed_at
                FROM manual_sell_queue
                WHERE id = ?
            """, (order_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "strategy_type": row[1],
                    "token_id": row[2],
                    "status": row[3],
                    "error_msg": row[4],
                    "result_info": row[5],
                    "created_at": row[6],
                    "processed_at": row[7]
                }
            return None

    def get_recent_trades_for_token(self, strategy_type: str, token_id: int, 
                                     limit: int = 2) -> List[Dict]:
        """
        获取指定策略和代币的最近交易记录（用于冷静期检查）
        
        参数:
            strategy_type: 策略类型 (A, B, C, ...)
            token_id: 代币 ID
            limit: 返回的记录数量
            
        返回:
            交易记录列表，按时间倒序排列
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT strategy_type, token_ca, token_name, action, price, amount, pnl, timestamp as created_at
                FROM strategy_trades
                WHERE strategy_type = ? AND token_ca IN (
                    SELECT ca FROM tokens WHERE id = ? AND ca IS NOT NULL
                )
                ORDER BY timestamp DESC
                LIMIT ?
            """, (strategy_type, token_id, limit))
            
            trades = []
            for row in cursor.fetchall():
                trades.append({
                    "strategy_type": row[0],
                    "token_ca": row[1],
                    "token_name": row[2],
                    "action": row[3],
                    "price": row[4],
                    "amount": row[5],
                    "pnl": row[6],
                    "created_at": row[7],
                })
            return trades

    def get_recent_trades_by_ca(self, strategy_type: str, token_ca: str,
                                 limit: int = 2) -> List[Dict]:
        """
        获取指定策略和代币CA的最近交易记录（用于冷静期检查）
        
        直接使用 token_ca 查询，避免通过 token_id 映射可能导致的匹配失败。
        
        参数:
            strategy_type: 策略类型 (A, B, C, ...)
            token_ca: 代币合约地址
            limit: 返回的记录数量
            
        返回:
            交易记录列表，按时间倒序排列
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT strategy_type, token_ca, token_name, action, price, amount, pnl, timestamp as created_at
                FROM strategy_trades
                WHERE strategy_type = ? AND token_ca = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (strategy_type, token_ca, limit))
            
            trades = []
            for row in cursor.fetchall():
                trades.append({
                    "strategy_type": row[0],
                    "token_ca": row[1],
                    "token_name": row[2],
                    "action": row[3],
                    "price": row[4],
                    "amount": row[5],
                    "pnl": row[6],
                    "created_at": row[7],
                })
            return trades

