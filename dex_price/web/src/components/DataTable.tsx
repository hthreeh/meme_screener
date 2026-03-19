// 数据表格组件
import React, { useMemo } from 'react';
import { Table, Button, Tag, Popconfirm, Space, message, InputNumber, Popover } from 'antd';
import {
    PauseCircleOutlined,
    PlayCircleOutlined,
    DeleteOutlined,
    DownloadOutlined,
    SettingOutlined
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { HighlightCell, PriceChange, TxnsDisplay } from './HighlightCell';
import { useAppStore, useColumnStore } from '../stores/appStore';
import type { TrackingSession, PushData } from '../stores/appStore';
import { pauseTracking, resumeTracking, deleteSession, getExportUrl, updateFrequency } from '../services/api';
import './DataTable.css';

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

interface TableRow {
    key: string;
    session: TrackingSession;
    data: PushData | null;
}

export const DataTable: React.FC = () => {
    const sessions = useAppStore(state => state.sessions);
    const latestData = useAppStore(state => state.latestData);
    const removeSession = useAppStore(state => state.removeSession);
    const updateSession = useAppStore(state => state.updateSession);
    const { visibleColumns } = useColumnStore();

    const handlePause = async (sessionId: string) => {
        try {
            await pauseTracking(sessionId);
            updateSession(sessionId, { status: 'paused' });
            message.success('已暂停追踪');
        } catch (error: any) {
            message.error(error.message);
        }
    };

    const handleResume = async (sessionId: string) => {
        try {
            await resumeTracking(sessionId);
            updateSession(sessionId, { status: 'running' });
            message.success('已恢复追踪');
        } catch (error: any) {
            message.error(error.message);
        }
    };

    const handleDelete = async (sessionId: string) => {
        try {
            await deleteSession(sessionId);
            removeSession(sessionId);
            message.success('已删除');
        } catch (error: any) {
            message.error(error.message);
        }
    };

    const handleExport = (sessionId: string) => {
        window.open(getExportUrl(sessionId), '_blank');
    };

    const handleUpdateFrequency = async (sessionId: string, newFrequency: number) => {
        try {
            await updateFrequency(sessionId, newFrequency);
            updateSession(sessionId, { frequencySeconds: newFrequency });
            message.success(`已更新频率为 ${newFrequency} 秒`);
        } catch (error: any) {
            message.error(error.message);
        }
    };

    // 定义所有列
    const columnDefinitions: Record<string, ColumnsType<TableRow>[number]> = {
        symbol: {
            title: 'Token',
            key: 'symbol',
            fixed: 'left' as const,
            width: 120,
            render: (_, record) => (
                <div className="token-cell">
                    <span className="token-symbol">{record.session.tokenSymbol || '???'}</span>
                    <Tag color={record.session.status === 'running' ? 'green' : record.session.status === 'paused' ? 'orange' : 'default'}>
                        {record.session.status === 'running' ? '运行中' : record.session.status === 'paused' ? '已暂停' : '已停止'}
                    </Tag>
                </div>
            ),
        },
        price: {
            title: '价格 (USD)',
            key: 'price',
            width: 120,
            render: (_, record) => (
                <HighlightCell
                    value={record.data?.current.priceUsd ?? record.session.baseData?.priceUsd}
                    delta={record.data?.deltas.priceUsd}
                    formatter={formatPrice}
                    prefix="$"
                />
            ),
        },
        marketCap: {
            title: '市值',
            key: 'marketCap',
            width: 100,
            render: (_, record) => (
                <HighlightCell
                    value={record.data?.current.marketCap ?? record.session.baseData?.marketCap}
                    delta={record.data?.deltas.marketCap}
                    formatter={formatNumber}
                    prefix="$"
                />
            ),
        },
        fdv: {
            title: 'FDV',
            key: 'fdv',
            width: 100,
            render: (_, record) => (
                <HighlightCell
                    value={record.data?.current.fdv ?? record.session.baseData?.fdv}
                    delta={record.data?.deltas.fdv}
                    formatter={formatNumber}
                    prefix="$"
                />
            ),
        },
        liquidity: {
            title: '流动性',
            key: 'liquidity',
            width: 100,
            render: (_, record) => (
                <HighlightCell
                    value={record.data?.current.liquidityUsd ?? record.session.baseData?.liquidityUsd}
                    delta={record.data?.deltas.liquidityUsd}
                    formatter={formatNumber}
                    prefix="$"
                />
            ),
        },
        volume_m5: {
            title: '交易量 5m',
            key: 'volume_m5',
            width: 100,
            render: (_, record) => (
                <HighlightCell
                    value={record.data?.current.volume.m5 ?? record.session.baseData?.volume.m5}
                    delta={record.data?.deltas.volumeM5}
                    formatter={formatNumber}
                    prefix="$"
                />
            ),
        },
        volume_h1: {
            title: '交易量 1h',
            key: 'volume_h1',
            width: 100,
            render: (_, record) => (
                <HighlightCell
                    value={record.data?.current.volume.h1 ?? record.session.baseData?.volume.h1}
                    delta={record.data?.deltas.volumeH1}
                    formatter={formatNumber}
                    prefix="$"
                />
            ),
        },
        volume_h6: {
            title: '交易量 6h',
            key: 'volume_h6',
            width: 100,
            render: (_, record) => (
                <HighlightCell
                    value={record.data?.current.volume.h6 ?? record.session.baseData?.volume.h6}
                    delta={record.data?.deltas.volumeH6}
                    formatter={formatNumber}
                    prefix="$"
                />
            ),
        },
        volume_h24: {
            title: '交易量 24h',
            key: 'volume_h24',
            width: 100,
            render: (_, record) => (
                <HighlightCell
                    value={record.data?.current.volume.h24 ?? record.session.baseData?.volume.h24}
                    delta={record.data?.deltas.volumeH24}
                    formatter={formatNumber}
                    prefix="$"
                />
            ),
        },
        txns_m5: {
            title: '交易次数 5m',
            key: 'txns_m5',
            width: 100,
            render: (_, record) => {
                const txns = record.data?.current.txns.m5 ?? record.session.baseData?.txns.m5;
                if (!txns) return '-';
                return <TxnsDisplay buys={txns.buys} sells={txns.sells} buysDelta={record.data?.deltas.txnsM5Buys} />;
            },
        },
        txns_h1: {
            title: '交易次数 1h',
            key: 'txns_h1',
            width: 100,
            render: (_, record) => {
                const txns = record.data?.current.txns.h1 ?? record.session.baseData?.txns.h1;
                if (!txns) return '-';
                return <TxnsDisplay buys={txns.buys} sells={txns.sells} buysDelta={record.data?.deltas.txnsH1Buys} />;
            },
        },
        txns_h6: {
            title: '交易次数 6h',
            key: 'txns_h6',
            width: 100,
            render: (_, record) => {
                const txns = record.data?.current.txns.h6 ?? record.session.baseData?.txns.h6;
                if (!txns) return '-';
                return <TxnsDisplay buys={txns.buys} sells={txns.sells} />;
            },
        },
        txns_h24: {
            title: '交易次数 24h',
            key: 'txns_h24',
            width: 100,
            render: (_, record) => {
                const txns = record.data?.current.txns.h24 ?? record.session.baseData?.txns.h24;
                if (!txns) return '-';
                return <TxnsDisplay buys={txns.buys} sells={txns.sells} />;
            },
        },
        priceChange_m5: {
            title: '涨跌幅 5m',
            key: 'priceChange_m5',
            width: 90,
            render: (_, record) => (
                <PriceChange value={record.data?.current.priceChange.m5 ?? record.session.baseData?.priceChange.m5} />
            ),
        },
        priceChange_h1: {
            title: '涨跌幅 1h',
            key: 'priceChange_h1',
            width: 90,
            render: (_, record) => (
                <PriceChange value={record.data?.current.priceChange.h1 ?? record.session.baseData?.priceChange.h1} />
            ),
        },
        priceChange_h6: {
            title: '涨跌幅 6h',
            key: 'priceChange_h6',
            width: 90,
            render: (_, record) => (
                <PriceChange value={record.data?.current.priceChange.h6 ?? record.session.baseData?.priceChange.h6} />
            ),
        },
        priceChange_h24: {
            title: '涨跌幅 24h',
            key: 'priceChange_h24',
            width: 90,
            render: (_, record) => (
                <PriceChange value={record.data?.current.priceChange.h24 ?? record.session.baseData?.priceChange.h24} />
            ),
        },
        actions: {
            title: '操作',
            key: 'actions',
            fixed: 'right' as const,
            width: 200,
            render: (_, record) => (
                <Space size="small">
                    {record.session.status === 'running' ? (
                        <Button
                            size="small"
                            icon={<PauseCircleOutlined />}
                            onClick={() => handlePause(record.session.id)}
                        />
                    ) : record.session.status === 'paused' ? (
                        <Button
                            size="small"
                            type="primary"
                            icon={<PlayCircleOutlined />}
                            onClick={() => handleResume(record.session.id)}
                        />
                    ) : null}
                    <Popover
                        content={
                            <div style={{ width: 150 }}>
                                <div style={{ marginBottom: 8, fontSize: 12, color: '#666' }}>
                                    当前: {record.session.frequencySeconds}s
                                </div>
                                <InputNumber
                                    min={10}
                                    max={3600}
                                    defaultValue={record.session.frequencySeconds}
                                    addonAfter="秒"
                                    size="small"
                                    style={{ width: '100%' }}
                                    onPressEnter={(e) => {
                                        const val = parseInt((e.target as HTMLInputElement).value);
                                        if (val >= 10) handleUpdateFrequency(record.session.id, val);
                                    }}
                                    onBlur={(e) => {
                                        const val = parseInt(e.target.value);
                                        if (val >= 10 && val !== record.session.frequencySeconds) {
                                            handleUpdateFrequency(record.session.id, val);
                                        }
                                    }}
                                />
                            </div>
                        }
                        title="调整追踪频率"
                        trigger="click"
                        placement="left"
                    >
                        <Button size="small" icon={<SettingOutlined />} />
                    </Popover>
                    <Button
                        size="small"
                        icon={<DownloadOutlined />}
                        onClick={() => handleExport(record.session.id)}
                    />
                    <Popconfirm
                        title="确定删除此追踪?"
                        onConfirm={() => handleDelete(record.session.id)}
                        okText="删除"
                        cancelText="取消"
                    >
                        <Button size="small" danger icon={<DeleteOutlined />} />
                    </Popconfirm>
                </Space>
            ),
        },
    };

    // 根据 visibleColumns 过滤显示列，确保 actions 始终在最后
    const columns = useMemo(() => {
        const cols = visibleColumns
            .filter(key => key !== 'actions') // 先排除 actions
            .map(key => columnDefinitions[key])
            .filter(Boolean) as ColumnsType<TableRow>;

        // 确保 actions 列始终在最后
        if (visibleColumns.includes('actions') && columnDefinitions.actions) {
            cols.push(columnDefinitions.actions as ColumnsType<TableRow>[number]);
        }

        return cols;
    }, [visibleColumns]);

    // 表格数据
    const dataSource: TableRow[] = useMemo(() => {
        return sessions.map(session => ({
            key: session.id,
            session,
            data: latestData.get(session.id) || null,
        }));
    }, [sessions, latestData]);

    return (
        <Table
            columns={columns}
            dataSource={dataSource}
            pagination={false}
            scroll={{ x: 'max-content', y: 'calc(100vh - 280px)' }}
            size="small"
            className="data-table"
            rowClassName={(record) =>
                record.session.status === 'stopped' ? 'row-stopped' : ''
            }
        />
    );
};

export default DataTable;
