# -*- coding: utf-8 -*-
"""
出场策略优化回测程序
测试不同超时时间、趋势延期、市值/热度分段策略的效果
"""

import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import json

DB_PATH = Path(__file__).parent.parent / "data" / "dex_monitor.db"

@dataclass
class TradeResult:
    """单笔交易结果"""
    token_ca: str
    buy_mc: float
    sell_mc: float
    pnl: float
    hold_minutes: int
    exit_reason: str  # 'timeout', 'stop_loss', 'take_profit', 'trailing_stop'
    extended: bool  # 是否触发了延期

@dataclass
class BacktestConfig:
    """回测配置"""
    name: str
    base_timeout: int  # 基础超时时间（分钟）
    use_trend_extension: bool  # 是否启用趋势延期
    trend_threshold: float  # 触发延期的涨幅阈值（如 0.10 = 10%）
    extension_minutes: int  # 延期时间
    max_extensions: int  # 最大延期次数
    use_market_cap_timeout: bool  # 是否按市值分段超时
    use_heat_timeout: bool  # 是否按热度分段超时
    stop_loss_pct: float  # 止损比例（如 -0.30 = -30%）
    take_profit_pct: float  # 止盈比例（如 0.50 = 50%）

def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def get_timeout_by_market_cap(market_cap: float) -> int:
    """根据市值返回超时时间（基于数据分析）"""
    if market_cap < 100000:      # <100k
        return 45
    elif market_cap < 200000:    # 100k-200k
        return 50
    elif market_cap < 500000:    # 200k-500k
        return 75  # 最佳市值段
    elif market_cap < 1000000:   # 500k-1M
        return 60
    else:                        # >1M
        return 65

def get_timeout_by_heat(heat_5m: int) -> int:
    """根据热度返回超时时间（基于数据分析）"""
    if heat_5m < 10:
        return 45
    elif heat_5m < 30:   # 低热度 = 更长持有
        return 80
    elif heat_5m < 50:
        return 60
    elif heat_5m < 100:
        return 50
    else:
        return 55

