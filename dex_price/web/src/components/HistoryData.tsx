import React, { useState, useEffect, useCallback } from 'react';
import { Card, Select, Input, Button, Table, Checkbox, Space, message, Spin } from 'antd';
import { DownloadOutlined, SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import type { TokenSummary, HistoryDataPoint, HistorySignalEvent, HistoryTradeRecord } from '../services/api';
import { getHistoryTokens, getHistoryData, getTokenSignals, getTokenTrades, getExportUrl } from '../services/api';

const { Option } = Select;

// 信号颜色配置
const SIGNAL_COLORS: Record<string, string> = {
    '5m': '#1890ff',      // 蓝色
    '20m': '#52c41a',     // 绿色
    '1h': '#fa8c16',      // 橙色
    '4h': '#722ed1',      // 紫色
    '5M_PRICE_ALERT': '#1890ff',
    '20M_PRICE_ALERT': '#52c41a',
    '1H_PRICE_ALERT': '#fa8c16',
    '4H_PRICE_ALERT': '#722ed1',
    'TEST_SIGNAL': '#722ed1', // 紫色测试信号
};

// 所有可选字段
const ALL_FIELDS = [
    { key: 'market_cap', label: '市值' },
    { key: 'price_usd', label: '价格(USD)' },
    { key: 'liquidity_usd', label: '流动性' },
    { key: 'volume_m5', label: '5分钟交易量' },
    { key: 'volume_h1', label: '1小时交易量' },
    { key: 'volume_h24', label: '24小时交易量' },
    { key: 'txns_m5_buys', label: '5分钟买入笔数' },
    { key: 'txns_m5_sells', label: '5分钟卖出笔数' },
    { key: 'txns_h1_buys', label: '1小时买入笔数' },
    { key: 'txns_h1_sells', label: '1小时卖出笔数' },
    { key: 'price_change_h1', label: '1小时涨跌%' },
    { key: 'price_change_h24', label: '24小时涨跌%' },
];

// 时间范围选项
const TIME_RANGES = [
    { value: 24, label: '24小时' },
    { value: 72, label: '3天' },
    { value: 168, label: '7天' },
];

interface HistoryDataProps {
    initialTokenId?: number;
    initialSearchTerm?: string;
}

const HistoryData: React.FC<HistoryDataProps> = ({ initialTokenId, initialSearchTerm }) => {
    // 状态
    const [tokens, setTokens] = useState<TokenSummary[]>([]);
    const [selectedTokenId, setSelectedTokenId] = useState<number | null>(initialTokenId || null);
    const [timeRange, setTimeRange] = useState(24);
    const [selectedFields, setSelectedFields] = useState(['market_cap', 'price_usd', 'volume_h1']);
    const [loading, setLoading] = useState(false);

    // 数据
    const [historyData, setHistoryData] = useState<HistoryDataPoint[]>([]);
    const [signals, setSignals] = useState<HistorySignalEvent[]>([]);
    const [trades, setTrades] = useState<HistoryTradeRecord[]>([]);
    const [tokenName, setTokenName] = useState<string>('');

    // 加载代币列表
    const loadTokens = useCallback(async (search?: string) => {
        try {
            const data = await getHistoryTokens(search);
            setTokens(data);
        } catch (error) {
            message.error('加载代币列表失败');
        }
    }, []);

    // 加载历史数据
    const loadData = useCallback(async () => {
        if (!selectedTokenId) return;

        setLoading(true);
        try {
            const [historyRes, signalsRes, tradesRes] = await Promise.all([
                getHistoryData(selectedTokenId, timeRange),
                getTokenSignals(selectedTokenId, timeRange),
                getTokenTrades(selectedTokenId, timeRange),
            ]);

            setHistoryData(historyRes.data);
            setTokenName(historyRes.token_name || '未知代币');
            setSignals(signalsRes);
            setTrades(tradesRes);
        } catch (error) {
            message.error('加载历史数据失败');
        } finally {
            setLoading(false);
        }
    }, [selectedTokenId, timeRange]);

    // 初始化
    useEffect(() => {
        loadTokens();
    }, [loadTokens]);

    // 代币或时间范围变化时重新加载
    useEffect(() => {
        if (selectedTokenId) {
            loadData();
        }
    }, [selectedTokenId, timeRange, loadData]);

    // 处理搜索
    const handleSearch = async (value: string) => {
        try {
            const data = await getHistoryTokens(value);
            setTokens(data);
            if (data.length > 0) {
                // 搜索后自动选中第一个结果
                const first = data[0];
                setSelectedTokenId(first.token_id);
                if (first.token_name) setTokenName(first.token_name);
            } else {
                message.info('未找到匹配的代币');
            }
        } catch (error) {
            message.error('搜索失败');
        }
    };

    // 监听初始搜索词
    useEffect(() => {
        if (initialSearchTerm) {
            getHistoryTokens(initialSearchTerm).then(data => {
                setTokens(data);
                if (data.length > 0) {
                    // 尝试找到精确匹配
                    const match = data.find(t =>
                        t.token_name?.toLowerCase() === initialSearchTerm.toLowerCase() ||
                        t.token_symbol?.toLowerCase() === initialSearchTerm.toLowerCase()
                    ) || data[0];

                    setSelectedTokenId(match.token_id);
                    if (match.token_name) setTokenName(match.token_name);
                }
            }).catch(() => {
                // ignore error
            });
        }
    }, [initialSearchTerm]);

    // 导出CSV
    const handleExport = () => {
        if (!selectedTokenId) return;
        window.open(getExportUrl(selectedTokenId, timeRange), '_blank');
    };

    // 格式化市值
    const formatMarketCap = (value: number | null) => {
        if (value === null || value === undefined) return '-';
        if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
        if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
        return `$${value.toFixed(0)}`;
    };

    // 图表配置
    const getChartOption = () => {
        if (historyData.length === 0) return {};

        const xData = historyData.map(d => d.timestamp);
        const yData = historyData.map(d => d.market_cap);

        // 辅助函数：找到最近的历史数据点
        const findNearestData = (targetTime: string) => {
            if (!historyData.length) return null;

            // 简单遍历寻找最近时间点 (假设historyData已排序)
            // 将时间字符串转换为时间戳比较
            const target = new Date(targetTime).getTime();
            let nearest = historyData[0];
            let minDiff = Math.abs(new Date(nearest.timestamp).getTime() - target);

            for (let i = 1; i < historyData.length; i++) {
                const current = historyData[i];
                const diff = Math.abs(new Date(current.timestamp).getTime() - target);
                if (diff < minDiff) {
                    minDiff = diff;
                    nearest = current;
                }
            }

            // 如果差异超过2小时，可能是不相关的数据，不显示
            if (minDiff > 2 * 60 * 60 * 1000) return null;

            return nearest;
        };

        // 定义策略颜色映射 (使用用户指定的颜色 + 三拼色)
        const STRATEGY_COLORS: Record<string, string | object> = {
            'A': '#f5222d',      // 红色 (热度)
            'B': '#fa8c16',      // 橙色 (信号)
            'C': '#fadb14',      // 黄色 (5m信号)
            'D': '#52c41a',      // 绿色 (API暴涨)
            'E': '#13c2c2',      // 青色 (20m信号)
            'F': '#1890ff',      // 蓝色 (1h信号)
            'G': '#2f54eb',      // 深蓝 (4h信号)
            'H': {               // 三拼色 (金狗狙击)
                type: 'linear',
                x: 0, y: 0, x2: 1, y2: 0,
                colorStops: [
                    { offset: 0, color: '#f5222d' }, // 红
                    { offset: 0.5, color: '#fadb14' }, // 黄
                    { offset: 1, color: '#1890ff' }  // 蓝
                ]
            },
            'I': '#722ed1',      // 紫色 (钻石手)
            'Alpha': '#000000',  // 黑色 (智能策略)
            'NA': '#8c8c8c'      // 灰色
        };

        const getStrategyColor = (strategy: string) => {
            if (!strategy) return STRATEGY_COLORS['NA'] as string;

            // 优先精确匹配
            if (Object.prototype.hasOwnProperty.call(STRATEGY_COLORS, strategy)) {
                return STRATEGY_COLORS[strategy];
            }

            // 尝试模糊匹配 (注意：Alpha 包含 A，所以必须把 Alpha 放在前面或者先匹配长字符串，或者只精确匹配)
            // 这里我们优化逻辑：先匹配较长的 key
            const keys = Object.keys(STRATEGY_COLORS).sort((a, b) => b.length - a.length);
            for (const key of keys) {
                if (strategy.includes(key) || strategy === key) {
                    return STRATEGY_COLORS[key];
                }
            }
            return STRATEGY_COLORS['NA'] as string;
        };

        // 按策略和动作分组交易
        const tradeSeries: any[] = [];
        const strategies = new Set<string>();

        // 预处理交易数据
        trades.forEach(t => {
            if (t.strategy_type) {
                strategies.add(t.strategy_type);
            }
        });

        // 为每个策略创建买入和卖出两个系列，但为了图例整洁，我们把它们合并为一个系列，通过数据项的 symbol 来区分买卖
        // 或者：为每个策略创建一个系列，系列名为 "策略A"，数据点包含买和卖
        Array.from(strategies).sort().forEach(strategy => {
            const strategyTrades = trades.filter(t => t.strategy_type === strategy);
            const color = getStrategyColor(strategy);

            const data = strategyTrades.map(t => {
                const nearest = findNearestData(t.timestamp);
                if (!nearest) return null;

                const isBuy = t.action === 'BUY';

                // 确保 tooltip 中显示的颜色是 CSS 字符串
                // 如果 color 是对象(ECharts gradient)，则使用 CSS 渐变字符串，否则尽量直接使用
                let tooltipColor = '#333';
                if (typeof color === 'string') {
                    tooltipColor = color;
                } else if (strategy === 'H') {
                    tooltipColor = 'linear-gradient(90deg, #f5222d, #fadb14, #1890ff)';
                }

                return {
                    name: `${strategy} ${isBuy ? '买入' : '卖出'}`,
                    value: [nearest.timestamp, nearest.market_cap || 0],
                    symbol: isBuy ? 'path://M512 0L64 960h896z' : 'path://M64 64h896L512 1024z',
                    symbolSize: 16,
                    itemStyle: {
                        color: color,
                        // 移除边框，保留阴影
                        shadowBlur: 3,
                        shadowColor: 'rgba(0,0,0,0.3)'
                    },
                    tooltip: {
                        formatter: () => {
                            const amountStr = t.amount ? `${t.amount.toFixed(2)} SOL` : '-';
                            // 针对渐变色，使用 webkit-background-clip 实现文字渐变效果，或者简单地用背景色块
                            const colorStyle = strategy === 'H'
                                ? `background-image:${tooltipColor};-webkit-background-clip:text;color:transparent;`
                                : `color:${tooltipColor};`;

                            return `
                                <div style="font-weight:bold;margin-bottom:4px;${colorStyle}">${strategy} ${t.action === 'BUY' ? '买入' : '卖出'}</div>
                                <div>时间: ${t.timestamp}</div>
                                <div>市值: ${formatMarketCap(nearest.market_cap)}</div>
                                <div>金额: ${amountStr}</div>
                            `;
                        }
                    }
                };
            }).filter(Boolean);

            if (data.length > 0) {
                tradeSeries.push({
                    name: `策略${strategy}`,
                    type: 'scatter',
                    data: data,
                    symbol: 'triangle', // 默认形状，具体由 data item 覆盖
                    itemStyle: { color: color },
                    z: 10
                });
            }
        });

        // 信号标记 (保留之前的逻辑)
        const signalMarks = signals.map(s => {
            const nearest = findNearestData(s.trigger_time);
            if (!nearest) return null;
            return {
                name: s.signal_type,
                coord: [nearest.timestamp, s.market_cap || nearest.market_cap || 0],
                symbol: 'diamond',
                symbolSize: 15,
                itemStyle: {
                    color: SIGNAL_COLORS[s.signal_type] || '#888',
                    borderColor: '#fff',
                    borderWidth: 1
                },
                tooltip: { formatter: `${s.signal_type}信号: ${s.trigger_time}` }
            };
        }).filter(Boolean);

        return {
            title: {
                text: `${tokenName} 市值走势`,
                left: 'center',
            },
            tooltip: {
                trigger: 'axis',
                formatter: (params: any) => {
                    // 这个 formatter 主要用于 tooltip trigger: axis 时的显示
                    // 对于 scatter 点的 hover，通常会被 scatter 自己的 tooltip 覆盖，
                    // 但如果没有覆盖，这里需要处理一下数组
                    if (!Array.isArray(params)) {
                        return `${params.name}<br/>市值: ${formatMarketCap(params.value[1] || params.value)}`;
                    }
                    const data = params[0];
                    return `${data.axisValue}<br/>市值: ${formatMarketCap(data.value)}`;
                },
            },
            legend: {
                // 动态生成图例
                data: [
                    '市值',
                    ...tradeSeries.map(s => s.name),
                    ...Object.keys(SIGNAL_COLORS).slice(0, 4)
                ],
                bottom: 10,
                type: 'scroll' // 如果图例太多，支持滚动
            },
            xAxis: {
                type: 'category',
                data: xData,
                axisLabel: {
                    formatter: (value: string) => value.split(' ')[1] || value,
                },
            },
            yAxis: {
                type: 'value',
                axisLabel: {
                    formatter: (value: number) => formatMarketCap(value),
                },
            },
            dataZoom: [
                { type: 'inside', start: 0, end: 100 },
                { type: 'slider', start: 0, end: 100, bottom: 40 },
            ],
            series: [
                {
                    name: '市值',
                    type: 'line',
                    data: yData,
                    smooth: true,
                    lineStyle: { width: 2 },
                    areaStyle: { opacity: 0.1 },
                    markPoint: {
                        data: [...signalMarks], // 仅保留信号标记在 markPoint
                    },
                },
                ...tradeSeries // 添加策略交易系列
            ],
        };
    };

    // 表格列
    const columns = [
        {
            title: '时间',
            dataIndex: 'timestamp',
            key: 'timestamp',
            width: 160,
            fixed: 'left' as const,
        },
        ...selectedFields.map(field => {
            const fieldConfig = ALL_FIELDS.find(f => f.key === field);
            return {
                title: fieldConfig?.label || field,
                dataIndex: field,
                key: field,
                width: 120,
                render: (value: number | null) => {
                    if (value === null || value === undefined) return '-';
                    if (field.includes('market_cap') || field.includes('liquidity') || field.includes('volume')) {
                        return formatMarketCap(value);
                    }
                    if (field.includes('change')) {
                        return <span style={{ color: value >= 0 ? '#52c41a' : '#f5222d' }}>{value.toFixed(2)}%</span>;
                    }
                    return value.toFixed(6);
                },
            };
        }),
    ];

    return (
        <div style={{ padding: '16px' }}>
            {/* 顶部控制栏 */}
            <Card size="small" style={{ marginBottom: 16 }}>
                <Space wrap>
                    {/* 代币选择 */}
                    <Select
                        showSearch
                        style={{ width: 240 }}
                        placeholder="选择代币"
                        value={selectedTokenId}
                        onChange={setSelectedTokenId}
                        filterOption={false}
                        onSearch={loadTokens}
                        notFoundContent={loading ? <Spin size="small" /> : null}
                    >
                        {tokens.map(token => (
                            <Option key={token.token_id} value={token.token_id}>
                                {token.token_name || token.token_symbol || token.token_ca.slice(0, 8)}
                                <span style={{ color: '#888', marginLeft: 8 }}>({token.data_count}条)</span>
                            </Option>
                        ))}
                    </Select>

                    {/* 搜索框 */}
                    <Input.Search
                        placeholder="搜索代币名称或CA"
                        style={{ width: 500 }}
                        onSearch={handleSearch}
                        prefix={<SearchOutlined />}
                    />

                    {/* 时间范围 */}
                    <Select value={timeRange} onChange={setTimeRange} style={{ width: 100 }}>
                        {TIME_RANGES.map(r => (
                            <Option key={r.value} value={r.value}>{r.label}</Option>
                        ))}
                    </Select>

                    {/* 刷新按钮 */}
                    <Button icon={<ReloadOutlined />} onClick={loadData} loading={loading}>
                        刷新
                    </Button>

                    {/* 导出按钮 */}
                    <Button
                        type="primary"
                        icon={<DownloadOutlined />}
                        onClick={handleExport}
                        disabled={!selectedTokenId}
                    >
                        导出CSV
                    </Button>
                </Space>
            </Card>

            {/* 市值曲线图 */}
            {selectedTokenId && historyData.length > 0 && (
                <Card title="市值曲线" size="small" style={{ marginBottom: 16 }}>
                    <div style={{ marginBottom: 8 }}>
                        <Space>
                            <span style={{ fontWeight: 'bold' }}>图例说明：</span>
                            <span>▲ 买入</span>
                            <span>▼ 卖出</span>
                            <span style={{ marginLeft: 8, color: '#999' }}>|</span>
                            <span>颜色代表不同策略 (各策略颜色见下图例)</span>
                            <span style={{ marginLeft: 8, color: '#999' }}>|</span>
                            <span style={{ color: '#1890ff' }}>◆ 5m信号</span>
                            <span style={{ color: '#52c41a' }}>◆ 20m信号</span>
                            <span style={{ color: '#fa8c16' }}>◆ 1h信号</span>
                            <span style={{ color: '#722ed1' }}>◆ 4h信号</span>
                        </Space>
                    </div>
                    <ReactECharts option={getChartOption()} style={{ height: 400 }} />
                </Card>
            )}

            {/* 字段选择 */}
            <Card title="字段选择" size="small" style={{ marginBottom: 16 }}>
                <Checkbox.Group
                    options={ALL_FIELDS.map(f => ({ label: f.label, value: f.key }))}
                    value={selectedFields}
                    onChange={(values) => setSelectedFields(values as string[])}
                />
            </Card>

            {/* 数据表格 */}
            <Card title={`历史数据 (${historyData.length}条)`} size="small">
                <Table
                    columns={columns}
                    dataSource={[...historyData].reverse()}
                    rowKey="timestamp"
                    size="small"
                    loading={loading}
                    scroll={{ x: 'max-content', y: 400 }}
                    pagination={{
                        pageSize: 50,
                        showSizeChanger: true,
                        showTotal: (total) => `共 ${total} 条`,
                    }}
                />
            </Card>
        </div>
    );
};

export default HistoryData;
