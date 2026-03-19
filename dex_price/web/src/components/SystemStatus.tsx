// 系统状态组件
import React, { useEffect } from 'react';
import { Tag, Tooltip, Progress, Space } from 'antd';
import {
    WifiOutlined,
    ApiOutlined,
    DatabaseOutlined,
    ClockCircleOutlined
} from '@ant-design/icons';
import { useAppStore } from '../stores/appStore';
import { getSystemStatus } from '../services/api';
import './SystemStatus.css';

export const SystemStatus: React.FC = () => {
    const isConnected = useAppStore(state => state.isConnected);
    const systemStatus = useAppStore(state => state.systemStatus);
    const setSystemStatus = useAppStore(state => state.setSystemStatus);

    useEffect(() => {
        const fetchStatus = async () => {
            try {
                const status: any = await getSystemStatus();
                setSystemStatus(status);
            } catch (error) {
                console.error('获取系统状态失败:', error);
            }
        };

        fetchStatus();
        const interval = setInterval(fetchStatus, 30000);
        return () => clearInterval(interval);
    }, [setSystemStatus]);

    const formatUptime = (seconds: number): string => {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        return `${hours}h ${minutes}m`;
    };

    return (
        <div className="system-status">
            <Space size="middle">
                {/* 连接状态 */}
                <Tooltip title={isConnected ? '实时连接正常' : '连接断开，正在重连...'}>
                    <Tag
                        icon={<WifiOutlined />}
                        color={isConnected ? 'success' : 'error'}
                    >
                        {isConnected ? '已连接' : '断开'}
                    </Tag>
                </Tooltip>

                {/* API 配额 */}
                {systemStatus && (
                    <>
                        <Tooltip title={`API 调用: ${systemStatus.api.used}/${systemStatus.api.limit}/分钟`}>
                            <div className="api-quota">
                                <ApiOutlined />
                                <Progress
                                    percent={systemStatus.api.usagePercent}
                                    size="small"
                                    showInfo={false}
                                    strokeColor={systemStatus.api.usagePercent > 80 ? '#ff4d4f' : '#52c41a'}
                                    style={{ width: 60 }}
                                />
                                <span>{systemStatus.api.used}/{systemStatus.api.limit}</span>
                            </div>
                        </Tooltip>

                        <Tooltip title={`活跃追踪任务: ${systemStatus.activeTasks}`}>
                            <Tag icon={<ClockCircleOutlined />}>
                                {systemStatus.activeTasks} 个任务
                            </Tag>
                        </Tooltip>

                        <Tooltip title={`数据库大小: ${systemStatus.database.sizeMB} MB`}>
                            <Tag icon={<DatabaseOutlined />}>
                                {systemStatus.database.sizeMB} MB
                            </Tag>
                        </Tooltip>

                        <Tooltip title={`服务器已运行: ${formatUptime(systemStatus.uptime)}`}>
                            <Tag>
                                运行 {formatUptime(systemStatus.uptime)}
                            </Tag>
                        </Tooltip>
                    </>
                )}
            </Space>
        </div>
    );
};

export default SystemStatus;