class BacktestEngine:
    """回测引擎"""
    
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.conn = get_connection()
    
    def get_dynamic_timeout(self, buy_mc: float, heat: int) -> int:
        """获取动态超时时间"""
        if self.config.use_market_cap_timeout:
            return get_timeout_by_market_cap(buy_mc)
        elif self.config.use_heat_timeout:
            return get_timeout_by_heat(heat)
        else:
            return self.config.base_timeout
    
    def should_extend(self, buy_mc: float, current_mc: float) -> bool:
        """判断是否应该延期"""
        if not self.config.use_trend_extension:
            return False
        multiplier = current_mc / buy_mc if buy_mc > 0 else 0
        return multiplier >= (1 + self.config.trend_threshold)
    
    def simulate_trade(self, buy_amount: float, price_history: List[dict], heat: int = 0) -> Optional[TradeResult]:
        """模拟单笔交易"""
        if not price_history or len(price_history) < 5:
            return None
        
        buy_mc = price_history[0]['market_cap']
        if not buy_mc or buy_mc <= 0:
            return None
        
        timeout = self.get_dynamic_timeout(buy_mc, heat)
        extensions = 0
        extended = False
        
        highest_mc = buy_mc  # 用于计算移动止损
        
        for idx, point in enumerate(price_history):
            current_mc = point['market_cap']
            if not current_mc or current_mc <= 0:
                continue
            
            minutes = idx  # 假设每条记录约 1 分钟
            multiplier = current_mc / buy_mc
            
            # 更新最高市值
            if current_mc > highest_mc:
                highest_mc = current_mc
            
            # 检查止损 (-30%)
            if multiplier <= (1 + self.config.stop_loss_pct):
                pnl = (multiplier - 1) * buy_amount
                return TradeResult(
                    token_ca="",
                    buy_mc=buy_mc,
                    sell_mc=current_mc,
                    pnl=pnl,
                    hold_minutes=minutes,
                    exit_reason='stop_loss',
                    extended=extended
                )
            
            # 检查止盈 (50%)
            if multiplier >= (1 + self.config.take_profit_pct):
                pnl = (multiplier - 1) * buy_amount
                return TradeResult(
                    token_ca="",
                    buy_mc=buy_mc,
                    sell_mc=current_mc,
                    pnl=pnl,
                    hold_minutes=minutes,
                    exit_reason='take_profit',
                    extended=extended
                )
            
            # 检查移动止损（从最高点回撤 20%）
            if highest_mc > buy_mc * 1.3:  # 曾涨过 30%
                drawdown = (highest_mc - current_mc) / highest_mc
                if drawdown > 0.20:  # 回撤超过 20%
                    pnl = (multiplier - 1) * buy_amount
                    return TradeResult(
                        token_ca="",
                        buy_mc=buy_mc,
                        sell_mc=current_mc,
                        pnl=pnl,
                        hold_minutes=minutes,
                        exit_reason='trailing_stop',
                        extended=extended
                    )
            
            # 检查超时
            if minutes >= timeout:
                # 检查是否应该延期
                if self.should_extend(buy_mc, current_mc) and extensions < self.config.max_extensions:
                    timeout += self.config.extension_minutes
                    extensions += 1
                    extended = True
                else:
                    # 超时离场
                    pnl = (multiplier - 1) * buy_amount
                    return TradeResult(
                        token_ca="",
                        buy_mc=buy_mc,
                        sell_mc=current_mc,
                        pnl=pnl,
                        hold_minutes=minutes,
                        exit_reason='timeout',
                        extended=extended
                    )
        
        # 数据结束，按最后价格离场
        if price_history:
            final_mc = price_history[-1]['market_cap'] or buy_mc
            multiplier = final_mc / buy_mc
            pnl = (multiplier - 1) * buy_amount
            return TradeResult(
                token_ca="",
                buy_mc=buy_mc,
                sell_mc=final_mc,
                pnl=pnl,
                hold_minutes=len(price_history),
                exit_reason='end_of_data',
                extended=extended
            )
        
        return None
    
    def run_backtest(self, sample_limit: int = 500) -> Dict:
        """运行回测"""
        cursor = self.conn.cursor()
        
        # 获取买入交易
        cursor.execute("""
            SELECT token_ca, amount as buy_amount, timestamp as buy_time
            FROM strategy_trades
            WHERE action = 'BUY'
            ORDER BY timestamp
            LIMIT ?
        """, (sample_limit,))
        
        buys = cursor.fetchall()
        
        results = {
            'config_name': self.config.name,
            'total_trades': 0,
            'total_pnl': 0.0,
            'wins': 0,
            'losses': 0,
            'flat': 0,
            'exit_reasons': defaultdict(int),
            'extended_count': 0,
            'avg_hold_minutes': 0,
            'trade_results': []
        }
        
        hold_minutes_sum = 0
        
        for buy in buys:
            # 获取价格历史
            cursor.execute("""
                SELECT market_cap, txns_m5_buys, txns_m5_sells
                FROM api_history
                WHERE token_address = ? AND timestamp > ?
                ORDER BY timestamp
                LIMIT 300
            """, (buy['token_ca'], buy['buy_time']))
            
            history = cursor.fetchall()
            if len(history) < 10:
                continue
            
            # 计算热度
            heat = (history[0]['txns_m5_buys'] or 0) + (history[0]['txns_m5_sells'] or 0)
            
            # 模拟交易
            result = self.simulate_trade(buy['buy_amount'], history, heat)
            if not result:
                continue
            
            result.token_ca = buy['token_ca']
            results['total_trades'] += 1
            results['total_pnl'] += result.pnl
            results['exit_reasons'][result.exit_reason] += 1
            hold_minutes_sum += result.hold_minutes
            
            if result.extended:
                results['extended_count'] += 1
            
            if result.pnl > 0.001:
                results['wins'] += 1
            elif result.pnl < -0.001:
                results['losses'] += 1
            else:
                results['flat'] += 1
            
            results['trade_results'].append(result)
        
        if results['total_trades'] > 0:
            results['avg_pnl'] = results['total_pnl'] / results['total_trades']
            results['win_rate'] = results['wins'] / results['total_trades'] * 100
            results['avg_hold_minutes'] = hold_minutes_sum / results['total_trades']
        else:
            results['avg_pnl'] = 0
            results['win_rate'] = 0
        
        return results
    
    def close(self):
        self.conn.close()

