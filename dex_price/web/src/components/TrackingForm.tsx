// 添加追踪表单组件
import React, { useState } from 'react';
import { Form, Input, Select, InputNumber, Button, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { startTracking } from '../services/api';
import { useAppStore } from '../stores/appStore';

const { Option } = Select;

const chains = [
    { value: 'solana', label: 'Solana' },
    { value: 'ethereum', label: 'Ethereum' },
    { value: 'bsc', label: 'BSC' },
    { value: 'base', label: 'Base' },
    { value: 'arbitrum', label: 'Arbitrum' },
];

interface FormValues {
    chainId: string;
    tokenAddress: string;
    frequencySeconds?: number;
}

export const TrackingForm: React.FC = () => {
    const [form] = Form.useForm();
    const [loading, setLoading] = useState(false);
    const addSession = useAppStore(state => state.addSession);

    const onFinish = async (values: FormValues) => {
        setLoading(true);
        try {
            const result: any = await startTracking(
                values.chainId,
                values.tokenAddress.trim(),
                values.frequencySeconds
            );

            message.success(`开始追踪 ${result.session.tokenSymbol || values.tokenAddress}`);
            addSession(result.session);
            form.resetFields(['tokenAddress']);
        } catch (error: any) {
            message.error(error.message || '添加追踪失败');
        } finally {
            setLoading(false);
        }
    };

    return (
        <Form
            form={form}
            layout="inline"
            onFinish={onFinish}
            initialValues={{ chainId: 'solana', frequencySeconds: 60 }}
            className="tracking-form"
        >
            <Form.Item name="chainId" label="链">
                <Select style={{ width: 120 }}>
                    {chains.map(chain => (
                        <Option key={chain.value} value={chain.value}>
                            {chain.label}
                        </Option>
                    ))}
                </Select>
            </Form.Item>

            <Form.Item
                name="tokenAddress"
                label="Token 地址"
                rules={[{ required: true, message: '请输入 Token 地址' }]}
            >
                <Input
                    placeholder="输入 Token 合约地址"
                    style={{ width: 360 }}
                    allowClear
                />
            </Form.Item>

            <Form.Item name="frequencySeconds" label="频率(秒)">
                <InputNumber min={10} max={300} style={{ width: 80 }} />
            </Form.Item>

            <Form.Item>
                <Button
                    type="primary"
                    htmlType="submit"
                    loading={loading}
                    icon={<PlusOutlined />}
                >
                    添加追踪
                </Button>
            </Form.Item>
        </Form>
    );
};

export default TrackingForm;
