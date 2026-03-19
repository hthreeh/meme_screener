// 历史归档组件 - 显示已删除的会话，支持导出历史数据
import React, { useEffect, useState } from 'react';
import { Table, Button, Tag, Empty, message, Spin } from 'antd';
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { getDeletedSessions, getExportUrl } from '../services/api';
import dayjs from 'dayjs';

interface DeletedSession {
    id: string;
    chainId: string;
    tokenAddress: string;
    tokenName: string;
    tokenSymbol: string;
    createdAt: string;
    updatedAt: string;
}

export const HistoryArchive: React.FC = () => {
    const [sessions, setSessions] = useState<DeletedSession[]>([]);
    const [loading, setLoading] = useState(false);

    const fetchDeletedSessions = async () => {
        setLoading(true);
        try {
            const result = await getDeletedSessions();
            setSessions(result.sessions || []);
        } catch (error: any) {
            message.error('获取历史归档失败: ' + error.message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchDeletedSessions();
    }, []);

    const handleExport = (sessionId: string) => {
        window.open(getExportUrl(sessionId), '_blank');
    };

    const columns: ColumnsType<DeletedSession> = [
        {
            title: 'Token',
            key: 'token',
            width: 150,
            render: (_, record) => (
                <div>
                    <Tag color="blue" style={{ fontWeight: 600 }}>{record.tokenSymbol}</Tag>
                    <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>
                        {record.tokenName}
                    </div>
                </div>
            ),
        },
        {
            title: '链',
            dataIndex: 'chainId',
            key: 'chainId',
            width: 100,
            render: (chainId) => (
                <Tag>{chainId}</Tag>
            ),
        },
        {
            title: '合约地址',
            dataIndex: 'tokenAddress',
            key: 'tokenAddress',
            width: 200,
            ellipsis: true,
            render: (addr) => (
                <span style={{ fontFamily: 'monospace', fontSize: 12 }}>
                    {addr.slice(0, 8)}...{addr.slice(-6)}
                </span>
            ),
        },
        {
            title: '创建时间',
            dataIndex: 'createdAt',
            key: 'createdAt',
            width: 160,
            render: (time) => dayjs(time).format('YYYY-MM-DD HH:mm'),
        },
        {
            title: '删除时间',
            dataIndex: 'updatedAt',
            key: 'updatedAt',
            width: 160,
            render: (time) => dayjs(time).format('YYYY-MM-DD HH:mm'),
        },
        {
            title: '操作',
            key: 'actions',
            width: 120,
            fixed: 'right',
            render: (_, record) => (
                <Button
                    type="primary"
                    icon={<DownloadOutlined />}
                    onClick={() => handleExport(record.id)}
                >
                    导出数据
                </Button>
            ),
        },
    ];

    return (
        <div style={{ padding: '16px 0' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <div>
                    <span style={{ fontSize: 14, color: '#666' }}>
                        已归档 {sessions.length} 个追踪记录，数据已保留可随时导出
                    </span>
                </div>
                <Button
                    icon={<ReloadOutlined />}
                    onClick={fetchDeletedSessions}
                    loading={loading}
                >
                    刷新
                </Button>
            </div>

            <Spin spinning={loading}>
                {sessions.length === 0 ? (
                    <Empty
                        description="暂无归档记录"
                        style={{ padding: 60 }}
                    />
                ) : (
                    <Table
                        columns={columns}
                        dataSource={sessions}
                        rowKey="id"
                        pagination={false}
                        scroll={{ y: 'calc(100vh - 400px)' }}
                        size="middle"
                    />
                )}
            </Spin>
        </div>
    );
};

export default HistoryArchive;
