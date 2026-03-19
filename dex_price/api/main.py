"""
DEX Price Dashboard - FastAPI 应用入口
提供 REST API 和 WebSocket 实时推送
"""

import logging
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.routes import strategies, tokens, signals, trades, dashboard, history

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("🚀 DEX Price Dashboard API 启动中...")
    yield
    logger.info("👋 DEX Price Dashboard API 已关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title="DEX Price Dashboard API",
    description="DEX 价格监控数据看板 API",
    version="3.0.0",
    lifespan=lifespan
)

# 配置 CORS - 允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发环境允许所有源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(strategies.router, prefix="/api/strategies", tags=["策略"])
app.include_router(tokens.router, prefix="/api/tokens", tags=["代币"])
app.include_router(signals.router, prefix="/api/signals", tags=["信号"])
app.include_router(trades.router, prefix="/api/trades", tags=["交易"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["看板"])
app.include_router(history.router, prefix="/api/history", tags=["历史数据"])


@app.get("/")
async def root():
    """根路由 - API 信息"""
    return {
        "name": "DEX Price Dashboard API",
        "version": "3.0.0",
        "endpoints": {
            "strategies": "/api/strategies",
            "tokens": "/api/tokens",
            "signals": "/api/signals",
            "trades": "/api/trades",
            "dashboard": "/api/dashboard",
            "history": "/api/history"
        }
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
