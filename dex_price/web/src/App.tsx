// DEX Price Dashboard - 主应用入口
import { useEffect, useState } from 'react';
import {
  Layout,
  Tabs,
  ConfigProvider,
  theme,
  Card,
  Statistic,
  Space
} from 'antd';
import {
  DashboardOutlined,
  SwapOutlined,
  LineChartOutlined
} from '@ant-design/icons';
import { getDashboard } from './services/api';
import type { DashboardData } from './services/api';
import StrategyDashboard from './components/StrategyDashboard';
import PositionTable from './components/PositionTable';
import TradeHistory from './components/TradeHistory';
import HistoryData from './components/HistoryData';
import './App.css';

const { Header, Content } = Layout;

function App() {
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [historySearch, setHistorySearch] = useState<string>('');

  const handleTokenClick = (tokenName: string) => {
    setHistorySearch(tokenName);
    setActiveTab('history');
  };

  useEffect(() => {
    const fetchDashboard = async () => {
      try {
        const data = await getDashboard();
        setDashboard(data);
      } catch (error) {
        console.error('获取看板数据失败:', error);
      }
    };

    fetchDashboard();
    // 每30秒刷新
    const interval = setInterval(fetchDashboard, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <ConfigProvider
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: '#1890ff',
          borderRadius: 6,
        },
      }}
    >
      <Layout className="app-layout">
        <Header className="app-header">
          <div className="header-inner">
            <div className="header-left">
              <div className="logo">
                🚀 DEX Price Dashboard
              </div>
            </div>
            <div className="header-right">
              <Space size="large">
                <Statistic
                  title="总余额"
                  value={dashboard?.total_balance ?? 0}
                  precision={2}
                  suffix="SOL"
                  valueStyle={{ fontSize: 14, color: '#1f1f1f', fontWeight: 'bold' }}
                />
                <Statistic
                  title="总盈亏"
                  value={dashboard?.total_pnl ?? 0}
                  precision={2}
                  suffix="SOL"
                  valueStyle={{
                    fontSize: 14,
                    color: (dashboard?.total_pnl ?? 0) >= 0 ? '#52c41a' : '#ff4d4f',
                    fontWeight: 'bold'
                  }}
                />
                <Statistic
                  title="持仓数"
                  value={dashboard?.total_positions ?? 0}
                  valueStyle={{ fontSize: 14, color: '#1f1f1f', fontWeight: 'bold' }}
                />
              </Space>
            </div>
          </div>
        </Header>

        <Content className="app-content">
          <div className="main-container">
            <Card className="content-card" bordered={false}>
              <Tabs
                activeKey={activeTab}
                onChange={setActiveTab}
                items={[
                  {
                    key: 'overview',
                    label: (
                      <span>
                        <DashboardOutlined />
                        策略概览
                      </span>
                    ),
                    children: (
                      <div className="dashboard-container">
                        <StrategyDashboard />
                        <div style={{ height: 24 }} />
                        <PositionTable onTokenClick={handleTokenClick} />
                      </div>
                    ),
                  },
                  {
                    key: 'trades',
                    label: (
                      <span>
                        <SwapOutlined />
                        交易历史
                      </span>
                    ),
                    children: <TradeHistory onTokenClick={handleTokenClick} />,
                  },
                  {
                    key: 'history',
                    label: (
                      <span>
                        <LineChartOutlined />
                        历史数据
                      </span>
                    ),
                    children: <HistoryData initialSearchTerm={historySearch} />,
                  },
                ]}
              />
            </Card>
          </div>
        </Content>
      </Layout>
    </ConfigProvider>
  );
}

export default App;
