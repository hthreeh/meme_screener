# DEX 价格监控系统 - 项目分析报告

---

## 1. 项目概述

### 1.1 项目用途

本项目是一个 **DEX（去中心化交易所）价格监控与多策略模拟交易系统**，主要功能包括：

- 从 **DexScreener** 抓取并解析加密货币价格与市值数据（支持网页抓取与 API）。
- 按多时间周期（5 分钟、20 分钟、1 小时、4 小时）检测价格异动并产生告警。
- 通过 **Telegram** 与 **飞书** 发送预警通知（含 Scanner 通道与 Sniper 通道）。
- 多策略模拟交易：多套独立策略（A/B/C/D/E/F/G/H/I/Alpha/手动），各有独立资金池与止盈止损规则，基于「信号 → 会话 → 策略评估 → 买入/持仓 → 止盈止损」闭环运行。
- 提供 **Web 看板**（React + FastAPI）查看策略状态、持仓、交易历史与代币历史数据，并支持手动买入/卖出队列。

### 1.2 技术栈

| 层级     | 技术 |
|----------|------|
| 后端     | Python 3.10+、FastAPI、uvicorn、APScheduler、SQLite |
| 数据获取 | DrissionPage（Chromium）、DexScreener API、BeautifulSoup |
| 通知     | Telegram Bot API、飞书 Webhook（邮件已禁用） |
| 前端     | React 18、TypeScript、Vite、Ant Design |
| 部署     | Docker / Docker Compose、Jenkins CI/CD、Nginx（前端） |

### 1.3 整体数据/请求流

- **监控主循环**：定时（默认每 5 分钟）跑一轮 `PriceMonitor.run_cycle()` → 多标签页并行抓取 DexScreener 收藏夹页面 → 解析 HTML 得到代币列表 → 与上一轮/历史周期数据比较 → 超阈值则生成告警并触发信号处理。
- **信号处理**：告警触发后 `_handle_signal()` → 获取/补全代币 CA、市值校验 → 创建/更新 `SessionManager` 的监控会话 → `_evaluate_strategies()` 调用各策略 `should_buy()` → 若某策略命中则模拟买入并写入 DB，同时可选发送 Sniper 通知。
- **持仓与止盈止损**：`PositionTracker` 独立线程按间隔（如 60 秒）轮询所有策略持仓的当前市值 → 调用各策略 `check_and_execute_exits()` → 触达止盈/止损/超时则模拟卖出并写库，并通过 `on_exit_callback` 发 Sniper 通知。
- **手动交易**：前端提交买入/卖出 → FastAPI 写入 `manual_buy_queue` / `manual_sell_queue` → `PositionTracker` 轮询中处理队列，调用策略或 API 完成模拟买入/卖出并更新状态。
- **前端**：React 周期请求 `/api/dashboard`、策略、持仓、交易等 REST 接口展示看板；历史数据、导出等通过 REST 完成。（代码中未见 WebSocket 在业务上的使用，仅依赖轮询或静态资源。）

---

## 2. 架构与模块划分

### 2.1 目录职责

| 目录/文件        | 职责 |
|------------------|------|
| `dex_price/main.py` | 进程入口：加载配置、初始化 DB/API/浏览器/通知/策略/会话管理器/持仓追踪器/价格监控器，注册并启动调度器。 |
| `dex_price/config/` | 配置：`AppSettings`、通知与策略等 JSON 加载、`url_mappings.json`（收藏夹名称 → 本地 HTML 文件名）。 |
| `dex_price/core/`   | 核心能力：浏览器管理、页面抓取、HTML 解析、DexScreener API、CA 获取、DB 访问、信号引擎（快速采集与验证）。 |
| `dex_price/services/` | 业务服务：价格监控、数据存储（JSON）、通知、会话管理、持仓追踪、多策略交易逻辑。 |
| `dex_price/scheduler/` | 定时任务：APScheduler 封装，按配置间隔执行 `run_cycle`。 |
| `dex_price/models/`   | 数据模型：`CurrencyData`、`GrowthRates`、`MarketData`、`Alert` 等。 |
| `dex_price/api/`      | FastAPI 应用与路由：看板、代币、信号、策略、交易、历史。 |
| `dex_price/utils/`     | 工具：市值/价格字符串解析、页面有效性检查、日志配置等。 |
| `dex_price/scripts_root/` | 运维脚本：初始化 DB 表、清理数据、分析、手动触发、重置、启动/停止看板、部署批处理。 |
| `dex_price/web/`      | 前端：Vite + React + TypeScript，看板、策略卡片、持仓表、交易历史、历史数据与手动交易。 |
| `dex_price/deploy/`    | Docker 与 Nginx 配置。 |
| `dex_price/tests/`、`tests_root/` | 策略与通知等测试。 |

