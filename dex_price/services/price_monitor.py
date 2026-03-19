"""
DEX 价格监控 - 价格监控服务
检测价格变化并发送告警的核心业务逻辑
支持失败重试机制和多策略交易系统
"""

import asyncio
import datetime
import logging
import time
import concurrent.futures
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set

from config.settings import AppSettings, load_url_mappings
from core.browser import BrowserManager
from core.scraper import PageScraper, ScraperError
from core.parser import parse_currency_rows
from core.database import DatabaseManager
from core.api_client import DexScreenerAPI
from core.ca_fetcher import CAFetcher
from models.currency import CurrencyData, Alert
from services.notifier import NotificationService
from services.data_store import DataStore
from utils.helpers import convert_value_to_number, check_page_validity

# 专用日志器
_alerts_logger = logging.getLogger('alerts')    # 预警记录
_scanner_logger = logging.getLogger('scanner')  # Scanner 通知消息


class PriceMonitor:
    """
    主价格监控服务

    协调浏览器抓取、数据解析、价格比较和通知发送
    支持失败重试机制和多策略交易系统
    """

    STRATEGY_SUFFIXES = {
        'A': '(热度≥150)',
        'B': '(5m+20m信号)',
        'C': '(5m信号)',
        'D': '(API价格暴涨)',
        'E': '(20m信号)',
        'F': '(1h信号)',
        'G': '(4h信号)',
        'H': '(金狗狙击)',
        'I': '(钻石手信号)'
    }

    def __init__(self, settings: AppSettings, browser: BrowserManager,
                 notifier: NotificationService, data_store: DataStore,
                 data_dir: Path, db: DatabaseManager = None,
                 strategies: Dict = None, session_manager = None,
                 sniper_notifier: NotificationService = None,
                 trading_simulator = None):
        """
        初始化价格监控器

        参数:
            settings: 应用程序配置
            browser: 浏览器管理器实例
            notifier: 通知服务实例（Scanner 通道）
            data_store: 数据持久化服务
            data_dir: HTML 缓存文件目录
            db: 数据库管理器（可选）
            strategies: 交易策略字典（可选）
            session_manager: 会话管理器（可选）
            sniper_notifier: Sniper 通知服务（可选）
            trading_simulator: 旧版交易模拟器（向后兼容）
        """
        self.settings = settings
        self.browser = browser
        self.notifier = notifier
        self.sniper_notifier = sniper_notifier
        self.data_store = data_store
        self.data_dir = data_dir

        self.scraper = PageScraper(settings, data_dir)
        self.url_mapping = load_url_mappings()
        self.url_chunks = self._split_url_mapping()

        self._cycle_count = 0
        self._logger = logging.getLogger(__name__)
        
        # 数据库和 API
        self.db = db or DatabaseManager(data_dir / "dex_monitor.db")
        self.api = DexScreenerAPI()
        
        # 多策略系统
        self.strategies = strategies or {}
        self.session_manager = session_manager
        

        
        # 向后兼容
        self.trading_simulator = trading_simulator


        # 打印 URL 分片信息
        self._logger.info(f"URL 映射总数: {len(self.url_mapping)} 个")
        for i, chunk in enumerate(self.url_chunks):
            self._logger.info(f"  标签页 {i+1}: {list(chunk.keys())}")
        
        # 每30天清理旧数据
        self._last_cleanup = datetime.datetime.now()
        
        # 反爬虫检测状态
        self._consecutive_high_failure_rounds = 0  # 连续高失败率轮数
        self._api_success_count = 0  # API 成功计数（线程安全替代 _api_healthy）
        self._api_failure_count = 0  # API 失败计数
        self._last_recovery_cycle = 0  # 上次触发恢复的周期数
        self._last_failure_notification_time = None  # 上次失败通知时间（冷却期）

    @property
    def cycle_count(self) -> int:
        """获取当前周期计数"""
        return self._cycle_count

    def run_cycle(self) -> None:
        """
        运行单个监控周期

        这是调度器调用的主入口点
        """
        self._cycle_count += 1
        
        # 尝试重新加载 URL 映射
        self._reload_url_mappings()
        
        self._logger.info(f"========== 开始第 {self._cycle_count} 轮监控 ==========")

        # 检查是否需要重启浏览器
        if self._should_restart_browser():
            self.browser.restart_tabs()

        # 收集所有数据和告警
        all_alerts: List[Alert] = []
        current_data: Dict[str, CurrencyData] = {}

        try:
            # 跨标签页并行抓取（带重试机制）
            current_data, five_min_alerts = self._scrape_all_pages_with_retry()
            all_alerts.extend(five_min_alerts)

            if not current_data:
                self._logger.warning("本轮未收集到任何数据，跳过后续处理")
                return

            # 保存当前快照
            self.data_store.save_current_data(current_data)
            self._save_to_database(current_data)
            self._logger.info(f"★★★ 本轮共记录 {len(current_data)} 条货币数据 ★★★")
            
            # 检查是否需要清理旧数据（每30天）
            self._check_data_cleanup()

            # 执行周期性比较
            for period_name, interval in self.settings.check_intervals.items():
                alerts = self._perform_periodic_check(
                    period_name, interval, current_data
                )
                all_alerts.extend(alerts)
                
                # 为周期性告警触发信号处理（创建/更新监控会话）
                signal_type_map = {
                    "20分钟": "20m",
                    "1小时": "1h",
                    "4小时": "4h",
                }
                signal_type_str = signal_type_map.get(period_name)
                if signal_type_str:
                    for alert in alerts:
                        try:
                            self._handle_signal(alert, signal_type_str)
                        except Exception as e:
                            self._logger.error(f"处理 {period_name} 信号失败: {e}")

            # 发送通知（如果有）
            if all_alerts:
                timestamp = datetime.datetime.now().strftime("%m月%d日-%H:%M")
                asyncio.run(self.notifier.send_all(
                    all_alerts, self._cycle_count, timestamp
                ))

                # 保存通知历史
                html_snippets = [self._alert_to_html(a) for a in all_alerts]
                self.data_store.save_notification_history(html_snippets)

        except Exception as e:
            self._logger.error(f"第 {self._cycle_count} 轮执行失败: {e}", exc_info=True)

    def _should_restart_browser(self) -> bool:
        """检查是否需要重启浏览器标签页"""
        if self._cycle_count <= 1:
            return False
        return (self._cycle_count - 1) % self.settings.browser_restart_interval == 0

    def _split_url_mapping(self) -> List[Dict[str, str]]:
        """将 URL 映射拆分为多个块用于并行处理"""
        all_keys = list(self.url_mapping.keys())
        chunks = []

        for i in range(self.settings.num_pages):
            chunk_keys = all_keys[i::self.settings.num_pages]
            chunk = {k: self.url_mapping[k] for k in chunk_keys}
            chunks.append(chunk)

        return chunks

    def _reload_url_mappings(self) -> None:
        """从文件重新加载 URL 映射"""
        try:
            new_mapping = load_url_mappings()
            # 简单比较长度或内容是否变化
            if new_mapping != self.url_mapping:
                self._logger.info(f"检测到 URL 映射配置变化，正在重新加载...")
                self.url_mapping = new_mapping
                self.url_chunks = self._split_url_mapping()
                self._logger.info(f"URL 映射已更新，当前共 {len(self.url_mapping)} 个")
        except Exception as e:
            self._logger.error(f"重新加载 URL 映射失败: {e}")

    def _scrape_all_pages_with_retry(self) -> Tuple[Dict[str, CurrencyData], List[Alert]]:
        """
        跨多个标签页并行抓取所有页面（带重试机制）

        第一轮：并行抓取所有 URL，记录失败的
        第二轮：重试失败的 URL

        返回:
            (收集到的货币数据, 5分钟告警列表)
        """
        all_data: Dict[str, CurrencyData] = {}
        all_alerts: List[Alert] = []
        all_failed_urls: Dict[int, Set[str]] = {}  # tab_index -> failed_urls
        tabs = self.browser.get_tabs()

        self._logger.info(f"开始第一轮抓取，使用 {len(tabs)} 个标签页...")
        
        # 每轮开始时重置 API 计数器（确保只统计当前轮的 API 健康状态）
        self._api_success_count = 0
        self._api_failure_count = 0

        # 第一轮抓取
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.settings.num_pages) as executor:
            future_to_info = {
                executor.submit(self._process_page_chunk_first_pass, tab, chunk, idx): (idx, chunk)
                for idx, (tab, chunk) in enumerate(zip(tabs, self.url_chunks))
            }

            for future in concurrent.futures.as_completed(future_to_info):
                idx, chunk = future_to_info[future]
                try:
                    data, alerts, failed_urls = future.result()
                    all_data.update(data)
                    all_alerts.extend(alerts)
                    if failed_urls:
                        all_failed_urls[idx] = failed_urls
                    self._logger.info(f"[标签页 {idx+1}] 第一轮完成，收集 {len(data)} 条，失败 {len(failed_urls)} 个")
                except Exception as e:
                    self._logger.error(f"[标签页 {idx+1}] 处理失败: {e}", exc_info=True)

        # 第二轮重试
        if all_failed_urls:
            total_failed = sum(len(urls) for urls in all_failed_urls.values())
            self._logger.info(f"开始第二轮重试，共 {total_failed} 个失败的 URL...")

            retry_still_failed = 0  # 重试后仍失败的计数

            for tab_idx, failed_urls in all_failed_urls.items():
                if tab_idx < len(tabs):
                    tab = tabs[tab_idx]
                    retry_results = self.scraper.retry_failed_urls(tab, failed_urls, self.url_mapping)

                    # 计算重试后仍失败的数量
                    retry_still_failed += len(failed_urls) - len(retry_results)

                    # 处理重试成功的数据
                    for url_name, file_path in retry_results.items():
                        try:
                            if check_page_validity(str(file_path)):
                                continue
                            
                            output_filename = self.url_mapping.get(url_name, "")
                            currencies = parse_currency_rows(file_path, output_filename)
                            
                            for currency in currencies:
                                all_data[currency.href] = currency
                                alert = self._check_five_minute_alert(currency)
                                if alert:
                                    all_alerts.append(alert)
                                    # 触发信号处理流程（修复：重试数据也需要触发）
                                    self._handle_signal(alert)

                        except Exception as e:
                            self._logger.error(f"[{url_name}] 处理重试数据失败: {e}")

            # 反爬虫检测：计算失败率（基于第一轮失败数，而非总URL数）
            # 只有当第一轮有失败时才检测
            first_round_failed = total_failed  # 第一轮失败的 URL 数量
            failure_rate = retry_still_failed / first_round_failed if first_round_failed > 0 else 0
            
            # 判断 API 是否健康（成功数 > 失败数 且 至少有成功请求）
            api_is_healthy = (self._api_success_count > self._api_failure_count 
                              and self._api_success_count > 0)
            
            # 注意：API 计数器在每轮开始时重置，此处无需再重置
            
            # 条件：重试后仍有 >90% 失败（基于第一轮失败数）
            if first_round_failed > 0 and failure_rate >= 0.9:
                self._consecutive_high_failure_rounds += 1
                self._logger.warning(
                    f"高失败率警告 (第 {self._consecutive_high_failure_rounds} 轮): "
                    f"重试后仍失败 {retry_still_failed}/{first_round_failed} ({failure_rate*100:.1f}%), "
                    f"API健康={api_is_healthy}"
                )
                
                # 条件：连续 2 轮高失败率 且 API 正常 且 距离上次恢复至少 3 轮
                if (self._consecutive_high_failure_rounds >= 2 
                    and api_is_healthy 
                    and self._cycle_count - self._last_recovery_cycle >= 3):
                    
                    self._logger.warning(
                        f"检测到反爬虫限制：连续 {self._consecutive_high_failure_rounds} 轮高失败率，API 正常"
                    )
                    try:
                        self.browser.clear_cookies_and_restart()
                        self._last_recovery_cycle = self._cycle_count
                        self._consecutive_high_failure_rounds = 0  # 重置计数
                        
                        # 发送恢复成功通知
                        self._send_recovery_success_notification()
                                
                    except Exception as e:
                        self._logger.error(f"反爬虫恢复失败: {e}", exc_info=True)
                        self._send_scrape_failure_notification()
            else:
                # 如果本轮失败率正常，重置连续计数
                self._consecutive_high_failure_rounds = 0

        self._logger.info(f"全部抓取完成，共收集 {len(all_data)} 条货币数据")
        return all_data, all_alerts

    def _process_page_chunk_first_pass(self, tab, url_chunk: Dict[str, str], tab_index: int
                                        ) -> Tuple[Dict[str, CurrencyData], List[Alert], Set[str]]:
        """
        第一轮处理：在单个标签页上处理一批 URL

        参数:
            tab: 浏览器标签页
            url_chunk: URL 映射子集
            tab_index: 标签页索引

        返回:
            (货币数据, 告警列表, 失败的 url_name 集合)
        """
        chunk_data: Dict[str, CurrencyData] = {}
        chunk_alerts: List[Alert] = []
        failed_urls: Set[str] = set()

        for url_name, output_filename in url_chunk.items():
            try:
                # 抓取页面
                result = self.scraper.scrape_url(tab, url_name, output_filename)
                output_path, success = result

                if not success or output_path is None:
                    failed_urls.add(url_name)
                    continue

                # 检查页面是否有问题
                if check_page_validity(str(output_path)):
                    self._logger.warning(f"[{url_name}] 页面加载存在问题，标记为失败")
                    failed_urls.add(url_name)
                    continue

                # 解析数据
                currencies = parse_currency_rows(output_path, output_filename)
                
                if not currencies:
                    self._logger.warning(f"[{url_name}] 解析后未获取到任何数据，标记为失败")
                    failed_urls.add(url_name)
                    continue

                # 处理每个货币
                for currency in currencies:
                    chunk_data[currency.href] = currency

                    # 检查 5 分钟告警
                    alert = self._check_five_minute_alert(currency)
                    if alert:
                        chunk_alerts.append(alert)
                        # 触发信号处理流程
                        self._handle_signal(alert)

                self._logger.info(f"[{url_name}] 成功添加 {len(currencies)} 条数据")

            except ScraperError as e:
                failed_urls.add(url_name)
                self._logger.warning(f"[{url_name}] 抓取失败，等待重试: {e}")
            except Exception as e:
                failed_urls.add(url_name)
                self._logger.error(f"[{url_name}] 处理失败: {e}", exc_info=True)

        return chunk_data, chunk_alerts, failed_urls

    def _check_five_minute_alert(self, currency: CurrencyData) -> Optional[Alert]:
        """
        检查货币是否触发 5 分钟告警

        参数:
            currency: 当前货币数据

        返回:
            如果超过阈值返回 Alert，否则返回 None
        """
        # 加载上一轮数据
        previous_data = self.data_store.load_current_data()
        previous = previous_data.get(currency.href)

        if not previous:
            return None

        prev_value_str = previous.get("market_value", "N/A")
        if prev_value_str in ("N/A", "-") or currency.market_value in ("N/A", "-"):
            return None

        prev_value_num = convert_value_to_number(prev_value_str)
        if prev_value_num <= 0:
            return None

        # 计算涨跌幅
        change_rate = ((currency.market_value_num - prev_value_num) / prev_value_num) * 100

        # 根据市值获取阈值
        threshold = self.settings.thresholds.get_threshold(currency.market_value_num)

        # 检查阈值
        if change_rate <= threshold:
            return None
        
        # === 新增过滤规则 ===
        # 规则1：代币市值必须大于 $20K
        MIN_MARKET_CAP = 20_000
        if currency.market_value_num < MIN_MARKET_CAP:
            self._logger.debug(f"[{currency.currency_name}] 市值 ${currency.market_value_num:.0f} < $20K，过滤")
            return None
        
        # 获取链类型
        from core.api_client import DexScreenerAPI
        chain = DexScreenerAPI.detect_chain_from_href(currency.href)
        
        # 如果 CA=Unknown，通过 API 获取 CA
        token_ca = currency.contract_address
        if not token_ca or token_ca == "Unknown":
            # 从 href 提取 pair address
            parts = currency.href.strip("/").split("/")
            pair_address = parts[-1] if len(parts) >= 2 else None
            
            if pair_address:
                token_ca, _ = self.api.get_token_ca_from_pair(pair_address, chain=chain)
                if token_ca:
                    self._logger.info(f"[5m] [{currency.currency_name}] 通过API获取 CA: {token_ca[:20]}...")
                    # 更新到 currency 对象以便后续使用
                    currency.contract_address = token_ca
                else:
                    self._logger.debug(f"[5m] [{currency.currency_name}] 无法获取CA，过滤")
                    return None
            else:
                self._logger.debug(f"[5m] [{currency.currency_name}] 无法解析 pair address，过滤")
                return None
        
        # 规则2：5m 预警需要检查 5m 买入次数 > 10
        api_data = self.api.get_token_data(token_ca, chain=chain)
        if api_data:
            # API 请求成功，递增成功计数（线程安全，用于反爬虫检测）
            self._api_success_count += 1
            
            txns_m5_buys = api_data.get("txns_m5_buys", 0)
            txns_m5_sells = api_data.get("txns_m5_sells", 0)
            
            # 记录 API 数据到日志
            self._logger.info(
                f"[5m] [{currency.currency_name}] API数据: "
                f"5m买入={txns_m5_buys}, 5m卖出={txns_m5_sells}, "
                f"市值=${api_data.get('market_cap', 0):,.0f}"
            )
            
            if txns_m5_buys <= 10:
                self._logger.info(f"[5m] [{currency.currency_name}] 5m买入次数 {txns_m5_buys} <= 10，过滤")
                return None
        else:
            # API 请求失败，递增失败计数
            self._api_failure_count += 1
            self._logger.debug(f"[5m] [{currency.currency_name}] 无法获取API数据，过滤")
            return None

        # 额外过滤：高涨幅但短期波动低的情况
        rates = currency.growth_rates
        if change_rate > 20 and rates.m5 < 10 and rates.h1 < 10:
            return None

        # 统计历史次数
        history_count = self.data_store.count_occurrences(currency.href)

        return Alert(
            currency=currency,
            period_name="5分钟",
            change_rate=change_rate,
            previous_value=prev_value_str,
            current_value=currency.market_value,
            history_count=history_count,
        )

    def _perform_periodic_check(self, period_name: str, interval_minutes: int,
                                 current_data: Dict[str, CurrencyData]) -> List[Alert]:
        """
        执行周期性价格比较

        参数:
            period_name: 周期名称（如 "20分钟"）
            interval_minutes: 间隔分钟数
            current_data: 当前周期的数据

        返回:
            告警列表
        """
        run_interval = interval_minutes // 5
        if self._cycle_count % run_interval != 0:
            return []

        self._logger.info(f"开始 {period_name} 周期对比...")
        alerts = []

        # 加载旧数据
        old_data = self.data_store.load_periodic_data(interval_minutes)

        for href, currency in current_data.items():
            try:
                old_info = old_data.get(href)
                if not old_info:
                    continue

                old_value_str = old_info.get("market_value", "N/A")
                if old_value_str in ("N/A", "-") or currency.market_value in ("N/A", "-"):
                    continue

                old_value_num = convert_value_to_number(old_value_str)
                if old_value_num <= 0:
                    continue

                # 计算涨跌幅
                change_rate = ((currency.market_value_num - old_value_num) / old_value_num) * 100

                # 获取阈值
                threshold = self.settings.thresholds.get_threshold(currency.market_value_num)

                if change_rate > threshold:
                    # === 新增过滤规则 ===
                    # 规则1：代币市值必须大于 $20K
                    MIN_MARKET_CAP = 20_000
                    if currency.market_value_num < MIN_MARKET_CAP:
                        self._logger.debug(f"[{period_name}] [{currency.currency_name}] 市值 ${currency.market_value_num:.0f} < $20K，过滤")
                        continue
                    
                    # 规则2：根据周期检查交易次数
                    # 20分钟预警：5m买入次数 > 10
                    # 1小时/4小时预警：1h买入次数 > 30
                    
                    # 获取链类型
                    from core.api_client import DexScreenerAPI
                    chain = DexScreenerAPI.detect_chain_from_href(currency.href)
                    
                    # 如果 CA=Unknown，通过 API 获取 CA
                    token_ca = currency.contract_address
                    if not token_ca or token_ca == "Unknown":
                        parts = currency.href.strip("/").split("/")
                        pair_address = parts[-1] if len(parts) >= 2 else None
                        
                        if pair_address:
                            token_ca, _ = self.api.get_token_ca_from_pair(pair_address, chain=chain)
                            if token_ca:
                                self._logger.info(f"[{period_name}] [{currency.currency_name}] 通过API获取 CA: {token_ca[:20]}...")
                                currency.contract_address = token_ca
                            else:
                                self._logger.debug(f"[{period_name}] [{currency.currency_name}] 无法获取CA，跳过")
                                continue
                        else:
                            self._logger.debug(f"[{period_name}] [{currency.currency_name}] 无法解析pair，跳过")
                            continue
                    
                    # 获取 API 数据
                    api_data = self.api.get_token_data(token_ca, chain=chain)
                    if not api_data:
                        self._logger.debug(f"[{period_name}] [{currency.currency_name}] 无法获取API数据，跳过预警")
                        continue
                    
                    # 按周期检查交易次数并记录日志
                    if period_name == "20分钟":
                        txns_m5_buys = api_data.get("txns_m5_buys", 0)
                        txns_m5_sells = api_data.get("txns_m5_sells", 0)
                        self._logger.info(
                            f"[{period_name}] [{currency.currency_name}] API数据: "
                            f"5m买入={txns_m5_buys}, 5m卖出={txns_m5_sells}"
                        )
                        if txns_m5_buys <= 10:
                            self._logger.info(f"[{period_name}] [{currency.currency_name}] 5m买入次数 {txns_m5_buys} <= 10，过滤")
                            continue
                    elif period_name in ("1小时", "4小时"):
                        txns_h1_buys = api_data.get("txns_h1_buys", 0)
                        txns_h1_sells = api_data.get("txns_h1_sells", 0)
                        self._logger.info(
                            f"[{period_name}] [{currency.currency_name}] API数据: "
                            f"1h买入={txns_h1_buys}, 1h卖出={txns_h1_sells}"
                        )
                        if txns_h1_buys <= 30:
                            self._logger.info(f"[{period_name}] [{currency.currency_name}] 1h买入次数 {txns_h1_buys} <= 30，过滤")
                            continue
                    
                    history_count = self.data_store.count_occurrences(href, period_name)

                    alert = Alert(
                        currency=currency,
                        period_name=period_name,
                        change_rate=change_rate,
                        previous_value=old_value_str,
                        current_value=currency.market_value,
                        history_count=history_count,
                    )
                    alerts.append(alert)

            except Exception as e:
                self._logger.warning(f"[{period_name}] 比较 {href} 时出错: {e}")

        # 保存当前数据用于下次比较
        self.data_store.save_periodic_data(current_data, interval_minutes)
        self._logger.info(f"{period_name} 周期对比完成，发现 {len(alerts)} 条告警")

        return alerts

    def _alert_to_html(self, alert: Alert) -> str:
        """将告警转换为 HTML 片段用于历史存储"""
        rates = alert.currency.growth_rates.to_dict()
        return (
            f"<p>【{alert.period_name}】{alert.currency.source_file} 中 "
            f"<a href='https://dexscreener.com{alert.currency.href}'>"
            f"{alert.currency.currency_name}</a> "
            f"涨幅: {alert.change_rate:.2f}%</p>"
        )

    def _save_to_database(self, current_data: Dict[str, CurrencyData]) -> None:
        """
        保存数据到数据库
        
        参数:
            current_data: 当前周期的货币数据
        """
        try:
            for href, currency in current_data.items():
                # 获取或创建代币记录
                token_id = self.db.get_or_create_token(
                    href=href,
                    name=currency.currency_name,
                    symbol=currency.currency_name,
                    ca=currency.contract_address if currency.contract_address != "Unknown" else None
                )
                
                # 保存价格快照
                snapshot_data = currency.to_db_snapshot()
                self.db.save_price_snapshot(token_id, snapshot_data)
                
        except Exception as e:
            self._logger.error(f"保存到数据库失败: {e}", exc_info=True)

    def _check_data_cleanup(self) -> None:
        """检查并执行数据清理（保留30天数据）"""
        now = datetime.datetime.now()
        days_since_cleanup = (now - self._last_cleanup).days
        
        if days_since_cleanup >= 1:  # 每天检查一次
            try:
                stats = self.db.cleanup_old_data(days=30)
                self._logger.info(f"数据清理完成: {stats}")
                self._last_cleanup = now
            except Exception as e:
                self._logger.error(f"数据清理失败: {e}")

    def _handle_signal(self, alert: Alert, signal_type_str: str = "5m") -> None:
        """
        处理信号触发（任何周期的价格预警）
        
        创建或更新监控会话，并评估所有策略是否应该买入
        
        参数:
            alert: 触发的告警
            signal_type_str: 信号类型 ("5m", "20m", "1h", "4h")
        """
        try:
            currency = alert.currency
            
            # 获取或创建代币记录
            token_id = self.db.get_or_create_token(
                href=currency.href,
                name=currency.currency_name,
                symbol=currency.currency_name,
                ca=currency.contract_address if currency.contract_address != "Unknown" else None
            )
            
            token_ca = currency.contract_address
            
            # 如果还没有 CA，通过 API 获取（避免浏览器冲突）
            api_market_cap = 0.0
            
            if not token_ca or token_ca == "Unknown":
                self._logger.info(f"代币 {currency.currency_name} 缺少 CA，通过 API 获取...")
                # 从 href 提取 pair address 和链类型
                # href 格式: /solana/xxxxx 或 /bsc/xxxxx
                from core.api_client import DexScreenerAPI
                chain = DexScreenerAPI.detect_chain_from_href(currency.href)
                
                # 提取 pair address（移除链前缀）
                parts = currency.href.strip("/").split("/")
                pair_address = parts[-1] if len(parts) >= 2 else None
                
                if pair_address:
                    # 获取 CA，顺便获取原始数据以复用
                    token_ca, raw_pair_data = self.api.get_token_ca_from_pair(pair_address, chain=chain)
                    
                    if token_ca:
                        self.db.update_token_ca(token_id, token_ca)
                        self._logger.info(f"成功获取 CA: {token_ca[:20]}... (链={chain})")
                        
                        # 尝试从原始数据提取市值
                        if raw_pair_data:
                            api_market_cap = raw_pair_data.get("marketCap", 0) or 0
                            if api_market_cap > 0:
                                self._logger.debug(f"已从 CA查询 预加载市值: ${api_market_cap}")
                    else:
                        self._logger.warning(f"无法获取 CA: {currency.currency_name}")
                        return
                else:
                    self._logger.warning(f"无法解析 pair address: {currency.href}")
                    return
            
            if not token_ca:
                return
            
            # 获取当前价格（使用 HTML 解析，更准确）和市值
            price = 0.0
            html_market_cap = currency.market_value_num  # HTML 解析的市值
            market_cap = html_market_cap  # 默认使用 HTML 市值
            if currency.market_data:
                price = currency.market_data.price
            
            # 尝试从 API 获取市值，并验证与 HTML 市值的差距
            # 如果之前没有预加载到 api_market_cap，则请求 API
            if api_market_cap <= 0:
                # 从 href 检测链类型
                from core.api_client import DexScreenerAPI
                chain = DexScreenerAPI.detect_chain_from_href(currency.href)
                
                # 优化: 只有在未获取到数据时才请求
                api_raw = self.api.get_token_data_raw(token_ca, chain=chain)
                if api_raw and isinstance(api_raw, list) and len(api_raw) > 0:
                    main_pair = api_raw[0]
                    api_market_cap = main_pair.get("marketCap", 0) or 0
            
            # 验证市场一致性
            if api_market_cap > 0:
                if html_market_cap > 0:
                    # 验证市值差距（20%容差）
                    diff_ratio = abs(api_market_cap - html_market_cap) / html_market_cap
                    if diff_ratio <= 0.50:
                        # API 市值有效，使用 API 值
                        market_cap = api_market_cap
                        self._logger.debug(f"API 市值验证通过 (差异{diff_ratio*100:.1f}%): ${market_cap:.0f}")
                    else:
                        # 差异过大，这是虚假信号，跳过处理
                        self._logger.warning(
                            f"API 市值差异过大 ({diff_ratio*100:.1f}%): "
                            f"API=${api_market_cap:.0f} vs HTML=${html_market_cap:.0f}，"
                            f"跳过 {currency.currency_name} 信号 (虚假)"
                        )
                        return  # 不继续处理，跳过
                else:
                    # 没有 HTML 市值可比较，直接使用 API 值
                    market_cap = api_market_cap
            
            # 映射信号类型
            from services.session_manager import SignalType as SessionSignalType
            signal_map = {
                "5m": SessionSignalType.SIGNAL_5M,
                "20m": SessionSignalType.SIGNAL_20M,
                "1h": SessionSignalType.SIGNAL_1H,
                "4h": SessionSignalType.SIGNAL_4H,
            }
            signal_type = signal_map.get(signal_type_str, SessionSignalType.SIGNAL_5M)
            
            # 创建或更新会话
            if self.session_manager:
                session = self.session_manager.create_or_update_session(
                    token_id=token_id,
                    token_ca=token_ca,
                    token_name=currency.currency_name,
                    token_href=currency.href,
                    signal_type=signal_type,
                    trigger_value=alert.change_rate,
                    price=price,
                    market_cap=market_cap,
                )
                
                # 评估所有策略（传递市值、钱包数和当前信号类型）
                wallet_count = 0
                if currency.market_data:
                    wallet_count = currency.market_data.makers_24h or 0
                self._evaluate_strategies(session, market_cap, wallet_count, signal_type_str)
                
                # 发送 Sniper 通知
                if self.sniper_notifier:
                    self._send_sniper_notification(session, signal_type_str, alert)
            
            # 保存信号事件到数据库（用于历史图表标注）
            try:
                self.db.create_signal_event(
                    token_id=token_id,
                    signal_type=signal_type_str,
                    trigger_value=alert.change_rate,
                    market_cap_at_trigger=market_cap,
                    price_at_trigger=price
                )
                self._logger.debug(f"信号事件已保存: {currency.currency_name} - {signal_type_str}")
            except Exception as db_err:
                self._logger.warning(f"保存信号事件失败: {db_err}")
            
            self._logger.info(
                f"信号处理完成 [{currency.currency_name}]: {signal_type_str}, "
                f"涨幅={alert.change_rate:.1f}%"
            )
            
        except Exception as e:
            self._logger.error(f"处理信号失败: {e}", exc_info=True)

    def _evaluate_strategies(self, session, current_market_cap: float,
                             wallet_count: int = 0, current_signal_type: str = "5m") -> None:
        """
        评估所有策略是否应该买入
        
        参数:
            session: 监控会话
            current_market_cap: 当前市值（用于买入记录）
            wallet_count: 24小时交易钱包数 (makers_24h)
            current_signal_type: 当前正在处理的信号类型 ("5m", "20m", "1h", "4h")
        """
        if not self.strategies:
            return
        
        session_data = session.to_session_data()
        
        # === 新增：添加当前信号类型（区分当前触发 vs 历史信号）===
        session_data["current_signal_type"] = current_signal_type
        
        # === 新增：为高级策略提供额外数据 ===
        # 0. 添加钱包数（策略Alpha需要）
        session_data["wallet_count"] = wallet_count
        
        # 1. 添加会话最高市值（策略H需要）
        session_data["highest_market_cap"] = session.highest_market_cap
        
        # 2. 获取 API 数据（多个策略需要）- 如果已有则跳过
        # TODO: 可优化 - 在 _handle_signal 中已调用 get_token_data_raw() 获取过市值，
        #       可以复用该数据减少 API 请求。当前保持两次请求以获取更实时的数据，
        #       且 API 请求频率远未达到限制。
        if "api_data" not in session_data:
            try:
                # 从 href 检测链类型
                from core.api_client import DexScreenerAPI
                chain = DexScreenerAPI.detect_chain_from_href(session.token_href)
                api_data = self.api.get_token_data(session.token_ca, chain=chain)
                if api_data:
                    session_data["api_data"] = api_data
            except Exception as e:
                self._logger.debug(f"获取API数据失败: {e}")
        

        # 评估所有策略并缓存结果（避免重复调用 should_buy）
        strategy_results = {}  # {strategy_type: (triggered: bool, strategy: obj)}
        strategy_triggers = []
        
        for st_type, strategy in self.strategies.items():
            try:
                triggered = strategy.should_buy(session.token_id, session.token_ca, session_data)
                strategy_results[st_type] = (triggered, strategy)
                strategy_triggers.append(f"{st_type.value}={'Y' if triggered else 'N'}")
            except Exception as e:
                strategy_results[st_type] = (False, strategy)
                strategy_triggers.append(f"{st_type.value}=E")  # E = Error
                self._logger.debug(f"策略{st_type.value} should_buy 异常: {e}")
        
        # 格式化市值
        mc = session_data.get("current_market_cap", 0)
        if mc >= 1_000_000:
            mc_str = f"${mc/1_000_000:.2f}M"
        elif mc >= 1_000:
            mc_str = f"${mc/1_000:.1f}K"
        else:
            mc_str = f"${mc:.0f}"
        
        _alerts_logger.info(
            f"{session_data.get('signals', [{}])[-1].get('type', 'unknown') if session_data.get('signals') else 'N/A'} | "
            f"{session.token_name} | 热度={session_data.get('heat_score', 0):.0f} | "
            f"市值={mc_str} | 策略触发: {', '.join(strategy_triggers)}"
        )
        
        # 使用缓存的结果执行买入（避免重复调用 should_buy）
        for st_type, (triggered, strategy) in strategy_results.items():
            if not triggered:
                continue
            
            try:
                result = strategy.execute_buy(
                    session.token_id,
                    session.token_ca,
                    session.token_name,
                    current_market_cap,  # 传递市值而非价格
                    session_data  # 传递 session_data 用于全局检查
                )
                
                if result:
                    self._logger.info(
                        f"🎯 策略{st_type.value} 买入 {session.token_name}"
                    )
                    
                    # 发送 Sniper 买入通知
                    if self.sniper_notifier:
                        # 格式化市值
                        if current_market_cap >= 1_000_000:
                            mc_str = f"${current_market_cap/1_000_000:.2f}M"
                        elif current_market_cap >= 1_000:
                            mc_str = f"${current_market_cap/1_000:.1f}K"
                        else:
                            mc_str = f"${current_market_cap:.0f}"
                        
                        suffix = self.STRATEGY_SUFFIXES.get(st_type.value, '')
                        buy_msg = (
                            f"🎯 【策略{st_type.value}{suffix}买入】{session.token_name}\n"
                            f"📊 市值: {mc_str}\n"
                            f"📝 CA: <code>{session.token_ca}</code>\n"
                            f"💰 金额: {strategy.config.trade_amount_sol} SOL\n"
                            f"💵 余额: {strategy.state.balance_sol:.2f} SOL"
                        )
                        
                        try:
                            # 尝试发送通知
                            try:
                                loop = asyncio.get_running_loop()
                                # 已有事件循环，创建任务
                                loop.create_task(self.sniper_notifier.send_raw_message(buy_msg))
                            except RuntimeError:
                                # 没有运行中的事件循环，用 asyncio.run
                                asyncio.run(self.sniper_notifier.send_raw_message(buy_msg))
                            self._logger.info(f"✅ 已发送买入通知: {session.token_name}")
                        except Exception as notify_err:
                            self._logger.error(f"发送买入通知失败: {notify_err}")
            except Exception as e:
                self._logger.error(f"策略{st_type.value}执行买入失败: {e}")


    def _send_sniper_notification(self, session, signal_type: str, alert: Alert) -> None:
        """发送 Sniper 通知"""
        try:
            # 格式化市值显示
            market_cap = alert.currency.market_value_num
            if market_cap >= 1_000_000:
                mc_str = f"${market_cap/1_000_000:.2f}M"
            elif market_cap >= 1_000:
                mc_str = f"${market_cap/1_000:.1f}K"
            else:
                mc_str = f"${market_cap:.0f}"
            
            msg = (
                f"🎯 【{signal_type}信号】{alert.currency.currency_name}\n"
                f"CA: <code>{session.token_ca}</code>\n"
                f"涨幅: {alert.change_rate:.1f}%\n"
                f"市值: {mc_str}\n"
                f"热度: {session.heat_score:.0f}\n"
                f"剩余追踪: {session.remaining_life_seconds//60}分钟"
            )
            asyncio.run(self.sniper_notifier.send_raw_message(msg))
        except Exception as e:
            self._logger.error(f"发送 Sniper 通知失败: {e}")

    def _send_scrape_failure_notification(self) -> None:
        """
        发送 DEX 抓取失败通知
        在反爬虫恢复尝试后仍然抓取失败时调用
        包含 30 分钟冷却期，防止频繁通知
        """
        try:
            # 冷却期检查：30分钟内只发一次通知
            now = datetime.datetime.now()
            if self._last_failure_notification_time:
                elapsed = (now - self._last_failure_notification_time).total_seconds()
                if elapsed < 1800:  # 30分钟 = 1800秒
                    self._logger.warning(
                        f"抓取失败通知冷却中 (剩余 {(1800-elapsed)/60:.0f} 分钟)，跳过发送"
                    )
                    return
            
            msg = (
                "⚠️ 【DEX 抓取失败】\n"
                "网页抓取连续失败，可能触发了反爬虫限制。\n"
                "已尝试清除 Cookies 并重启标签页，但仍然无法正常抓取。\n"
                "请检查浏览器状态或手动重启程序。"
            )
            self._logger.error("DEX 抓取持续失败，发送告警通知")
            
            # 优先使用 sniper_notifier，其次使用普通 notifier
            if self.sniper_notifier:
                asyncio.run(self.sniper_notifier.send_raw_message(msg))
            elif self.notifier:
                asyncio.run(self.notifier.send_raw_message(msg))
            
            # 更新通知时间
            self._last_failure_notification_time = now
            
        except Exception as e:
            self._logger.error(f"发送抓取失败通知时出错: {e}", exc_info=True)

    def _send_recovery_success_notification(self) -> None:
        """
        发送反爬虫恢复成功通知
        """
        try:
            msg = (
                "✅ 【DEX 恢复成功】\n"
                "已成功清除 Cookies 并重启标签页。\n"
                "抓取功能将在下一轮恢复正常。"
            )
            self._logger.info("反爬虫恢复完成，发送成功通知")
            
            if self.sniper_notifier:
                asyncio.run(self.sniper_notifier.send_raw_message(msg))
            elif self.notifier:
                asyncio.run(self.notifier.send_raw_message(msg))
                
        except Exception as e:
            self._logger.error(f"发送恢复成功通知时出错: {e}", exc_info=True)

    def check_all_strategy_exits(self) -> None:
        """检查所有策略的止盈止损（基于市值）"""
        if not self.strategies or not self.session_manager:
            return
        
        current_market_caps = self.session_manager.get_current_market_caps()
        
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
                for result in results:
                    if self.sniper_notifier:
                        action = result.get("action", "EXIT")
                        token_name = result.get("token_name", "Unknown")
                        pnl = result.get("pnl", 0)
                        pnl_pct = result.get("pnl_percent", 0)
                        
                        emoji = "🎉" if pnl > 0 else "❌"
                        balance = strategy.state.balance_sol
                        token_ca = result.get("token_ca", "")
                        
                        suffix = self.STRATEGY_SUFFIXES.get(st_type.value, '')
                        exit_msg = (
                            f"{emoji} 【策略{st_type.value}{suffix} {action}】{token_name}\n"
                            f"CA: <code>{token_ca}</code>\n"
                            f"PNL: {pnl:+.4f} SOL ({pnl_pct:+.1f}%)\n"
                            f"💵 余额: {balance:.2f} SOL"
                        )
                        try:
                            loop = asyncio.get_running_loop()
                            loop.create_task(self.sniper_notifier.send_raw_message(exit_msg))
                        except RuntimeError:
                            asyncio.run(self.sniper_notifier.send_raw_message(exit_msg))
            except Exception as e:
                self._logger.error(f"策略{st_type.value}止盈止损检查失败: {e}")
    


