# DexScreener 元素定位文档

本文档整理了 DexScreener 页面中需要采集的所有 HTML 元素。

---

## 一、代币列表页面元素

### 1.1 表格行容器
```html
<a class="ds-dex-table-row ds-dex-table-row-top" href="/solana/...">
```
- **CSS选择器**: `.ds-dex-table-row`
- **说明**: 每个代币一行，href 属性包含代币路径

---

### 1.2 代币基础信息

| 字段 | CSS 类名 | 示例值 | 说明 |
|------|----------|--------|------|
| 代币名称 | `ds-dex-table-row-base-token-symbol` | `USDUC` | 代币符号 |
| 代币图标 | `ds-dex-table-row-token-icon-img` | - | src 属性包含 CA |

---

### 1.3 价格与涨跌幅

| 字段 | CSS 类名 | 示例值 | 说明 |
|------|----------|--------|------|
| 当前价格 | `ds-dex-table-row-col-price` | `$0.004549` | 代币价格 |
| 5分钟涨幅 | `ds-dex-table-row-col-price-change-m5` | `+15.2%` | 5分钟变化 |
| 1小时涨幅 | `ds-dex-table-row-col-price-change-h1` | `-2.3%` | 1小时变化 |
| 6小时涨幅 | `ds-dex-table-row-col-price-change-h6` | `+45.1%` | 6小时变化 |
| 24小时涨幅 | `ds-dex-table-row-col-price-change-h24` | `+120%` | 24小时变化 |

---

### 1.4 市场数据

| 字段 | CSS 类名 | 示例值 | 说明 |
|------|----------|--------|------|
| 市值 | `ds-dex-table-row-col-market-cap` | `$4.5M` | 市值 |
| 流动性 | `ds-dex-table-row-col-liquidity` | `$575K` | 流动池大小 |
| 交易量 | `ds-dex-table-row-col-volume` | `$1.2M` | 24小时交易量 |
| 交易次数 | `ds-dex-table-row-col-txns` | `1,644` | 24小时交易次数 |
| 钱包数 | `ds-dex-table-row-col-makers` | `305` | 24小时交易钱包数 |
| 交易对年龄 | `ds-dex-table-row-col-pair-age` | `7mo` | 交易对创建时间 |

---

## 二、代币详情页 CA 获取

从代币详情页获取合约地址 (CA)：

```html
<div class="chakra-stack custom-i33gp9">
  <span class="chakra-text custom-72rvq0" title="CB9dDufT3ZuQXqqSfa1c5kY935TEreyBw9XJXxHKpump">
    USDUC
  </span>
</div>
```

- **CSS选择器**: `.chakra-text.custom-72rvq0` 或 `span[title]`
- **说明**: `title` 属性值即为代币的 CA 地址

---

## 三、DexScreener API 数据

### 3.1 API 端点
```
GET https://api.dexscreener.com/token-pairs/v1/solana/{CA}
```

### 3.2 返回字段

| 字段路径 | 类型 | 说明 |
|----------|------|------|
| `[0].baseToken.address` | string | 代币 CA |
| `[0].baseToken.name` | string | 代币名称 |
| `[0].baseToken.symbol` | string | 代币符号 |
| `[0].priceUsd` | string | 美元价格 |
| `[0].priceNative` | string | SOL 价格 |
| `[0].txns.m5.buys` | int | 5分钟买入次数 |
| `[0].txns.m5.sells` | int | 5分钟卖出次数 |
| `[0].txns.h1.buys` | int | 1小时买入次数 |
| `[0].txns.h1.sells` | int | 1小时卖出次数 |
| `[0].txns.h24.buys` | int | 24小时买入次数 |
| `[0].txns.h24.sells` | int | 24小时卖出次数 |
| `[0].volume.h24` | float | 24小时交易量 |
| `[0].volume.h6` | float | 6小时交易量 |
| `[0].volume.h1` | float | 1小时交易量 |
| `[0].volume.m5` | float | 5分钟交易量 |
| `[0].priceChange.m5` | float | 5分钟涨跌幅% |
| `[0].priceChange.h1` | float | 1小时涨跌幅% |
| `[0].priceChange.h6` | float | 6小时涨跌幅% |
| `[0].priceChange.h24` | float | 24小时涨跌幅% |
| `[0].liquidity.usd` | float | 流动性(USD) |
| `[0].fdv` | int | 完全稀释估值 |
| `[0].marketCap` | int | 市值 |
| `[0].pairCreatedAt` | int | 交易对创建时间戳 |

---

## 四、URL 构建规则

| 场景 | URL 格式 |
|------|----------|
| 代币详情页 | `https://dexscreener.com{href}` |
| API 查询 | `https://api.dexscreener.com/token-pairs/v1/solana/{CA}` |

示例：
- href: `/solana/bax9m9a5fvy5cniewwnuwkvdzhsg9psznb4fj9r677tn`
- 完整 URL: `https://dexscreener.com/solana/bax9m9a5fvy5cniewwnuwkvdzhsg9psznb4fj9r677tn`