### 2.2 模块依赖关系（简要）

- `main.py` 依赖：`config`、`core.*`、`services.*`、`scheduler`、`utils.logging_config`。
- `PriceMonitor` 依赖：`core`（browser, scraper, parser, database, api_client, ca_fetcher）、`services`（notifier, data_store）、`models.currency`、`utils.helpers`；并持有 `strategies`、`session_manager`。
- `SessionManager` 依赖：`core.database`、`core.api_client`。
- `PositionTracker` 依赖：`core.api_client`、各策略实例（用于持仓收集与止盈止损）、`db`（缓存市值、写历史、手动单队列）。
- 策略层（`trading_strategies`）依赖：`core.database`、`core.api_client`。
- API 层依赖：`core.database`、`config.settings`（DB_PATH），无直接依赖监控/策略运行时对象，仅读写 DB 与队列表。

---

## 3. 核心模块说明

### 3.1 core 包

#### 3.1.1 browser.py — 浏览器管理

- **职责**：管理 DrissionPage Chromium 生命周期与多标签页，用于 DexScreener 页面抓取。
- **主要接口**：`start()` 打开浏览器并创建多个标签页指向 `base_url`；`get_tabs()` 返回标签页列表；`restart_tabs()` 关闭并重新打开所有标签页（防长时间运行内存问题）；`clear_cookies_and_restart()` 清 Cookie 并重启标签页（应对反爬）；`stop()` 关闭所有标签页并退出浏览器。
- **实现要点**：使用 `Chromium()` 与 `new_tab()`，每页 `get(url)` 后 `page_load_wait` 等待；CDP 清 Cookie/Cache。
- **关键依赖**：`DrissionPage`、`config.settings.AppSettings`。

#### 3.1.2 scraper.py — 页面抓取

- **职责**：在单个标签页上按「收藏夹名称 → 输出文件名」抓取指定 URL：点击收藏夹项、点击市值列排序、等待表格数据加载、保存 HTML。
- **主要接口**：`scrape_url(page, url_name, output_filename)` → `(Path|None, bool)`；`scrape_chunk_with_retry()` 一批 URL 首次抓取并返回失败集合；`retry_failed_urls()` 对失败 URL 重试。
- **实现要点**：通过 `REQUIRED_MARKER`（如 `"ds-dex-table-row ds-dex-table-row-top"`）轮询判断加载完成；超时 `MAX_LOAD_WAIT_SECONDS`；自定义异常 `ScraperError`。
- **关键依赖**：`DrissionPage.ChromiumPage`、`config.settings.AppSettings`。

#### 3.1.3 parser.py — HTML 解析

- **职责**：从保存的 HTML 中解析出代币表格行，得到 `CurrencyData` 列表。
- **主要接口**：`parse_currency_rows(file_path, source_file)` → `List[CurrencyData]`。
- **实现要点**：BeautifulSoup 查找 `class_="ds-dex-table-row"`；从行内提取 href、名称、涨跌幅（5M/1H/6H/24H）、市值、价格/流动性/成交量/交易次数/钱包数/交易对年龄等；合约地址从图片 URL 正则提取（`tokens/solana/{address}.png`）。
- **关键依赖**：`bs4`、`models.currency`、`utils.helpers.convert_value_to_number`。

#### 3.1.4 database.py — 数据库管理

- **职责**：SQLite 持久化，管理代币、价格快照、信号事件、信号跟踪、模拟交易、策略状态与持仓、API 缓存、API 历史、手动买卖队列等表。
- **主要接口**：大量方法，例如：`get_or_create_token`、`save_price_snapshot`、`create_signal_event`、`update_signal_validation`、`save_strategy_state`、`load_positions`、`save_position`、`cache_api_data`、`insert_api_history`、`add_manual_order`、`get_pending_manual_orders`、`mark_manual_order_done`/`failed` 等。
- **实现要点**：`get_connection()` 上下文管理器，`row_factory=sqlite3.Row`；建表与索引在 `_init_tables()`；唯一冲突时先查后插或 ON CONFLICT 更新。
- **关键依赖**：无第三方业务库，仅标准库 `sqlite3`。

#### 3.1.5 api_client.py — DexScreener API

- **职责**：调用 DexScreener API 获取代币/交易对数据，并做全局限流。
- **主要接口**：`get_token_data(ca, chain)`、`get_token_data_raw(ca, chain)`、`get_token_ca_from_pair(pair_address, chain)`、`get_signal_tracking_data(ca)`；静态方法 `detect_chain_from_href(href)`。
- **实现要点**：`APIRateLimiter` 滑动窗口（默认 300 次/60 秒）；`_make_request_with_retry()` 重试与 429 退避；支持链如 solana/bsc/ethereum/base/arbitrum；响应解析兼容 `pair` 与 `pairs` 两种格式。
- **关键依赖**：`urllib.request`、标准库。

