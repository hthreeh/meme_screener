// 持仓表格组件 - 显示当前所有策略的持仓
import React, { useEffect, useState } from 'react';
import { Table, Tag, Card, Space, Select, Tooltip, Button, Typography, Popconfirm, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { getStrategies, getStrategyPositions, createManualSellOrder } from '../services/api';
import type { Position } from '../services/api';
import dayjs from 'dayjs';

const { Option } = Select;

// 策略颜色映射
const strategyColors: Record<string, string> = {
    'A': '#1890ff',
    'B': '#52c41a',
    'C': '#722ed1',
    'D': '#eb2f96',
    'F': '#fa8c16',
    'G': '#13c2c2',
    'H': '#2f54eb',
    'R': '#f5222d',
};

// 格式化市值
const formatMarketCap = (value: number): string => {
    if (value >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
    if (value >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
    if (value >= 1e3) return `$${(value / 1e3).toFixed(2)}K`;
    return `$${value.toFixed(2)}`;
};

interface PositionTableProps {
    onTokenClick?: (token: string) => void;
}

export const PositionTable: React.FC<PositionTableProps> = ({ onTokenClick }) => {
    const [positions, setPositions] = useState<Position[]>([]);
    const [strategies, setStrategies] = useState<string[]>([]);
    const [selectedStrategy, setSelectedStrategy] = useState<string>('all');
    const [loading, setLoading] = useState(true);
    const [sellingId, setSellingId] = useState<number | null>(null);  // 正在卖出的持仓 ID

    // 处理卖出
    const handleSell = async (record: Position) => {
        setSellingId(record.id);
        try {
            const result = await createManualSellOrder(record.strategy_type, record.token_id);
            if (result.success) {
                message.success(
                    `卖出成功！${result.token_name || ''} PNL: ${result.pnl?.toFixed(4) || 0} SOL (${result.pnl_percent?.toFixed(1) || 0}%)`
                );
                // 刷新持仓列表
                fetchData();
            } else {
                message.error(result.message || '卖出失败');
            }
        } catch (error: any) {
            message.error(`卖出失败: ${error.message || '未知错误'}`);
        } finally {
            setSellingId(null);
        }
    };

    const fetchData = async () => {
        setLoading(true);
        try {
            // 获取所有策略
            const strategyData = await getStrategies();
            const types = strategyData.map(s => s.strategy_type);
            setStrategies(types);

            // 获取持仓
            let allPositions: Position[] = [];
            if (selectedStrategy === 'all') {
                // 获取所有策略的持仓
                for (const type of types) {
                    const pos = await getStrategyPositions(type);
                    allPositions = [...allPositions, ...pos];
                }
            } else {
                allPositions = await getStrategyPositions(selectedStrategy);
            }
            setPositions(allPositions);
        } catch (error) {
            console.error('获取持仓数据失败:', error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, [selectedStrategy]);

    // 每60秒刷新
    useEffect(() => {
        const interval = setInterval(fetchData, 60000);
        return () => clearInterval(interval);
    }, [selectedStrategy]);

    const columns: ColumnsType<Position> = [
        {
            title: '策略',
            dataIndex: 'strategy_type',
            key: 'strategy_type',
            width: 70,
            render: (type: string) => (
                <Tag color={strategyColors[type] || '#666'}>{type}</Tag>
            ),
        },
        {
            title: '代币',
            dataIndex: 'token_name',
            key: 'token_name',
            width: 140,
            render: (name: string, record: Position) => (
                <Space size={4}>
                    <Tooltip title={record.token_ca}>
                        <a onClick={() => onTokenClick?.(record.token_ca)} style={{ cursor: 'pointer', fontWeight: 500 }}>
                            {name || record.token_ca?.slice(0, 8)}
                        </a>
                    </Tooltip>
                    <Typography.Text
                        copyable={{ text: record.token_ca, tooltips: false }}
                        style={{ color: '#999', fontSize: 12, display: 'inline-flex', verticalAlign: 'middle' }}
                    />
                </Space>
            ),
        },
        {
            title: '买入市值',
            dataIndex: 'buy_market_cap',
            key: 'buy_market_cap',
            width: 100,
            render: (value: number) => formatMarketCap(value),
        },
        {
            title: '当前市值',
            dataIndex: 'current_market_cap',
            key: 'current_market_cap',
            width: 100,
            render: (value: number | null, record: Position) => {
                if (value === null) return <span style={{ color: '#999' }}>-</span>;
                const isProfitable = record.pnl_percent !== null && record.pnl_percent >= 0;
                return (
                    <span style={{ color: isProfitable ? '#52c41a' : '#ff4d4f' }}>
                        {formatMarketCap(value)}
                    </span>
                );
            },
        },
        {
            title: '买入金额',
            dataIndex: 'buy_amount_sol',
            key: 'buy_amount_sol',
            width: 90,
            render: (value: number) => `${value.toFixed(3)} SOL`,
        },
        {
            title: '当前金额',
            dataIndex: 'current_amount_sol',
            key: 'current_amount_sol',
            width: 100,
            render: (value: number | null, record: Position) => {
                if (value === null) return <span style={{ color: '#999' }}>-</span>;
                const isProfitable = record.pnl_percent !== null && record.pnl_percent >= 0;
                return (
                    <span style={{
                        color: isProfitable ? '#52c41a' : '#ff4d4f',
                        fontWeight: 500
                    }}>
                        {value.toFixed(3)} SOL
                    </span>
                );
            },
        },
        {
            title: '盈亏',
            dataIndex: 'pnl_percent',
            key: 'pnl_percent',
            width: 80,
            render: (value: number | null) => {
                if (value === null) return <span style={{ color: '#999' }}>-</span>;
                const isProfitable = value >= 0;
                return (
                    <span style={{
                        color: isProfitable ? '#52c41a' : '#ff4d4f',
                        fontWeight: 600
                    }}>
                        {isProfitable ? '+' : ''}{value.toFixed(1)}%
                    </span>
                );
            },
        },
        {
            title: '剩余',
            dataIndex: 'remaining_ratio',
            key: 'remaining_ratio',
            width: 60,
            render: (ratio: number) => (
                <span style={{ color: ratio < 0.5 ? '#fa8c16' : '#52c41a' }}>
                    {(ratio * 100).toFixed(0)}%
                </span>
            ),
        },
        {
            title: '最高',
            dataIndex: 'highest_multiplier',
            key: 'highest_multiplier',
            width: 70,
            render: (mult: number) => (
                <span style={{
                    color: mult >= 2 ? '#52c41a' : mult >= 1 ? '#1890ff' : '#ff4d4f',
                    fontWeight: mult >= 2 ? 600 : 400
                }}>
                    {mult.toFixed(2)}x
                </span>
            ),
        },
        {
            title: 'TP',
            dataIndex: 'take_profit_level',
            key: 'take_profit_level',
            width: 50,
            render: (level: number) => (
                <Tag color={level > 0 ? 'green' : 'default'} style={{ margin: 0 }}>{level}</Tag>
            ),
        },
        {
            title: '买入时间',
            dataIndex: 'buy_time',
            key: 'buy_time',
            width: 100,
            render: (time: string) => dayjs(time).format('MM-DD HH:mm'),
        },
        {
            title: '操作',
            key: 'action',
            width: 80,
            fixed: 'right' as const,
            render: (_: any, record: Position) => (
                <Popconfirm
                    title="确认卖出"
                    description={`确定要卖出 ${record.token_name || record.token_ca?.slice(0, 8)} 吗？`}
                    onConfirm={() => handleSell(record)}
                    okText="确认"
                    cancelText="取消"
                    okButtonProps={{ danger: true }}
                >
                    <Button
                        type="link"
                        danger
                        size="small"
                        loading={sellingId === record.id}
                        disabled={sellingId !== null}
                    >
                        卖出
                    </Button>
                </Popconfirm>
            ),
        },
    ];

    return (
        <Card
            title="📈 当前持仓"
            extra={
                <Space>
                    <Select
                        value={selectedStrategy}
                        onChange={setSelectedStrategy}
                        style={{ width: 100 }}
                    >
                        <Option value="all">全部</Option>
                        {strategies.map(s => (
                            <Option key={s} value={s}>策略 {s}</Option>
                        ))}
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
                dataSource={positions}
                rowKey="id"
                loading={loading}
                size="small"
                pagination={{ pageSize: 10 }}
                scroll={{ x: 900 }}
            />
        </Card>
    );
};

export default PositionTable;
