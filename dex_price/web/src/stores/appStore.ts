// Zustand 状态管理
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

// Token 数据类型
export interface TokenData {
    chainId: string;
    pairAddress: string;
    baseTokenAddress: string;
    baseTokenName: string;
    baseTokenSymbol: string;
    quoteTokenSymbol: string;
    priceUsd: number;
    priceNative: number;
    marketCap: number | null;
    fdv: number | null;
    liquidityUsd: number;
    volume: {
        m5: number;
        h1: number;
        h6: number;
        h24: number;
    };
    txns: {
        m5: { buys: number; sells: number };
        h1: { buys: number; sells: number };
        h6: { buys: number; sells: number };
        h24: { buys: number; sells: number };
    };
    priceChange: {
        m5: number;
        h1: number;
        h6: number;
        h24: number;
    };
}

// 追踪会话
export interface TrackingSession {
    id: string;
    chainId: string;
    tokenAddress: string;
    tokenName: string | null;
    tokenSymbol: string | null;
    frequencySeconds: number;
    status: 'running' | 'stopped' | 'paused';
    baseData: TokenData | null;
    createdAt: string;
    updatedAt: string;
}

// 推送数据
export interface PushData {
    sessionId: string;
    tokenSymbol: string;
    current: TokenData;
    baseline: TokenData;
    deltas: {
        priceUsd: 'up' | 'down' | 'same';
        marketCap: 'up' | 'down' | 'same';
        fdv: 'up' | 'down' | 'same';
        liquidityUsd: 'up' | 'down' | 'same';
        volumeM5: 'up' | 'down' | 'same';
        volumeH1: 'up' | 'down' | 'same';
        volumeH6: 'up' | 'down' | 'same';
        volumeH24: 'up' | 'down' | 'same';
        txnsM5Buys: 'up' | 'down' | 'same';
        txnsH1Buys: 'up' | 'down' | 'same';
    };
    timestamp: string;
}

// 系统状态
export interface SystemStatus {
    api: {
        available: number;
        used: number;
        limit: number;
        usagePercent: number;
    };
    activeTasks: number;
    database: {
        sizeBytes: number;
        sizeMB: string;
    };
    uptime: number;
}

// 应用状态
interface AppState {
    // 连接状态
    isConnected: boolean;
    setConnected: (connected: boolean) => void;

    // 会话列表
    sessions: TrackingSession[];
    setSessions: (sessions: TrackingSession[]) => void;
    addSession: (session: TrackingSession) => void;
    removeSession: (sessionId: string) => void;
    updateSession: (sessionId: string, updates: Partial<TrackingSession>) => void;

    // 实时数据
    latestData: Map<string, PushData>;
    updateLatestData: (data: PushData) => void;
    setLatestData: (data: Record<string, PushData>) => void;

    // 数据流日志
    dataLogs: PushData[];
    addDataLog: (data: PushData) => void;
    setDataLogs: (logs: PushData[]) => void;

    // 系统状态
    systemStatus: SystemStatus | null;
    setSystemStatus: (status: SystemStatus) => void;
}

export const useAppStore = create<AppState>()((set, get) => ({
    // 连接状态
    isConnected: false,
    setConnected: (connected) => set({ isConnected: connected }),

    // 会话列表
    sessions: [],
    setSessions: (sessions) => set({ sessions }),
    addSession: (session) => set((state) => ({
        sessions: [session, ...state.sessions]
    })),
    removeSession: (sessionId) => set((state) => ({
        sessions: state.sessions.filter(s => s.id !== sessionId)
    })),
    updateSession: (sessionId, updates) => set((state) => ({
        sessions: state.sessions.map(s =>
            s.id === sessionId ? { ...s, ...updates } : s
        )
    })),

    // 实时数据
    latestData: new Map(),
    updateLatestData: (data) => set((state) => {
        const newMap = new Map(state.latestData);
        newMap.set(data.sessionId, data);
        return { latestData: newMap };
    }),
    setLatestData: (data) => set(() => {
        const newMap = new Map(Object.entries(data));
        return { latestData: newMap };
    }),

    // 数据流日志 (新数据在数组前面)
    dataLogs: [],
    addDataLog: (data) => set((state) => {
        const newLogs = [data, ...state.dataLogs].slice(0, 500); // 保留最近 500 条
        return { dataLogs: newLogs };
    }),
    setDataLogs: (logs) => set(() => ({ dataLogs: logs.slice(0, 500) })),

    // 系统状态
    systemStatus: null,
    setSystemStatus: (status) => set({ systemStatus: status }),
}));

// 列显示状态 (持久化)
interface ColumnState {
    visibleColumns: string[];
    setVisibleColumns: (columns: string[]) => void;
    liveFeedVisibleColumns: string[];
    setLiveFeedVisibleColumns: (columns: string[]) => void;
}

export const useColumnStore = create<ColumnState>()(
    persist(
        (set) => ({
            visibleColumns: [
                'symbol', 'price', 'marketCap', 'volume_h1',
                'txns_h1', 'priceChange_h1', 'liquidity', 'actions'
            ],
            setVisibleColumns: (columns) => set({ visibleColumns: columns }),
            liveFeedVisibleColumns: [
                'timestamp', 'symbol', 'price', 'marketCap',
                'volume_h1', 'txns_h1', 'priceChange_h1'
            ],
            setLiveFeedVisibleColumns: (columns) => set({ liveFeedVisibleColumns: columns }),
        }),
        {
            name: 'meme-tracker-columns',
        }
    )
);
