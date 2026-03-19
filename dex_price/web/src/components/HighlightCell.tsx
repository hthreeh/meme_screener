// 高亮单元格组件
import React from 'react';
import './HighlightCell.css';

interface HighlightCellProps {
    value: number | null | undefined;
    delta?: 'up' | 'down' | 'same';
    formatter?: (value: number) => string;
    prefix?: string;
    suffix?: string;
}

export const HighlightCell: React.FC<HighlightCellProps> = ({
    value,
    delta = 'same',
    formatter,
    prefix = '',
    suffix = ''
}) => {
    if (value === null || value === undefined) {
        return <span className="cell-empty">-</span>;
    }

    const formattedValue = formatter ? formatter(value) : String(value);

    const className = delta === 'up'
        ? 'cell-up'
        : delta === 'down'
            ? 'cell-down'
            : 'cell-same';

    return (
        <span className={`highlight-cell ${className}`}>
            {prefix}{formattedValue}{suffix}
        </span>
    );
};

// 价格变化组件
interface PriceChangeProps {
    value: number | null | undefined;
}

export const PriceChange: React.FC<PriceChangeProps> = ({ value }) => {
    if (value === null || value === undefined) {
        return <span className="cell-empty">-</span>;
    }

    const isPositive = value >= 0;
    const className = isPositive ? 'cell-up' : 'cell-down';
    const sign = isPositive ? '+' : '';

    return (
        <span className={`highlight-cell ${className}`}>
            {sign}{value.toFixed(2)}%
        </span>
    );
};

// 交易次数组件
interface TxnsDisplayProps {
    buys: number;
    sells: number;
    buysDelta?: 'up' | 'down' | 'same';
}

export const TxnsDisplay: React.FC<TxnsDisplayProps> = ({
    buys,
    sells,
    buysDelta = 'same'
}) => {
    const buysClass = buysDelta === 'up'
        ? 'cell-up'
        : buysDelta === 'down'
            ? 'cell-down'
            : '';

    return (
        <span className="txns-display">
            <span className={buysClass}>{buys}</span>
            <span className="txns-separator">/</span>
            <span>{sells}</span>
        </span>
    );
};

export default HighlightCell;
