// 交易历史组件
import React, { useEffect, useState } from 'react';
import { Table, Tag, Card, Space, Select, Button, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { getTrades, getTradeStats } from '../services/api';
import type { Trade, TradeStats } from '../services/api';
import dayjs from 'dayjs';

const { Option } = Select;

// 策略颜色映射 (与图表保持一致)
// 策略颜色映射 (与图表保持一致)
const strategyColors: Record<string, string> = {
    'A': '#f5222d',      // 红色 (热度)
    'B': '#fa8c16',      // 橙色 (信号)
    'C': '#fadb14',      // 黄色 (5m信号)
    'D': '#52c41a',      // 绿色 (API暴涨)
    'E': '#13c2c2',      // 青色 (20m信号)
    'F': '#1890ff',      // 蓝色 (1h信号)
    'G': '#2f54eb',      // 深蓝 (4h信号)
    'H': '#1890ff',      // 三拼色 (Table中暂用蓝色或自定义渲染)
    'I': '#722ed1',      // 紫色 (钻石手)
    'Alpha': '#000000',  // 黑色 (智能策略)
    'M': '#fa541c',      // 火山红 (手动交易)
};


const strategies = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'Alpha', 'M'];

interface TradeHistoryProps {
    onTokenClick?: (token: string) => void;
}

export const TradeHistory: React.FC<TradeHistoryProps> = ({ onTokenClick }) => {
    const [trades, setTrades] = useState<Trade[]>([]);
    const [stats, setStats] = useState<TradeStats | null>(null);
    const [timeRange, setTimeRange] = useState<number>(72);
    const [limit, setLimit] = useState<number>(100);
    const [actionFilter, setActionFilter] = useState<string>('all');
    const [strategyFilter, setStrategyFilter] = useState<string>('all');
    const [loading, setLoading] = useState(true);

    const fetchData = async () => {
        setLoading(true);
        try {
            // 根据筛选条件获取交易数据
            const action = actionFilter === 'all' ? undefined : actionFilter;
            const strategy = strategyFilter === 'all' ? undefined : strategyFilter;
            const [tradeData, statsData] = await Promise.all([
                getTrades(timeRange, strategy, action, limit),
                getTradeStats()
            ]);
            setTrades(tradeData);
            setStats(statsData);
        } catch (error) {
            console.error('获取交易数据失败:', error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, [timeRange, actionFilter, strategyFilter, limit]);

    const columns: ColumnsType<Trade> = [
        {
            title: '时间',
            dataIndex: 'timestamp',
            key: 'timestamp',
            width: 140,
            render: (time: string) => dayjs(time).format('MM-DD HH:mm'),
        },
        {
            title: '策略',
            dataIndex: 'strategy_type',
            key: 'strategy_type',
            width: 80,
            render: (type: string) => {
                const displayText = type === 'M' ? 'Manual' : type;
                const color = strategyColors[type] || '#666';
                const style = type === 'H' ? { background: 'linear-gradient(90deg, #f5222d, #fadb14, #1890ff)', border: 'none' } : undefined;
                return (
                    <Tag color={color} style={style}>{displayText}</Tag>
                );
            },
        },
        {
            title: '代币',
            dataIndex: 'token_name',
            key: 'token_name',
            width: 170,
            render: (name: string, record: Trade) => (
                <Space size={4}>
                    <a
                        onClick={() => onTokenClick?.(record.token_ca)}
                        style={{
                            cursor: 'pointer',
                            fontWeight: 500,
                            color: '#1890ff'
                        }}
                    >
                        {name}
                    </a>
                    <Typography.Text
                        copyable={{ text: record.token_ca, tooltips: false }}
                        style={{ color: '#999', fontSize: 12, display: 'inline-flex', verticalAlign: 'middle' }}
                    />
                </Space>
            ),
        },
        {
            title: '操作',
            dataIndex: 'action',
            key: 'action',
            width: 80,
            render: (action: string) => (
                <Tag color={action === 'BUY' ? 'blue' : 'orange'}>
                    {action === 'BUY' ? '买入' : '卖出'}
                </Tag>
            ),
        },
        {
            title: '成交市值',
            dataIndex: 'price',
            key: 'price',
            width: 100,
            render: (val: number) => {
                if (!val) return '-';
                if (val >= 1000000) return `$${(val / 1000000).toFixed(2)}M`;
                if (val >= 1000) return `$${(val / 1000).toFixed(1)}K`;
                return `$${val.toFixed(0)}`;
            }
        },
        {
            title: '金额',
            dataIndex: 'amount',
            key: 'amount',
            width: 100,
            render: (amount: number) => amount ? `${amount.toFixed(3)} SOL` : '-',
        },
        {
            title: '盈亏',
            dataIndex: 'pnl',
            key: 'pnl',
            width: 120,
            render: (pnl: number, record: Trade) => {
                if (record.action === 'BUY' || pnl === null) return '-';
                return (
                    <span style={{
                        color: pnl >= 0 ? '#52c41a' : '#ff4d4f',
                        fontWeight: 500
                    }}>
                        {pnl >= 0 ? '+' : ''}{pnl.toFixed(4)} SOL
                    </span>
                );
            },
        },
    ];

    return (
        <Card
            title="📜 交易历史"
            extra={
                <Space>
                    {stats && (
                        <Space size="large" style={{ marginRight: 16 }}>
                            <span>
                                总盈亏:
                                <span style={{
                                    color: stats.total_pnl >= 0 ? '#52c41a' : '#ff4d4f',
                                    fontWeight: 600,
                                    marginLeft: 4
                                }}>
                                    {stats.total_pnl >= 0 ? '+' : ''}{stats.total_pnl.toFixed(4)} SOL
                                </span>
                            </span>
                            <span>胜率: <strong>{stats.win_rate}%</strong></span>
                        </Space>
                    )}
                    <Select
                        value={strategyFilter}
                        onChange={setStrategyFilter}
                        style={{ width: 100 }}
                        placeholder="策略"
                    >
                        <Option value="all">所有策略</Option>
                        {strategies.map(s => (
                            <Option key={s} value={s}>{s}</Option>
                        ))}
                    </Select>
                    <Select
                        value={actionFilter}
                        onChange={setActionFilter}
                        style={{ width: 90 }}
                    >
                        <Option value="all">全部</Option>
                        <Option value="BUY">买入</Option>
                        <Option value="SELL">卖出</Option>
                    </Select>
                    <Select
                        value={timeRange}
                        onChange={setTimeRange}
                        style={{ width: 80 }}
                    >
                        <Option value={24}>24h</Option>
                        <Option value={72}>3天</Option>
                        <Option value={168}>7天</Option>
                    </Select>
                    <Select
                        value={limit}
                        onChange={setLimit}
                        style={{ width: 100 }}
                        placeholder="Limit"
                        title="最大记录数"
                    >
                        <Option value={100}>Limit: 100</Option>
                        <Option value={500}>Limit: 500</Option>
                        <Option value={1000}>Limit: 1K</Option>
                    </Select>
                    <Button
                        icon={<ReloadOutlined />}
                        onClick={fetchData}
                        size="small"
                    />
                </Space>
            }
        >
            <Table
                columns={columns}
                dataSource={trades}
                rowKey="id"
                loading={loading}
                size="small"
                pagination={{
                    pageSize: 15,
                    showSizeChanger: true,
                    pageSizeOptions: ['15', '30', '50', '100'],
                    showTotal: (total) => `共 ${total} 条`
                }}
            />
        </Card>
    );
};

export default TradeHistory;