def run_all_scenarios():
    """运行所有测试场景"""
    scenarios = [
        # A. 基准：当前 30 分钟超时
        BacktestConfig(
            name="A. 基准(30分钟)",
            base_timeout=30,
            use_trend_extension=False,
            trend_threshold=0.10,
            extension_minutes=30,
            max_extensions=0,
            use_market_cap_timeout=False,
            use_heat_timeout=False,
            stop_loss_pct=-0.30,
            take_profit_pct=0.50,
        ),
        # B. 固定 60 分钟
        BacktestConfig(
            name="B. 固定60分钟",
            base_timeout=60,
            use_trend_extension=False,
            trend_threshold=0.10,
            extension_minutes=30,
            max_extensions=0,
            use_market_cap_timeout=False,
            use_heat_timeout=False,
            stop_loss_pct=-0.30,
            take_profit_pct=0.50,
        ),
        # C. 趋势延期（涨10%延期30分钟，最多延2次）
        BacktestConfig(
            name="C. 趋势延期(涨10%+)",
            base_timeout=30,
            use_trend_extension=True,
            trend_threshold=0.10,
            extension_minutes=30,
            max_extensions=2,
            use_market_cap_timeout=False,
            use_heat_timeout=False,
            stop_loss_pct=-0.30,
            take_profit_pct=0.50,
        ),
        # D. 市值分段超时
        BacktestConfig(
            name="D. 市值分段",
            base_timeout=60,
            use_trend_extension=False,
            trend_threshold=0.10,
            extension_minutes=30,
            max_extensions=0,
            use_market_cap_timeout=True,
            use_heat_timeout=False,
            stop_loss_pct=-0.30,
            take_profit_pct=0.50,
        ),
        # E. 热度分段超时
        BacktestConfig(
            name="E. 热度分段",
            base_timeout=60,
            use_trend_extension=False,
            trend_threshold=0.10,
            extension_minutes=30,
            max_extensions=0,
            use_market_cap_timeout=False,
            use_heat_timeout=True,
            stop_loss_pct=-0.30,
            take_profit_pct=0.50,
        ),
        # F. 组合：市值分段 + 趋势延期
        BacktestConfig(
            name="F. 市值+趋势延期",
            base_timeout=60,
            use_trend_extension=True,
            trend_threshold=0.10,
            extension_minutes=30,
            max_extensions=2,
            use_market_cap_timeout=True,
            use_heat_timeout=False,
            stop_loss_pct=-0.30,
            take_profit_pct=0.50,
        ),
        # G. 趋势延期（涨20%延期）
        BacktestConfig(
            name="G. 趋势延期(涨20%+)",
            base_timeout=30,
            use_trend_extension=True,
            trend_threshold=0.20,
            extension_minutes=30,
            max_extensions=2,
            use_market_cap_timeout=False,
            use_heat_timeout=False,
            stop_loss_pct=-0.30,
            take_profit_pct=0.50,
        ),
        # H. 固定 90 分钟
        BacktestConfig(
            name="H. 固定90分钟",
            base_timeout=90,
            use_trend_extension=False,
            trend_threshold=0.10,
            extension_minutes=30,
            max_extensions=0,
            use_market_cap_timeout=False,
            use_heat_timeout=False,
            stop_loss_pct=-0.30,
            take_profit_pct=0.50,
        ),
    ]
    
    print("=" * 80)
    print("出场策略优化回测报告")
    print("=" * 80)
    
    all_results = []
    
    for config in scenarios:
        print(f"\n运行场景: {config.name}...")
        engine = BacktestEngine(config)
        results = engine.run_backtest(sample_limit=500)
        engine.close()
        all_results.append(results)
    
    # 打印对比表
    print("\n" + "=" * 80)
    print("【回测结果对比】")
    print("=" * 80)
    print(f"{'场景名称':<25} {'总PnL':<12} {'平均PnL':<12} {'胜率':<8} {'交易数':<8} {'延期次数':<8}")
    print("-" * 80)
    
    for r in all_results:
        print(f"{r['config_name']:<25} "
              f"{r['total_pnl']:>+10.4f} "
              f"{r.get('avg_pnl', 0):>+10.6f} "
              f"{r.get('win_rate', 0):>6.1f}% "
              f"{r['total_trades']:>6} "
              f"{r['extended_count']:>6}")
    
    # 详细退出原因分析
    print("\n" + "=" * 80)
    print("【退出原因分布】")
    print("=" * 80)
    
    for r in all_results:
        print(f"\n{r['config_name']}:")
        total = r['total_trades']
        for reason, count in sorted(r['exit_reasons'].items(), key=lambda x: -x[1]):
            pct = count / total * 100 if total > 0 else 0
            print(f"  {reason:<15}: {count:>4} ({pct:.1f}%)")
    
    # 找出最优方案
    print("\n" + "=" * 80)
    print("【最优方案排名（按总PnL）】")
    print("=" * 80)
    
    sorted_results = sorted(all_results, key=lambda x: x['total_pnl'], reverse=True)
    for i, r in enumerate(sorted_results[:3], 1):
        print(f"  #{i} {r['config_name']}: PnL={r['total_pnl']:+.4f} SOL, 胜率={r.get('win_rate', 0):.1f}%")
    
    # 保存结果到 JSON
    output_path = Path(__file__).parent.parent / "data" / "backtest_results.json"
    json_results = []
    for r in all_results:
        json_r = {k: v for k, v in r.items() if k != 'trade_results'}
        json_r['exit_reasons'] = dict(r['exit_reasons'])
        json_results.append(json_r)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(json_results, f, ensure_ascii=False, indent=2)
    
    print(f"\n详细结果已保存至: {output_path}")

if __name__ == "__main__":
    run_all_scenarios()
