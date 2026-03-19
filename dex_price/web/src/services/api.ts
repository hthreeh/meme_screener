// DEX Price Dashboard API 服务
// 动态获取API地址，支持局域网访问
const API_BASE = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000/api`;

// ==================== 通用请求函数 ====================

async function request<T>(
    endpoint: string,
    options: RequestInit = {}
): Promise<T> {
    const response = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ error: 'Unknown error' }));
        throw new Error(error.error || error.detail || `HTTP ${response.status}`);
    }

    return response.json();
}

// ==================== 看板接口 ====================

// 获取综合看板数据
export async function getDashboard() {
    return request<DashboardData>('/dashboard');
}

// 获取简要汇总
export async function getDashboardSummary() {
    return request<{ positions: number; active_strategies: number; total_balance: number }>('/dashboard/summary');
}

// ==================== 策略接口 ====================

// 获取所有策略状态
export async function getStrategies() {
    return request<StrategyState[]>('/strategies');
}

// 获取策略详情（含持仓）
export async function getStrategyDetail(strategyType: string) {
    return request<StrategyDetail>(`/strategies/${strategyType}`);
}

// 获取策略持仓
export async function getStrategyPositions(strategyType: string) {
    return request<Position[]>(`/strategies/${strategyType}/positions`);
}

// ==================== 代币接口 ====================

// 获取所有代币列表
export async function getTokens(limit?: number, offset?: number) {
    const params = new URLSearchParams();
    if (limit) params.append('limit', limit.toString());
    if (offset) params.append('offset', offset.toString());
    const query = params.toString() ? `?${params.toString()}` : '';
    return request<Token[]>(`/tokens${query}`);
}

// 获取代币历史数据（用于市值曲线）
export async function getTokenHistory(ca: string, hours?: number) {
    const query = hours ? `?hours=${hours}` : '';
    return request<TokenHistoryPoint[]>(`/tokens/${ca}/history${query}`);
}

// 获取代币最新数据
export async function getTokenLatest(ca: string) {
    return request<TokenLatest>(`/tokens/${ca}/latest`);
}

// 获取持仓中的代币
export async function getPositionTokens() {
    return request<Token[]>('/tokens/positions/all');
}

// ==================== 信号接口 ====================

// 获取信号列表
export async function getSignals(hours?: number, signalType?: string, limit?: number) {
    const params = new URLSearchParams();
    if (hours) params.append('hours', hours.toString());
    if (signalType) params.append('signal_type', signalType);
    if (limit) params.append('limit', limit.toString());
    const query = params.toString() ? `?${params.toString()}` : '';
    return request<SignalEvent[]>(`/signals${query}`);
}

// 获取信号统计
export async function getSignalStats() {
    return request<SignalStats>('/signals/stats');
}

// 获取信号类型列表
export async function getSignalTypes() {
    return request<{ types: string[] }>('/signals/types');
}

// ==================== 交易接口 ====================

// 获取交易历史
export async function getTrades(hours?: number, strategyType?: string, action?: string, limit?: number) {
    const params = new URLSearchParams();
    if (hours) params.append('hours', hours.toString());
    if (strategyType) params.append('strategy_type', strategyType);
    if (action) params.append('action', action);
    if (limit) params.append('limit', limit.toString());
    const query = params.toString() ? `?${params.toString()}` : '';
    return request<Trade[]>(`/trades${query}`);
}

// 获取交易统计
export async function getTradeStats() {
    return request<TradeStats>('/trades/stats');
}

// 获取按策略分组的交易统计
export async function getTradesByStrategy() {
    return request<{ strategies: StrategyTradeStats[] }>('/trades/by-strategy');
}

// 手动交易 - 创建买入订单
export async function createManualOrder(ca: string, amount: number = 0.2) {
    return request<ManualOrderResponse>('/trades/manual', {
        method: 'POST',
        body: JSON.stringify({ ca, amount }),
    });
}

export interface ManualOrderResponse {
    success: boolean;
    order_id?: number;
    message: string;
    // 详细结果
    token_name?: string;
    buy_price?: number;
    buy_amount?: number;
    balance_after?: number;
}

// 手动卖出响应接口
export interface ManualSellOrderResponse {
    success: boolean;
    order_id?: number;
    message: string;
    // 详细结果
    token_name?: string;
    sell_price?: number;
    sell_amount?: number;
    pnl?: number;
    pnl_percent?: number;
    balance_after?: number;
}

// 手动交易 - 创建卖出订单
export async function createManualSellOrder(strategyType: string, tokenId: number) {
    return request<ManualSellOrderResponse>('/trades/manual-sell', {
        method: 'POST',
        body: JSON.stringify({ strategy_type: strategyType, token_id: tokenId }),
    });
}

// ==================== 类型定义 ====================

export interface DashboardData {
    total_balance: number;
    total_pnl: number;
    total_positions: number;
    active_strategies: number;
    trades_24h: number;
    signals_24h: number;
    pnl_24h: number;
    strategies: StrategyOverview[];
    recent_trades: RecentTrade[];
    last_update: string;
}

export interface StrategyOverview {
    strategy_type: string;
    balance: number;
    pnl: number;
    position_count: number;
}

export interface RecentTrade {
    strategy_type: string;
    token_name: string;
    action: string;
    pnl: number | null;
    timestamp: string;
}

export interface StrategyState {
    strategy_type: string;
    balance_sol: number;
    total_trades: number;
    winning_trades: number;
    losing_trades: number;
    total_pnl: number;
    win_rate: number;
}

export interface Position {
    id: number;
    token_id: number;  // 代币 ID，用于手动卖出
    strategy_type: string;
    token_ca: string;
    token_name: string | null;
    buy_market_cap: number;
    buy_amount_sol: number;
    buy_time: string;
    remaining_ratio: number;
    highest_multiplier: number;
    take_profit_level: number;
    // 新增字段
    current_market_cap: number | null;
    current_amount_sol: number | null;
    current_multiplier: number | null;
    pnl_percent: number | null;
}

export interface StrategyDetail {
    state: StrategyState;
    positions: Position[];
}

export interface Token {
    id: number;
    ca: string | null;
    href: string;
    name: string | null;
    symbol: string | null;
    first_seen: string;
    last_updated: string;
}

export interface TokenHistoryPoint {
    timestamp: string;
    price_usd: number | null;
    market_cap: number | null;
    liquidity_usd: number | null;
    volume_h1: number | null;
    txns_h1_buys: number | null;
    txns_h1_sells: number | null;
}

export interface TokenLatest {
    ca: string;
    name: string | null;
    symbol: string | null;
    price_usd: number | null;
    market_cap: number | null;
    liquidity_usd: number | null;
    price_change_h1: number | null;
    price_change_h24: number | null;
    volume_h24: number | null;
    timestamp: string;
}

export interface SignalEvent {
    id: number;
    token_id: number;
    token_name: string | null;
    token_symbol: string | null;
    token_ca: string | null;
    signal_type: string;
    trigger_value: number | null;
    market_cap_at_trigger: number | null;
    price_at_trigger: number | null;
    is_validated: boolean;
    validation_result: string | null;
    created_at: string;
}

export interface SignalStats {
    total_signals: number;
    signals_24h: number;
    signals_by_type: Record<string, number>;
    validated_count: number;
    validation_rate: number;
}

export interface Trade {
    id: number;
    strategy_type: string | null;
    token_ca: string;
    token_name: string;
    action: string;
    price: number | null;
    amount: number | null;
    pnl: number | null;
    timestamp: string;
}

export interface TradeStats {
    total_trades: number;
    trades_24h: number;
    buy_count: number;
    sell_count: number;
    total_pnl: number;
    winning_trades: number;
    losing_trades: number;
    win_rate: number;
    avg_pnl: number;
}

export interface StrategyTradeStats {
    strategy_type: string;
    total_trades: number;
    buy_count: number;
    sell_count: number;
    winning_trades: number;
    total_pnl: number;
    win_rate: number;
}

// ==================== 历史数据接口 ====================

export interface TokenSummary {
    token_id: number;
    token_ca: string;
    token_name: string | null;
    token_symbol: string | null;
    data_count: number;
    first_time: string | null;
    last_time: string | null;
}

export interface HistoryDataPoint {
    timestamp: string;
    price_usd: number | null;
    market_cap: number | null;
    liquidity_usd: number | null;
    volume_m5: number | null;
    volume_h1: number | null;
    volume_h24: number | null;
    txns_m5_buys: number | null;
    txns_m5_sells: number | null;
    txns_h1_buys: number | null;
    txns_h1_sells: number | null;
    price_change_h1: number | null;
    price_change_h24: number | null;
}

export interface HistoryResponse {
    token_id: number;
    token_ca: string;
    token_name: string | null;
    data: HistoryDataPoint[];
}

export interface HistorySignalEvent {
    id: number;
    signal_type: string;
    trigger_time: string;
    trigger_value: number | null;
    market_cap: number | null;
    price: number | null;
}

export interface HistoryTradeRecord {
    id: number;
    strategy_type: string;
    action: string;
    timestamp: string;
    price: number | null;
    amount: number | null;
    pnl: number | null;
}

// 获取有历史数据的代币列表
export async function getHistoryTokens(search?: string, limit: number = 100) {
    const params = new URLSearchParams();
    if (search) params.append('search', search);
    params.append('limit', limit.toString());
    return request<TokenSummary[]>(`/history/tokens?${params}`);
}

// 获取代币历史数据
export async function getHistoryData(tokenId: number, hours: number = 24) {
    return request<HistoryResponse>(`/history/${tokenId}?hours=${hours}`);
}

// 获取代币信号事件
export async function getTokenSignals(tokenId: number, hours: number = 24) {
    return request<HistorySignalEvent[]>(`/history/${tokenId}/signals?hours=${hours}`);
}

// 获取代币交易记录
export async function getTokenTrades(tokenId: number, hours: number = 24) {
    return request<HistoryTradeRecord[]>(`/history/${tokenId}/trades?hours=${hours}`);
}

// 导出CSV (返回下载URL)
export function getExportUrl(tokenId: number, hours: number = 24) {
    return `${API_BASE}/history/${tokenId}/export?hours=${hours}`;
}