#### 3.1.6 ca_fetcher.py — 合约地址获取

- **职责**：用无头浏览器打开代币详情页，从页面元素或 HTML 中提取 Solana 合约地址（CA）。
- **主要接口**：`get_ca(href)`、`get_ca_batch(hrefs)`；`_extract_ca_from_page(tab)`、`_is_valid_solana_address(address)`。
- **实现要点**：多选择器尝试（如 `.chakra-text.custom-72rvq0`、`span[title]`）；Base58 校验与长度 40–50；可选的正则兜底。
- **关键依赖**：`DrissionPage`。

#### 3.1.7 signal_engine.py — 信号引擎

- **职责**：信号触发后的快速数据采集（如 5 分钟内每分钟一次）与多维度验证（价格/成交量/买卖比），过滤虚假信号。
- **主要接口**：`on_signal_triggered(token_id, token_ca, signal_type, trigger_value, market_cap, price, callback)` → signal_id；内部 `_start_rapid_collection`、`_validate_signal()`。
- **实现要点**：后台线程跑采集循环；用 `DexScreenerAPI.get_signal_tracking_data()` 取点；趋势分析、虚假信号检测（大跌、卖压过大、量骤降）、评分与 `should_trade`；结果写 DB 并回调。
- **关键依赖**：`core.api_client`、`core.database`。

### 3.2 services 包

#### 3.2.1 price_monitor.py — 价格监控

- **职责**：协调整轮监控：加载 URL 映射、多标签页并行抓取与重试、解析、5 分钟与多周期比较、告警汇总、写库、信号处理、策略评估、通知与数据清理。
- **主要入口**：`run_cycle()`（由调度器周期性调用）。
- **实现要点**：`url_mapping` 按 `num_pages` 分块，每块对应一标签页；`_scrape_all_pages_with_retry()` 用 `ThreadPoolExecutor` 第一轮并行抓取，再对失败 URL 重试；`_check_five_minute_alert()` 与 `_perform_periodic_check()` 产生告警；5 分钟告警过滤（市值≥20K、5m 买入>10 等）；`_save_to_database()` 为每个 href 做 get_or_create_token + save_price_snapshot；`_handle_signal()` 补 CA、市值校验、创建/更新会话、`_evaluate_strategies()`、写 signal_events、可选 Sniper 通知；`_evaluate_strategies()` 调用各策略 `should_buy()`，触发则执行策略的模拟买入；反爬与 API 健康统计、周期性清理 30 天前数据。
- **关键依赖**：`core` 多模块、`services.notifier`、`services.data_store`、`models.currency`、`utils.helpers`。

#### 3.2.2 data_store.py — 数据存储（JSON）

- **职责**：当前周期数据、各周期比较数据、通知历史的 JSON 文件读写。
- **主要接口**：`save_current_data`、`load_current_data`、`save_periodic_data`、`load_periodic_data`、`save_notification_history`、`load_notification_history`、`count_occurrences`。
- **实现要点**：路径为 `data_dir/currency_value_data.json`、`currency_value_data_{interval}min.json`、`email_results.json`；通知历史仅保留最近 20 批。
- **关键依赖**：`models.currency.CurrencyData`。

#### 3.2.3 notifier.py — 通知服务

- **职责**：统一通过 Telegram 与飞书发送告警与错误；支持「原始消息」用于 Sniper 通道。
- **主要接口**：`send_all(alerts, cycle_count, timestamp)`、`send_error_notification(error_message, subject)`、`send_raw_message(message)`。
- **实现要点**：告警按条数分块（Telegram 每条约 5 条、飞书约 10 条）；Telegram 使用 `telegram` 库与 `HTTPXRequest`；飞书 POST webhook；邮件相关已注释。
- **关键依赖**：`telegram`、`requests`、`config.settings`、`models.currency.Alert`。

#### 3.2.4 session_manager.py — 会话管理

- **职责**：管理「监控会话」：信号触发后为代币创建/更新会话，维护热度、剩余寿命、轮询间隔与 API 采样；独立线程按 `next_poll_time` 轮询会话并更新市值/热度/寿命，到期或条件满足时结束会话。
- **主要接口**：`start()`、`stop()`、`create_or_update_session(token_id, token_ca, token_name, token_href, signal_type, trigger_value, price, market_cap)`；内部维护 `MonitoringSession` 与 `SignalRecord`。
- **实现要点**：根据信号类型与市值区间计算 `life_add`、`heat_add`、统一轮询间隔；会话存于内存字典；后台线程循环处理会话列表。
- **关键依赖**：`core.database`、`core.api_client`。

#### 3.2.5 position_tracker.py — 持仓追踪

