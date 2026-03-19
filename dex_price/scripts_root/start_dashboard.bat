@echo off
chcp 65001 >nul
echo ====================================
echo   DEX Price Dashboard v3.0
echo ====================================
echo.

REM 启动 Python API 服务
echo [1/2] 启动 API 服务 (端口 8000)...
start "DEX API Server" cmd /c "cd /d %~dp0.. && python -m api.main"

REM 等待 API 启动
timeout /t 3 /nobreak >nul

REM 启动前端开发服务器
echo [2/2] 启动前端服务 (端口 5173)...
start "DEX Frontend" cmd /c "cd /d %~dp0..\web && npm run dev"

echo.
echo ====================================
echo   服务已启动！
echo   API:      http://localhost:8000
echo   Frontend: http://localhost:5173
echo ====================================
echo.
echo 按任意键打开浏览器...
pause >nul

start http://localhost:5173
