// 手动交易组件
import React, { useState } from 'react';
import { Card, Input, InputNumber, Button, Space, message, Alert } from 'antd';
import { SendOutlined } from '@ant-design/icons';
import { createManualOrder } from '../services/api';

export const ManualTrade: React.FC = () => {
    const [ca, setCa] = useState('');
    const [amount, setAmount] = useState(0.2);
    const [loading, setLoading] = useState(false);
    const [lastResult, setLastResult] = useState<any>(null);

    const handleSubmit = async () => {
        if (!ca.trim()) {
            message.error('请输入代币 CA');
            return;
        }

        if (ca.length < 30 || ca.length > 50) {
            message.error('CA 地址格式不正确 (应为 30-50 字符)');
            return;
        }

        setLoading(true);
        setLastResult(null);

        try {
            const result = await createManualOrder(ca.trim(), amount);
            setLastResult(result);

            if (result.success) {
                if (result.token_name) {
                    message.success(`买入成功: ${result.token_name}`);
                    setCa('');
                } else {
                    message.info(result.message);
                }
            } else {
                message.error(result.message);
            }
        } catch (error: any) {
            const errMsg = error.message || '提交失败';
            setLastResult({ success: false, message: errMsg });
            message.error(errMsg);
        } finally {
            setLoading(false);
        }
    };

    return (
        <Card
            title="🎯 手动买入"
            size="small"
            style={{ marginBottom: 16 }}
        >
            <Space direction="vertical" style={{ width: '100%' }}>
                <Space.Compact style={{ width: '100%' }}>
                    <Input
                        placeholder="输入代币 CA (合约地址)"
                        value={ca}
                        onChange={e => setCa(e.target.value)}
                        style={{ flex: 1 }}
                        disabled={loading}
                        onPressEnter={handleSubmit}
                    />
                    <InputNumber
                        value={amount}
                        onChange={v => setAmount(v || 0.2)}
                        min={0.01}
                        max={10}
                        step={0.1}
                        addonAfter="SOL"
                        style={{ width: 130 }}
                        disabled={loading}
                    />
                    <Button
                        type="primary"
                        icon={<SendOutlined />}
                        onClick={handleSubmit}
                        loading={loading}
                    >
                        买入
                    </Button>
                </Space.Compact>

                {lastResult && (
                    <Alert
                        type={lastResult.success ? 'success' : 'error'}
                        message={lastResult.success ? '交易成功' : '交易失败'}
                        description={
                            lastResult.success && lastResult.token_name ? (
                                <ul style={{ margin: 0, paddingLeft: 20 }}>
                                    <li><b>代币:</b> {lastResult.token_name}</li>
                                    <li><b>买入市值:</b> ${lastResult.buy_price?.toLocaleString()}</li>
                                    <li><b>买入金额:</b> {lastResult.buy_amount} SOL</li>
                                    <li><b>当前余额:</b> {lastResult.balance_after?.toFixed(2)} SOL</li>
                                </ul>
                            ) : (
                                lastResult.message
                            )
                        }
                        showIcon
                        closable
                        onClose={() => setLastResult(null)}
                    />
                )}

                <div style={{ fontSize: 12, color: '#888' }}>
                    提示: 系统将立即尝试买入 (最多等待10秒)，成交后自动执行止盈止损 (1.5x/3x/10x，-30%)
                </div>
            </Space>
        </Card>
    );
};

export default ManualTrade;