- **职责**：独立于会话，汇总所有策略持仓，定时轮询 API 获取当前市值，调用各策略止盈止损逻辑，处理手动买卖队列。
- **主要接口**：`start()`、`stop()`；内部 `_run_loop()`、`_poll_all_positions()`、`_process_manual_orders()`、`_process_manual_sell_orders()`。
- **实现要点**：`_collect_all_positions()` 从各策略 state.positions 收集；对每个持仓请求 `get_token_data_raw()` 取市值并写 `api_data_cache` 与 `api_history`；然后对各策略 `check_and_execute_exits(current_market_caps)`；在等待间隔内每秒处理 manual_buy_queue 与 manual_sell_queue。
- **关键依赖**：`core.api_client`、各策略实例、`db`、`on_exit_callback`。

#### 3.2.6 trading_strategies.py — 多策略交易

- **职责**：定义策略类型（A/B/C/D/E/F/G/H/I/Alpha/M）、策略配置与状态、持仓结构；实现各策略的 `should_buy()` 与 `check_and_execute_exits()`；止盈阶梯、移动止损、超时/横盘离场；状态与持仓持久化到 DB。
- **主要接口**：`create_all_strategies(db, api, strategies_config)` → `Dict[StrategyType, TradingStrategy]`；各策略 `should_buy(token_id, token_ca, session_data)`、`check_and_execute_exits(current_market_caps)`；`Position`、`StrategyState`、`StrategyConfig`。
- **实现要点**：基类 `TradingStrategy` 定义止盈档位（如 1.5x 卖 50%、3x 再 30%、10x 清仓）、止损 -30%、移动止损（涨 30% 保本、涨 80% 锁 1.5x）；子类实现不同入场条件（热度、信号组合、API 涨幅等）；持仓 `remaining_ratio`、`take_profit_level`、`trailing_stop_multiplier`、`highest_multiplier`、超时与亏损比例判断；买入/卖出时写 `strategy_trades`、更新 `strategy_states` 与 `strategy_positions`。
- **关键依赖**：`core.database`、`core.api_client`。

### 3.3 scheduler 包

- **职责**：使用 APScheduler 的 BlockingScheduler，按 `task_interval_minutes` 定时执行注册的 `run_cycle`；支持首次立即执行。
- **主要接口**：`register_task(task_func)`、`start(run_immediately=True)`、`stop()`；内部 `_safe_task()` 捕获异常不中断调度，`_handle_fatal_error()` 发通知并 `sys.exit(1)`。
- **关键依赖**：`apscheduler`、`pytz`（Asia/Shanghai）、`config.settings`、`services.notifier`。

### 3.4 api 包（FastAPI）

- **职责**：提供 REST 与前端所需的数据接口；不直接持有监控/策略实例，仅读写 DB 与队列表。
- **入口**：`api/main.py` 创建 FastAPI 应用，挂 CORS，注册各路由；`uvicorn.run("api.main:app", host="0.0.0.0", port=8000)`。
- **路由概览**：
  - `api/routes/dashboard.py`：看板汇总（策略余额/盈亏/持仓数、24h 交易/信号/盈亏、最近交易）。
  - `api/routes/tokens.py`：代币列表、代币历史、最新数据、持仓代币等。
  - `api/routes/signals.py`：信号列表、统计、类型。
  - `api/routes/strategies.py`：策略列表、策略详情（含持仓）、持仓列表。
  - `api/routes/trades.py`：交易历史、统计、按策略统计、手动买入/卖出（写队列）。
  - `api/routes/history.py`：历史数据（api_history 等）、导出 CSV。
- **实现要点**：统一使用 `config.settings.DB_PATH` 初始化 `DatabaseManager`；时间展示转为上海时区；手动交易为 POST 写 `manual_buy_queue` / `manual_sell_queue`，由 PositionTracker 异步消费。

### 3.5 前端（web/src）

- **职责**：看板页展示总余额/总盈亏/持仓数、策略卡片、持仓表、交易历史、代币历史数据与手动交易入口。
- **主要文件**：
  - `App.tsx`：布局、Header 统计、Tabs（策略概览 / 交易历史 / 历史数据），30 秒轮询 `getDashboard()`。
  - `services/api.ts`：封装所有 REST 调用与类型（Dashboard、Strategy、Position、Trade、Signal、Token、History、ManualOrder 等）。
  - `components/StrategyDashboard.tsx`：请求 `getStrategies()`，展示策略卡片与 `ManualTrade`。
  - `components/PositionTable.tsx`：展示持仓，可点击代币跳转历史；依赖策略与持仓接口。
  - `components/TradeHistory.tsx`：交易历史列表。
  - `components/HistoryData.tsx`：历史数据（按代币查历史点、信号、交易）。
  - `components/ManualTrade.tsx`：手动买入（CA + 金额）/ 卖出（策略+token_id）表单与提交。
