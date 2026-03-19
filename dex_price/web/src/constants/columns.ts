// 列定义常量
export const dashboardColumns = [
    { key: 'symbol', label: 'Token', fixed: true },
    { key: 'price', label: '价格 (USD)' },
    { key: 'marketCap', label: '市值' },
    { key: 'fdv', label: 'FDV' },
    { key: 'liquidity', label: '流动性' },
    { key: 'volume_m5', label: '交易量 5m' },
    { key: 'volume_h1', label: '交易量 1h' },
    { key: 'volume_h6', label: '交易量 6h' },
    { key: 'volume_h24', label: '交易量 24h' },
    { key: 'txns_m5', label: '交易次数 5m' },
    { key: 'txns_h1', label: '交易次数 1h' },
    { key: 'txns_h6', label: '交易次数 6h' },
    { key: 'txns_h24', label: '交易次数 24h' },
    { key: 'priceChange_m5', label: '涨跌幅 5m' },
    { key: 'priceChange_h1', label: '涨跌幅 1h' },
    { key: 'priceChange_h6', label: '涨跌幅 6h' },
    { key: 'priceChange_h24', label: '涨跌幅 24h' },
    { key: 'actions', label: '操作', fixed: true },
];

export const liveFeedColumnsDefinition = [
    { key: 'symbol', label: 'Token', fixed: true },
    { key: 'price', label: '价格 (USD)' },
    { key: 'marketCap', label: '市值' },
    { key: 'fdv', label: 'FDV' },
    { key: 'liquidity', label: '流动性' },

    { key: 'volume_m5', label: '交易量 5m' },
    { key: 'volume_h1', label: '交易量 1h' },
    { key: 'volume_h6', label: '交易量 6h' },
    { key: 'volume_h24', label: '交易量 24h' },

    { key: 'txns_m5', label: '交易次数 5m' },
    { key: 'txns_h1', label: '交易次数 1h' },
    { key: 'txns_h6', label: '交易次数 6h' },
    { key: 'txns_h24', label: '交易次数 24h' },

    { key: 'priceChange_m5', label: '涨跌幅 5m' },
    { key: 'priceChange_h1', label: '涨跌幅 1h' },
    { key: 'priceChange_h6', label: '涨跌幅 6h' },
    { key: 'priceChange_h24', label: '涨跌幅 24h' },

    { key: 'timestamp', label: '时间 (上海)', fixed: true },
];
