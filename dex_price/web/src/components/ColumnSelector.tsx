// 列选择器组件
import React from 'react';
import { Dropdown, Button, Checkbox, Space } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import type { CheckboxChangeEvent } from 'antd/es/checkbox';

export interface ColumnDefinition {
    key: string;
    label: string;
    fixed?: boolean;
}

interface ColumnSelectorProps {
    allColumns: ColumnDefinition[];
    visibleColumns: string[];
    onChange: (columns: string[]) => void;
}

export const ColumnSelector: React.FC<ColumnSelectorProps> = ({
    allColumns,
    visibleColumns,
    onChange
}) => {
    const handleChange = (key: string) => (e: CheckboxChangeEvent) => {
        if (e.target.checked) {
            onChange([...visibleColumns, key]);
        } else {
            onChange(visibleColumns.filter(k => k !== key));
        }
    };

    const handleSelectAll = () => {
        onChange(allColumns.map(c => c.key));
    };

    const handleDeselectAll = () => {
        const fixedColumns = allColumns.filter(c => c.fixed).map(c => c.key);
        onChange(fixedColumns);
    };

    const menuContent = (
        <div style={{ padding: 12, background: '#fff', borderRadius: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.15)' }}>
            <Space direction="vertical" size={4}>
                <div style={{ marginBottom: 8, borderBottom: '1px solid #f0f0f0', paddingBottom: 8 }}>
                    <Button size="small" type="link" onClick={handleSelectAll} style={{ padding: '0 8px 0 0' }}>全选</Button>
                    <Button size="small" type="link" onClick={handleDeselectAll} style={{ padding: 0 }}>重置</Button>
                </div>
                {allColumns.map(col => (
                    <Checkbox
                        key={col.key}
                        checked={visibleColumns.includes(col.key)}
                        onChange={handleChange(col.key)}
                        disabled={col.fixed}
                    >
                        {col.label}
                    </Checkbox>
                ))}
            </Space>
        </div>
    );

    return (
        <Dropdown
            dropdownRender={() => menuContent}
            trigger={['click']}
            placement="bottomRight"
        >
            <Button icon={<SettingOutlined />}>
                列设置 ({visibleColumns.length})
            </Button>
        </Dropdown>
    );
};

export default ColumnSelector;