- **实现要点**：`API_BASE` 使用 `import.meta.env.VITE_API_URL` 或 `http://${hostname}:8000/api`；Ant Design 组件；无 WebSocket 业务逻辑，依赖轮询。

### 3.6 config、models、utils

- **config/settings.py**：`AppSettings`（浏览器数、重启间隔、base_url、task_interval_minutes、check_intervals、data_dir、阈值、通知与策略配置）、`load_settings()`、`load_url_mappings()`；`DB_PATH`。
- **models/currency.py**：`GrowthRates`、`MarketData`、`CurrencyData`、`Alert`；`to_dict()`、`to_db_snapshot()` 等。
- **utils/helpers.py**：`convert_value_to_number()`（K/M/B、下标数字等）、`check_page_validity()` 等；**utils/logging_config.py**：文件日志等。

---

## 4. 关键流程

### 4.1 价格监控流程

1. **调度触发**：`TaskScheduler` 每 `task_interval_minutes`（默认 5 分钟）调用 `PriceMonitor.run_cycle()`（见 `main.py:163-165`、`scheduler/task_scheduler.py:72-74`）。
2. **重载 URL 映射**：`_reload_url_mappings()` 从 `config/url_mappings.json` 重载并重新分块（`price_monitor.py:128-129`）。
3. **可选重启标签页**：若达到 `browser_restart_interval` 周期则 `browser.restart_tabs()`（`price_monitor.py:133-134`）。
4. **并行抓取与重试**：`_scrape_all_pages_with_retry()` 使用 `ThreadPoolExecutor`，每个 worker 执行 `_process_page_chunk_first_pass(tab, chunk, idx)`：对 chunk 内每个 url_name 调用 `scraper.scrape_url()`，保存 HTML；`check_page_validity()`；`parse_currency_rows()`；对每个 currency 做 5 分钟告警检查 `_check_five_minute_alert()`，若告警则 `_handle_signal(alert)`（`price_monitor.py:223-406`）。首轮失败 URL 收集后再 `retry_failed_urls()`。
5. **保存与周期比较**：`data_store.save_current_data(current_data)`；`_save_to_database(current_data)`（get_or_create_token + save_price_snapshot）；对 20 分钟/1 小时/4 小时执行 `_perform_periodic_check()`，产生告警并同样 `_handle_signal(alert, signal_type_str)`（`price_monitor.py:157-178`）。
6. **通知与清理**：若有告警则 `notifier.send_all(...)`；`save_notification_history`；每 30 天执行 `cleanup_old_data(30)`（`price_monitor.py:181-186`、`676-687`）。

### 4.2 信号处理与策略买入流程

1. **入口**：任一轮告警（5m/20m/1h/4h）触发 `_handle_signal(alert, signal_type_str)`（`price_monitor.py:690`）。
2. **代币与 CA**：`get_or_create_token()`；若 CA 缺失则用 `api.get_token_ca_from_pair()` 或已有逻辑补全并 `update_token_ca()`（`price_monitor.py:703-748`）。
3. **市值校验**：HTML 市值与 API 市值比较，差异过大则视为虚假信号并 return（`price_monitor.py:771-789`）。
4. **会话**：`session_manager.create_or_update_session(...)` 创建或更新 `MonitoringSession`（`price_monitor.py:804-814`）。
5. **策略评估**：`_evaluate_strategies(session, market_cap, wallet_count, signal_type_str)`：为 session 补 `api_data` 等，对每个策略调用 `strategy.should_buy(token_id, token_ca, session_data)`；若触发则执行该策略的模拟买入（写持仓、扣余额、写 strategy_trades、保存 state/position 到 DB）（`price_monitor.py:848-899` 及 trading_strategies 内执行逻辑）。
6. **Sniper 通知与事件**：若配置了 `sniper_notifier` 则 `_send_sniper_notification(...)`；`db.create_signal_event(...)`（`price_monitor.py:822-837`）。

### 4.3 持仓与止盈止损流程

1. **PositionTracker 启动**：`main.py` 中创建 `PositionTracker(strategies, api, db, on_exit_callback)` 并 `start()`（`main.py:140-146`）。
2. **循环**：`_run_loop()` 每 `POLL_INTERVAL`（60 秒）执行 `_poll_all_positions()`，中间每秒处理手动买卖队列（`position_tracker.py:69-96`）。
3. **轮询持仓**：`_collect_all_positions()` 从各策略 `state.positions` 收集；对每个持仓用 `api.get_token_data_raw(token_ca, chain)` 取当前市值；写 `db.cache_api_data()` 与 `db.insert_api_history()`；汇总 `current_market_caps`（`position_tracker.py:118-187`）。
4. **止盈止损**：对每个策略 `strategy.check_and_execute_exits(current_market_caps)`：遍历该策略持仓，用当前市值算倍数、更新移动止损与超时计数，判断是否止盈/止损/超时离场；若卖出则更新余额、写 strategy_trades、删持仓、保存状态，并返回 result 列表（`trading_strategies` 中实现）。
5. **回调**：若有 result，`on_exit_callback(st_type, result)` 被调用，发送 Sniper 通知（`main.py:111-137`、`position_tracker.py:193-197`）。

