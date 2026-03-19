// 市值曲线图表组件
import React, { useEffect, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { Select, Card, Space, Spin } from 'antd';
import { getChartData } from '../services/api';
import { useAppStore } from '../stores/appStore';
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';

dayjs.extend(utc);
dayjs.extend(timezone);

const { Option } = Select;

interface ChartDataPoint {
    timestamp: string;
    priceUsd: number | null;
    marketCap: number | null;
    volume: number | null;
}

export const MarketCapChart: React.FC = () => {
    const sessions = useAppStore(state => state.sessions);
    const [selectedSessionId, setSelectedSessionId] = useState<string>('');
    const [timeRange, setTimeRange] = useState<number>(24);
    const [chartData, setChartData] = useState<ChartDataPoint[]>([]);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (sessions.length > 0 && !selectedSessionId) {
            setSelectedSessionId(sessions[0].id);
        }
    }, [sessions, selectedSessionId]);

    useEffect(() => {
        if (!selectedSessionId) return;

        const fetchData = async () => {
            setLoading(true);
            try {
                const result: any = await getChartData(selectedSessionId, timeRange);
                setChartData(result.chartData || []);
            } catch (error) {
                console.error('获取图表数据失败:', error);
                setChartData([]);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
        // 每分钟刷新一次
        const interval = setInterval(fetchData, 60000);
        return () => clearInterval(interval);
    }, [selectedSessionId, timeRange]);

    const option = {
        backgroundColor: 'transparent',
        tooltip: {
            trigger: 'axis',
            backgroundColor: 'rgba(255, 255, 255, 0.9)',
            borderColor: '#f0f0f0',
            textStyle: { color: '#333' },
            axisPointer: {
                type: 'cross',
                crossStyle: { color: '#999' }
            },
            formatter: (params: any) => {
                if (!params || params.length === 0) return '';
                const date = params[0].value[0];
                // 强制转换为上海时区
                const timeStr = dayjs(date).tz('Asia/Shanghai').format('MM-DD HH:mm');
                let result = `<div style="font-weight: 500; margin-bottom: 4px;">${timeStr}</div>`;

                params.forEach((param: any) => {
                    const value = param.value[1];
                    let formattedValue = value;
                    if (value === null || value === undefined) {
                        formattedValue = '-';
                    } else if (param.seriesName === '市值') {
                        if (value >= 1e9) formattedValue = '$' + (value / 1e9).toFixed(2) + 'B';
                        else if (value >= 1e6) formattedValue = '$' + (value / 1e6).toFixed(2) + 'M';
                        else if (value >= 1e3) formattedValue = '$' + (value / 1e3).toFixed(2) + 'K';
                        else formattedValue = '$' + value.toFixed(2);
                    } else if (param.seriesName === '价格') {
                        formattedValue = '$' + (value < 0.0001 ? value.toExponential(4) : value.toFixed(6));
                    }
                    result += `<div style="display: flex; justify-content: space-between; align-items: center; gap: 16px;">
                        <span>${param.marker}${param.seriesName}</span>
                        <span style="font-weight: 500;">${formattedValue}</span>
                    </div>`;
                });
                return result;
            }
        },
        legend: {
            data: ['市值', '价格'],
            textStyle: { color: '#666' },
            top: 0
        },
        grid: {
            left: '3%',
            right: '4%',
            bottom: '3%',
            containLabel: true
        },
        xAxis: {
            type: 'time',
            axisLine: { lineStyle: { color: '#d9d9d9' } },
            axisLabel: {
                color: '#666',
                formatter: (value: number) => {
                    // 强制转换为上海时区
                    return dayjs(value).tz('Asia/Shanghai').format('HH:mm');
                }
            },
            splitLine: { show: false }
        },
        yAxis: [
            {
                type: 'value',
                name: '市值',
                position: 'left',
                axisLine: { lineStyle: { color: '#52c41a' } },
                axisLabel: {
                    color: '#52c41a',
                    formatter: (val: number) => {
                        if (val >= 1e9) return (val / 1e9).toFixed(1) + 'B';
                        if (val >= 1e6) return (val / 1e6).toFixed(1) + 'M';
                        if (val >= 1e3) return (val / 1e3).toFixed(1) + 'K';
                        return val.toString();
                    }
                },
                splitLine: { lineStyle: { color: '#f0f0f0' } }
            },
            {
                type: 'value',
                name: '价格',
                position: 'right',
                axisLine: { lineStyle: { color: '#1890ff' } },
                axisLabel: {
                    color: '#1890ff',
                    formatter: (val: number) => '$' + val.toFixed(6)
                },
                splitLine: { show: false }
            }
        ],
        series: [
            {
                name: '市值',
                type: 'line',
                yAxisIndex: 0,
                smooth: true,
                lineStyle: { color: '#52c41a', width: 2 },
                areaStyle: {
                    color: {
                        type: 'linear',
                        x: 0, y: 0, x2: 0, y2: 1,
                        colorStops: [
                            { offset: 0, color: 'rgba(82, 196, 26, 0.2)' },
                            { offset: 1, color: 'rgba(82, 196, 26, 0.02)' }
                        ]
                    }
                },
                data: chartData.map(d => [dayjs.utc(d.timestamp).valueOf(), d.marketCap])
            },
            {
                name: '价格',
                type: 'line',
                yAxisIndex: 1,
                smooth: true,
                lineStyle: { color: '#1890ff', width: 2 },
                data: chartData.map(d => [dayjs.utc(d.timestamp).valueOf(), d.priceUsd])
            }
        ]
    };


    const selectedSession = sessions.find(s => s.id === selectedSessionId);

    return (
        <Card
            title="📈 市值曲线"
            className="chart-card"
            extra={
                <Space>
                    <Select
                        value={selectedSessionId}
                        onChange={setSelectedSessionId}
                        style={{ width: 150 }}
                        placeholder="选择 Token"
                    >
                        {sessions.map(s => (
                            <Option key={s.id} value={s.id}>
                                {s.tokenSymbol || s.tokenAddress.slice(0, 8)}
                            </Option>
                        ))}
                    </Select>
                    <Select value={timeRange} onChange={setTimeRange} style={{ width: 80 }}>
                        <Option value={1}>1h</Option>
                        <Option value={6}>6h</Option>
                        <Option value={24}>24h</Option>
                        <Option value={168}>7d</Option>
                    </Select>
                </Space>
            }
        >
            <Spin spinning={loading}>
                {chartData.length > 0 ? (
                    <ReactECharts
                        option={option}
                        style={{ height: 300 }}
                    />
                ) : (
                    <div style={{ height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999' }}>
                        {selectedSession ? '暂无数据' : '请选择一个 Token'}
                    </div>
                )}
            </Spin>
        </Card>
    );
};

export default MarketCapChart;
