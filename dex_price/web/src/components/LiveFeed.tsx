// 实时数据流表格组件
import React, { useMemo } from 'react';
import { Table, Tag, Typography, Button } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { HighlightCell } from './HighlightCell';
import { useAppStore, useColumnStore } from '../stores/appStore';
import type { PushData, TrackingSession } from '../stores/appStore';
import { ColumnSelector } from './ColumnSelector';
import { liveFeedColumnsDefinition } from '../constants/columns';
import { DownOutlined, RightOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';

dayjs.extend(utc);
dayjs.extend(timezone);

const { Text } = Typography;

// 预定义一组好看的颜色
const presetColors = [
    '#f56a00', '#7265e6', '#ffbf00', '#00a2ae',
    '#1890ff', '#52c41a', '#eb2f96', '#722ed1'
];

const getTokenColor = (symbol: string) => {
    if (!symbol) return '#999';
    let hash = 0;
    for (let i = 0; i < symbol.length; i++) {
        hash = symbol.charCodeAt(i) + ((hash << 5) - hash);
    }
    return presetColors[Math.abs(hash) % presetColors.length];
};

// 数字格式化
const formatNumber = (num: number | null | undefined): string => {
    if (num === null || num === undefined) return '-';
    if (num >= 1e9) return (num / 1e9).toFixed(2) + 'B';
    if (num >= 1e6) return (num / 1e6).toFixed(2) + 'M';
    if (num >= 1e3) return (num / 1e3).toFixed(2) + 'K';
    return num.toFixed(2);
};

const formatPrice = (price: number | null | undefined): string => {
    if (price === null || price === undefined) return '-';
    if (price < 0.0001) return price.toExponential(4);
    if (price < 1) return price.toFixed(6);
    return price.toFixed(4);
};

export const LiveFeed: React.FC = () => {
    const sessions = useAppStore(state => state.sessions);
    const latestDataMap = useAppStore(state => state.latestData);
    const dataLogs = useAppStore(state => state.dataLogs);
    const { liveFeedVisibleColumns, setLiveFeedVisibleColumns } = useColumnStore();

    // 辅助函数：根据列 key 获取渲染配置
    const getColumnConfig = (key: string): ColumnsType<any>[number] | null => {
        // 通用渲染器
        const renderPrice = (data: PushData) => (
            <HighlightCell value={data.current.priceUsd} delta={data.deltas.priceUsd} formatter={formatPrice} prefix="$" />
        );
        const renderNumber = (val: number, delta: any) => (
            <HighlightCell value={val} delta={delta} formatter={formatNumber} prefix="$" />
        );
        const renderTxns = (buys: number, sells: number) => (
            <span>
                <span style={{ color: '#52c41a' }}>{buys}</span>
                <span style={{ margin: '0 4px', color: '#e8e8e8' }}>/</span>
                <span style={{ color: '#ff4d4f' }}>{sells}</span>
            </span>
        );
        const renderChange = (val: number) => (
            <Tag color={val >= 0 ? 'success' : 'error'} style={{ margin: 0, minWidth: 60, textAlign: 'center' }}>
                {val >= 0 ? '+' : ''}{val.toFixed(2)}%
            </Tag>
        );

        switch (key) {
            case 'timestamp':
                return {
                    title: '时间',
                    key: 'timestamp',
                    width: 100,
                    fixed: 'right',
                    align: 'right',
                    render: (_, record) => {
                        // 如果是 Session，从 latestData 获取时间
                        const timestamp = (record as any).timestamp || (latestDataMap.get((record as any).id)?.timestamp);
                        if (!timestamp) return '-';
                        return (
                            <Text type="secondary" style={{ fontFamily: 'monospace' }}>
                                {dayjs(timestamp).tz('Asia/Shanghai').format('HH:mm:ss')}
                            </Text>
                        );
                    }
                };
            case 'symbol':
                return {
                    title: 'Token',
                    key: 'symbol',
                    width: 140,
                    fixed: 'left',
                    render: (_, record: any) => {
                        const symbol = record.tokenSymbol || record.symbol; // 兼容 Session 和 PushData
                        return (
                            <Tag color={getTokenColor(symbol)} style={{ fontWeight: 600, marginRight: 0 }}>
                                {symbol}
                            </Tag>
                        );
                    }
                };
            case 'price': return {
                title: '价格 (USD)', key, width: 120, align: 'right', render: (_, r: any) => {
                    const data = r.current ? r : latestDataMap.get(r.id);
                    if (!data) return '-';
                    return renderPrice(data);
                }
            };
            case 'marketCap': return {
                title: '市值', key, width: 100, align: 'right', render: (_, r: any) => {
                    const data = r.current ? r : latestDataMap.get(r.id);
                    if (!data) return '-';
                    return renderNumber(data.current.marketCap, data.deltas.marketCap);
                }
            };
            case 'fdv': return {
                title: 'FDV', key, width: 100, align: 'right', render: (_, r: any) => {
                    const data = r.current ? r : latestDataMap.get(r.id);
                    if (!data) return '-';
                    return renderNumber(data.current.fdv, data.deltas.fdv);
                }
            };
            case 'liquidity': return {
                title: '流动性', key, width: 100, align: 'right', render: (_, r: any) => {
                    const data = r.current ? r : latestDataMap.get(r.id);
                    if (!data) return '-';
                    return renderNumber(data.current.liquidityUsd, data.deltas.liquidityUsd);
                }
            };

            // Volume
            case 'volume_m5': return {
                title: 'Vol 5m', key, width: 100, align: 'right', render: (_, r: any) => {
                    const data = r.current ? r : latestDataMap.get(r.id);
                    if (!data) return '-';
                    return renderNumber(data.current.volume.m5, data.deltas.volumeM5);
                }
            };
            case 'volume_h1': return {
                title: 'Vol 1h', key, width: 100, align: 'right', render: (_, r: any) => {
                    const data = r.current ? r : latestDataMap.get(r.id);
                    if (!data) return '-';
                    return renderNumber(data.current.volume.h1, data.deltas.volumeH1);
                }
            };
            case 'volume_h6': return {
                title: 'Vol 6h', key, width: 100, align: 'right', render: (_, r: any) => {
                    const data = r.current ? r : latestDataMap.get(r.id);
                    if (!data) return '-';
                    return renderNumber(data.current.volume.h6, data.deltas.volumeH6);
                }
            };
            case 'volume_h24': return {
                title: 'Vol 24h', key, width: 100, align: 'right', render: (_, r: any) => {
                    const data = r.current ? r : latestDataMap.get(r.id);
                    if (!data) return '-';
                    return renderNumber(data.current.volume.h24, data.deltas.volumeH24);
                }
            };

            // Txns
            case 'txns_m5': return {
                title: 'Txns 5m', key, width: 120, align: 'center', render: (_, r: any) => {
                    const data = r.current ? r : latestDataMap.get(r.id);
                    if (!data) return '-';
                    return renderTxns(data.current.txns.m5.buys, data.current.txns.m5.sells);
                }
            };
            case 'txns_h1': return {
                title: 'Txns 1h', key, width: 120, align: 'center', render: (_, r: any) => {
                    const data = r.current ? r : latestDataMap.get(r.id);
                    if (!data) return '-';
                    return renderTxns(data.current.txns.h1.buys, data.current.txns.h1.sells);
                }
            };
            case 'txns_h6': return {
                title: 'Txns 6h', key, width: 120, align: 'center', render: (_, r: any) => {
                    const data = r.current ? r : latestDataMap.get(r.id);
                    if (!data) return '-';
                    return renderTxns(data.current.txns.h6.buys, data.current.txns.h6.sells);
                }
            };
            case 'txns_h24': return {
                title: 'Txns 24h', key, width: 120, align: 'center', render: (_, r: any) => {
                    const data = r.current ? r : latestDataMap.get(r.id);
                    if (!data) return '-';
                    return renderTxns(data.current.txns.h24.buys, data.current.txns.h24.sells);
                }
            };

            // Price Change
            case 'priceChange_m5': return {
                title: '涨跌 5m', key, width: 100, align: 'right', render: (_, r: any) => {
                    const data = r.current ? r : latestDataMap.get(r.id);
                    if (!data) return '-';
                    return renderChange(data.current.priceChange.m5);
                }
            };
            case 'priceChange_h1': return {
                title: '涨跌 1h', key, width: 100, align: 'right', render: (_, r: any) => {
                    const data = r.current ? r : latestDataMap.get(r.id);
                    if (!data) return '-';
                    return renderChange(data.current.priceChange.h1);
                }
            };
            case 'priceChange_h6': return {
                title: '涨跌 6h', key, width: 100, align: 'right', render: (_, r: any) => {
                    const data = r.current ? r : latestDataMap.get(r.id);
                    if (!data) return '-';
                    return renderChange(data.current.priceChange.h6);
                }
            };
            case 'priceChange_h24': return {
                title: '涨跌 24h', key, width: 100, align: 'right', render: (_, r: any) => {
                    const data = r.current ? r : latestDataMap.get(r.id);
                    if (!data) return '-';
                    return renderChange(data.current.priceChange.h24);
                }
            };

            default: return null;
        }
    };

    const columns = useMemo(() => {
        return liveFeedColumnsDefinition
            .filter(def => liveFeedVisibleColumns.includes(def.key))
            .map(def => getColumnConfig(def.key))
            .filter(Boolean) as ColumnsType<any>;
    }, [liveFeedVisibleColumns, latestDataMap]);

    // 展开行的子表格
    const expandedRowRender = (record: TrackingSession) => {
        const historyLogs = dataLogs.filter(log => log.sessionId === record.id);

        const childColumns = columns.filter(col => col.key !== 'symbol'); // 子表格不显示 Token 列

        return (
            <Table
                columns={childColumns}
                dataSource={historyLogs}
                pagination={false}
                size="small"
                rowKey="timestamp"
                className="history-table"
                showHeader={true}
            />
        );
    };

    return (
        <div className="live-feed-container">
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
                <ColumnSelector
                    allColumns={liveFeedColumnsDefinition}
                    visibleColumns={liveFeedVisibleColumns}
                    onChange={setLiveFeedVisibleColumns}
                />
            </div>
            <Table
                columns={columns}
                dataSource={sessions} // 主表格显示 Session 列表
                rowKey="id"
                pagination={false}
                scroll={{ y: 'calc(100vh - 450px)' }}
                size="middle"
                className="live-feed-table"
                expandable={{
                    expandedRowRender,
                    expandRowByClick: true, // 点击行展开
                    columnWidth: 48,
                    fixed: 'left',
                    expandIcon: ({ expanded, onExpand, record }) => (
                        <Button
                            type="text"
                            size="small"
                            icon={expanded ? <DownOutlined /> : <RightOutlined />}
                            onClick={e => onExpand(record, e)}
                            style={{ marginRight: 8 }}
                        />
                    )
                }}
            />
        </div>
    );
};