### 4.4 前端展示与手动交易流程

1. **看板加载**：`App.tsx` 挂载时 `getDashboard()`，并每 30 秒轮询；Tab 切换后各子组件自行请求（如 `getStrategies()`、持仓、交易历史）（`App.tsx:36-49`、`StrategyDashboard.tsx` 等）。
2. **手动买入**：用户在前端输入 CA 与金额 → `createManualOrder(ca, amount)` POST `/api/trades/manual` → 后端在 `manual_buy_queue` 插入 PENDING 记录；PositionTracker 在 `_process_manual_orders()` 中读取 PENDING 订单并执行策略 M 的买入逻辑，更新队列状态（`api/routes/trades.py`、`position_tracker.py` 中处理逻辑）。
3. **手动卖出**：用户选择策略与 token_id → `createManualSellOrder(strategyType, tokenId)` POST `/api/trades/manual-sell` → 后端写入 `manual_sell_queue`；PositionTracker 的 `_process_manual_sell_orders()` 消费并执行对应策略的卖出（更新持仓与余额、写 strategy_trades）。

---

## 5. 数据与接口

### 5.1 主要数据结构（DB 与内存）

- **tokens**：id, ca, href, name, symbol, first_seen, last_updated。
- **price_snapshots**：token_id, price, market_cap, liquidity, volume_24h, txns_24h, makers_24h, growth_5m/1h/6h/24h, source_file, timestamp。
- **signal_events**：token_id, signal_type, trigger_value, market_cap_at_trigger, price_at_trigger, is_validated, validation_result, created_at。
- **signal_tracking**：signal_event_id, price, volume_5m, txns_5m_buys/sells, minute_offset, timestamp。
- **strategy_states**：strategy_type, balance_sol, total_trades, winning_trades, losing_trades, total_pnl, last_updated。
- **strategy_positions**：strategy_type, token_id, token_ca, token_name, buy_market_cap, buy_amount_sol, buy_time, remaining_ratio, highest_multiplier, take_profit_level, poll_count, loss_check_count, trailing_stop_multiplier。
- **strategy_trades**：strategy_type, token_ca, token_name, action, price, amount, pnl, timestamp。
- **api_data_cache** / **api_history**：按 token 的 API 快照与历史（价格、成交量、买卖笔数等）。
- **manual_buy_queue** / **manual_sell_queue**：status, token_ca/strategy_type+token_id, amount_sol 等，processed_at。

前端类型与上述对应：`DashboardData`、`StrategyState`、`Position`、`Trade`、`SignalEvent`、`Token`、`TokenHistoryPoint`、`HistoryResponse` 等（见 `web/src/services/api.ts`）。

### 5.2 前后端接口约定

- **基础**：REST，JSON；前端 base URL 为 `VITE_API_URL` 或 `http://${hostname}:8000/api`。
- **主要端点**：
  - `GET /api/dashboard` → 看板汇总。
  - `GET /api/strategies`、`GET /api/strategies/{type}` → 策略列表与详情（含持仓）。
  - `GET /api/tokens`、`GET /api/tokens/{ca}/history`、`GET /api/tokens/{ca}/latest` 等 → 代币与历史。
  - `GET /api/signals`、`GET /api/signals/stats` → 信号列表与统计。
  - `GET /api/trades`、`GET /api/trades/stats`、`POST /api/trades/manual`、`POST /api/trades/manual-sell` → 交易与手动单。
  - `GET /api/history/*` → 历史数据与导出。
- **时间**：后端部分接口使用上海时区格式化返回时间字符串。

---

## 6. 部署与运行

### 6.1 启动方式

- **本地开发（DEPLOY_GUIDE）**：  
  - 后端：项目根目录（或 `dex_price`）下创建 venv，`pip install -r requirements.txt`，`cd dex_price` 后 `python init_db_tables.py`（或运行 `scripts_root/init_db_tables.py` 需在能访问 `data/dex_monitor.db` 的目录），然后启动监控主进程（例如在 `dex_price` 下 `python main.py`）和 API（`python -m api.main`）。  
  - 前端：`cd dex_price/web`，`npm install`，`npm run dev`（默认 5173）。  
