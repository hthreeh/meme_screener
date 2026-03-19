// Socket.io 服务
import { io, Socket } from 'socket.io-client';
import { useAppStore } from '../stores/appStore';
import type { PushData, TrackingSession } from '../stores/appStore';

// 动态获取Socket地址，支持局域网访问
const SOCKET_URL = import.meta.env.VITE_SOCKET_URL || `http://${window.location.hostname}:3001`;

let socket: Socket | null = null;

export function initSocket(): Socket {
    if (socket) return socket;

    socket = io(SOCKET_URL, {
        reconnection: true,
        reconnectionAttempts: Infinity,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
        randomizationFactor: 0.5,
        timeout: 10000,
    });

    const store = useAppStore.getState();

    // 连接事件
    socket.on('connect', () => {
        console.log('🔌 WebSocket 已连接');
        store.setConnected(true);
    });

    socket.on('disconnect', (reason) => {
        console.log('🔌 WebSocket 断开:', reason);
        store.setConnected(false);
    });

    socket.on('connect_error', (error) => {
        console.error('❌ WebSocket 连接错误:', error);
        store.setConnected(false);
    });

    // 数据事件
    socket.on('sessions', (sessions: TrackingSession[]) => {
        console.log('📡 收到会话列表:', sessions.length);
        store.setSessions(sessions);
    });

    socket.on('tokenUpdate', (data: PushData) => {
        // console.log('📡 收到数据更新:', data.tokenSymbol, data.current.priceUsd);
        store.updateLatestData(data);
        store.addDataLog(data);
    });

    return socket;
}

export function getSocket(): Socket | null {
    return socket;
}

export function disconnectSocket(): void {
    if (socket) {
        socket.disconnect();
        socket = null;
    }
}

export function subscribeToSession(sessionId: string): void {
    if (socket) {
        socket.emit('subscribe', sessionId);
    }
}

export function unsubscribeFromSession(sessionId: string): void {
    if (socket) {
        socket.emit('unsubscribe', sessionId);
    }
}
