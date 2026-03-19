// 策略看板组件 - 显示各策略的状态卡片
import React, { useEffect, useState } from 'react';
import { Card, Row, Col, Statistic, Tag, Spin, Space } from 'antd';
import {
    DollarOutlined,
    TrophyOutlined,
    RiseOutlined,
    FallOutlined,
    ReloadOutlined
} from '@ant-design/icons';
import { getStrategies } from '../services/api';
import type { StrategyState } from '../services/api';
import ManualTrade from './ManualTrade';

// 策略颜色映射
const strategyColors: Record<string, string> = {
    'A': '#f5222d',
    'B': '#fa8c16',
    'C': '#fadb14',
    'D': '#52c41a',
    'E': '#13c2c2',
    'F': '#1890ff',
    'G': '#2f54eb',
    'H': '#722ed1',
    'I': '#eb2f96',
    'Alpha': '#000000',
    'M': '#8c8c8c',
};

export const StrategyDashboard: React.FC = () => {
    const [strategies, setStrategies] = useState<StrategyState[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchData = async () => {
        try {
            const data = await getStrategies();
            setStrategies(data);
        } catch (error) {
            console.error('获取策略数据失败:', error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
        // 每30秒刷新一次
        const interval = setInterval(fetchData, 30000);
        return () => clearInterval(interval);
    }, []);

    if (loading) {
        return (
            <div style={{ textAlign: 'center', padding: 50 }}>
                <Spin size="large" />
            </div>
        );
    }

    return (
        <div className="strategy-dashboard">
            {/* 手动交易入口 */}
            <ManualTrade />

            <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 style={{ margin: 0 }}>📊 策略概览</h3>
                <ReloadOutlined
                    onClick={fetchData}
                    style={{ cursor: 'pointer', fontSize: 16 }}
                />
            </div>

            <Row gutter={[16, 16]}>
                {strategies.map((strategy) => (
                    <Col xs={24} sm={12} md={8} lg={6} key={strategy.strategy_type}>
                        <Card
                            size="small"
                            title={
                                <Space>
                                    <Tag color={strategyColors[strategy.strategy_type] || '#666'}>
                                        策略 {strategy.strategy_type}
                                    </Tag>
                                </Space>
                            }
                            style={{
                                borderTop: `3px solid ${strategyColors[strategy.strategy_type] || '#666'}`
                            }}
                        >
                            <Row gutter={8}>
                                <Col span={12}>
                                    <Statistic
                                        title="余额"
                                        value={strategy.balance_sol}
                                        precision={2}
                                        suffix="SOL"
                                        valueStyle={{ fontSize: 14 }}
                                        prefix={<DollarOutlined />}
                                    />
                                </Col>
                                <Col span={12}>
                                    <Statistic
                                        title="总盈亏"
                                        value={strategy.total_pnl}
                                        precision={2}
                                        suffix="SOL"
                                        valueStyle={{
                                            fontSize: 14,
                                            color: strategy.total_pnl >= 0 ? '#52c41a' : '#ff4d4f'
                                        }}
                                        prefix={strategy.total_pnl >= 0 ? <RiseOutlined /> : <FallOutlined />}
                                    />
                                </Col>
                            </Row>
                            <Row gutter={8} style={{ marginTop: 12 }}>
                                <Col span={12}>
                                    <Statistic
                                        title="胜率"
                                        value={strategy.win_rate}
                                        precision={1}
                                        suffix="%"
                                        valueStyle={{ fontSize: 14 }}
                                        prefix={<TrophyOutlined />}
                                    />
                                </Col>
                                <Col span={12}>
                                    <Statistic
                                        title="交易数"
                                        value={strategy.total_trades}
                                        valueStyle={{ fontSize: 14 }}
                                    />
                                </Col>
                            </Row>
                            <div style={{ marginTop: 8, fontSize: 12, color: '#999' }}>
                                胜 {strategy.winning_trades} / 负 {strategy.losing_trades}
                            </div>
                        </Card>
                    </Col>
                ))}
            </Row>

            {strategies.length === 0 && (
                <Card>
                    <div style={{ textAlign: 'center', color: '#999', padding: 20 }}>
                        暂无策略数据
                    </div>
                </Card>
            )}
        </div>
    );
};

export default StrategyDashboard;