- **脚本**：`scripts_root/start_dashboard.bat` 会启动「API」与「前端」两个窗口：先 `cd /d %~dp0`（即脚本所在目录 scripts_root），再执行 `python -m api.main` 和 `cd web && npm run dev`。若从仓库根或 dex_price 运行该脚本，需注意当前工作目录；若从 scripts_root 直接运行，需确保 Python 能解析 `api` 包（例如将工作目录改为 `dex_price` 或设置 `PYTHONPATH` 包含 `dex_price`）。  
- **停止**：`scripts_root/stop_dashboard.bat` 用于停止相关进程（具体行为需查看脚本内容）。

### 6.2 与 DEPLOY_GUIDE、Jenkins、脚本的关系

- **DEPLOY_GUIDE.md**：描述在新电脑上安装 Python/Node/Chrome、venv、pip 安装、初始化 DB、前端 npm install、以及通过 `start_dashboard.bat` 启动看板；并说明局域网访问（host:5173）与常见问题（DrissionPage、端口占用等）。
- **Jenkinsfile**：流水线在任意 agent 上 checkout 后，进入 `deploy` 目录执行 `docker-compose build` 和 `docker-compose up -d`、`docker image prune -f`；即部署依赖 `deploy/` 下的 Docker 配置，而非本地 bat 脚本。
- **deploy/**：`docker-compose.yml` 定义 backend（FastAPI，端口 8000）与 frontend（Nginx，端口 3000）；backend 挂载 `../data`；前端构建自 `web` 的 Dockerfile。  
- **scripts_root**：`init_db_tables.py` 检查并创建策略相关表（若使用 `core.database` 的 `_init_tables` 则主表由 DB 模块创建）；`clean_all_data.py`、`reset_system.py`、`analyze_data.py`、`manual.py` 等为运维/分析脚本；`deploy_to_remote.bat` 为远程部署用。

---

## 7. 其他

### 7.1 测试策略

- **tests/test_strategies.py**：针对移动止损、超时离场、StrategyAlpha 等做模拟运行 1–2 小时的场景测试；依赖 `services.trading_strategies` 与本地路径（如 `data/logs/test_strategies.log`）。
- **tests/test_sniper_notification.py**：Sniper 通知相关测试。
- **tests_root/**：如 `test_dynamic_session.py`、`test_new_strategies.py`、`test_v31_features.py` 等，用于会话或策略版本功能验证。

### 7.2 限制与可改进点（可选）

- **启动脚本工作目录**：`start_dashboard.bat` 以 scripts_root 为当前目录启动 API 时，若未设置 PYTHONPATH 或工作目录，可能找不到 `api` 包；建议在 bat 中 `cd` 到 `dex_price` 再执行 `python -m api.main`，或明确文档说明运行环境。
- **监控主进程与 API**：当前为主进程（`main.py`）负责监控与调度，API 为独立进程，仅共享 DB；若需「通过 API 触发单次抓取」等，需在 API 侧增加与监控进程的通信或共享状态（未在代码中发现）。
- **前端实时性**：完全依赖轮询；若需实时推送可考虑后端 WebSocket 或 SSE，并在前端对接。
- **配置集中**：部分阈值与魔法数分散在代码中（如 20K 市值、5m 买入>10、50% 市值差异）；可收敛到 config 或策略配置。
- **日志与可观测性**：已有分模块/分用途日志；可补充统一请求 ID、指标导出（如 Prometheus）便于运维。

## 8. 运行数据分析（日志/数据库）

### 8.1 数据源与覆盖范围

- 日志：`dex_price/data/logs/*.log*`
- 数据库：`dex_price/data/dex_monitor.db`
- 日志交易时间范围：2026-01-21 12:30:56 至 2026-02-07 16:18:23
- 数据库交易时间范围：2026-01-26 12:25:34 至 2026-02-07 08:18:23
- 说明：2026-01-26 至 2026-01-30 缺少 `trades.log.*`，但数据库仍有交易记录

### 8.2 日志交易统计（SELL 口径）

- BUY 4,835；SELL 5,706
- SELL 总 PnL：-16.9403 SOL；平均 -0.002969 SOL/笔
- SELL 结果：盈利 1,619（28.4%）；亏损 3,181（55.8%）；持平 906（15.9%）

### 8.3 退出原因贡献（SELL）

| 退出原因 | 次数 | 总PnL(SOL) | 说明 |
| --- | --- | --- | --- |
| 止损(-30%) | 1,008 | -34.14 | 绝对亏损主因 |
| 超时离场(30/60分钟) | 2,276 | -30.8867 | 30分钟亏损离场占大头 |
| 保本止损 | 903 | 0 | 不贡献盈亏 |
| 止盈/盈利止损/手动卖出 | 1,519 | +48.0864 | 盈利来源 |
| 合计 | 5,706 | -16.9403 | 与日志汇总一致 |

### 8.4 策略表现（数据库 strategy_states 最新）

| 策略 | 交易数 | 胜率 | 总PnL(SOL) | 余额(SOL) | 最后更新时间 |
| --- | --- | --- | --- | --- | --- |
| A | 543 | 38.12% | -1.3487 | 98.6513 | 2026-02-07 07:38:45 |
| Alpha | 216 | 43.52% | +0.2146 | 100.2146 | 2026-02-07 04:44:01 |
| B | 528 | 33.52% | -2.2639 | 97.5661 | 2026-02-07 06:20:00 |
| C | 919 | 37.16% | -1.7770 | 97.8880 | 2026-02-07 08:18:23 |
| D | 17 | 41.18% | -0.0510 | 99.9490 | 2026-02-05 11:26:12 |
| E | 325 | 34.26% | -1.1475 | 98.8175 | 2026-02-07 04:58:32 |
| F | 286 | 35.09% | -0.9326 | 99.0324 | 2026-02-07 05:15:23 |
| G | 82 | 28.40% | -0.4594 | 99.4406 | 2026-02-07 05:28:12 |
| H | 224 | 35.43% | +2.5307 | 102.5024 | 2026-02-07 05:55:36 |
| I | 103 | 33.01% | -0.5683 | 99.4317 | 2026-02-07 05:28:19 |
| M | 11 | 18.18% | -0.1836 | 99.8164 | 2026-02-01 18:53:17 |

### 8.5 信号与数据概况

- `signal_events` 共 3,784 条，`is_validated=0`（未验证）占 100%
- `tokens` 4,256；`price_snapshots` 4,680,567
- `strategy_trades` 7,270（BUY 3,254 / SELL 4,016）
- 参与交易的代币数 366（去重 `token_ca`）

### 8.6 买入市值分布（日志 BUY）

- 最小 $13.5k
- P25 $96.9k
- 中位数 $246.1k
- P75 $838.2k
- 最大 $139.64M
- 结论：买入高度集中在微盘，波动与滑点风险显著

### 8.7 运行稳定性与采集质量

- `api_client`：ERROR 416 / WARNING 959，主要为连接被重置与 SSL EOF
- `price_monitor`：WARNING 7,296，抓取失败重试频繁
- `session_manager`：WARNING 433，API 返回空数据
- `notifications`：ERROR 53 / WARNING 76，Telegram 连接失败、飞书频率限制
- 结论：采集稳定性不足，会放大入场误判与提前离场风险

### 8.8 当前持仓概况（strategy_positions）

- 持仓总数 11
- 持仓最多策略：C（4 个）
- 最老持仓：2026-01-28 07:18:32（策略 H）
- 最新持仓：2026-02-07 16:18:23（策略 C）

---

## 9. 优化策略报告（计划）

### 9.1 优化目标

- 降低止损(-30%)与超时离场的占比
- 提升整体期望值（平均每笔 PnL > 0）并控制回撤
- 在交易量可控下降的前提下提高胜率与盈亏比

### 9.2 优化方向与方法

**A. 数据质量与稳定性**

- 对 `api_client` 增加指数退避与熔断策略，统一处理 429/连接被重置/SSL EOF
- 降低抓取并发与重试频率，减少短时间大规模失败
- 对空数据与异常响应设置缓存回退与一致性校验

**B. 信号与入场过滤**

- 启用 `signal_engine` 验证结果，只有 `is_validated=1` 的信号进入交易链路
- 提高最小市值与流动性门槛，叠加 24h 成交量与交易次数约束
- 排除极端新盘与低活跃度标的，降低假信号比例

**C. 退出与风控逻辑**

- 将固定止损(-30%)改为分段止损或波动率自适应止损
- 对“超时离场”加入趋势与成交量的二次判断，避免早退
- 增强移动止损与分批止盈机制，减少止盈后回撤

**D. 策略配置与资金分配**

- 逐步降低 A/B/C/E/F/G/I 等负收益策略权重或停用
- 强化 H/Alpha 的权重并提取其入场条件作为基线策略
- 控制同一代币多策略同时入场，设置单币最大暴露

**E. 评估与迭代流程**

- 利用 `price_snapshots` 与 `strategy_trades` 做离线回放与参数回测
- 以周为粒度做 A/B 测试，逐步替换策略参数
- 以胜率、平均 PnL、最大回撤、交易频次为核心指标迭代

### 9.3 分阶段执行计划

- 第 1 阶段：修复数据质量与信号验证流程（优先减少噪声交易）
- 第 2 阶段：调整入场门槛与退出规则，收敛止损与超时离场比例
- 第 3 阶段：围绕 H/Alpha 做参数优化与资金倾斜
- 第 4 阶段：上线后监控并滚动复盘，建立可持续优化闭环

---

**报告结束。** 以上内容基于对仓库代码的阅读与归纳；未实际运行或连接外部服务，运行期行为或环境相关细节需结合运行/配置进一步确认。