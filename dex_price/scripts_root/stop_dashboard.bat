@echo off
chcp 65001 >nul
echo 停止 DEX Dashboard 服务...

REM 关闭 Python API 进程
taskkill /FI "WINDOWTITLE eq DEX API Server*" /F >nul 2>&1

REM 关闭前端进程  
taskkill /FI "WINDOWTITLE eq DEX Frontend*" /F >nul 2>&1

REM 关闭可能的 node 和 uvicorn 进程
tasklist /FI "IMAGENAME eq uvicorn.exe" 2>NUL | find /I /N "uvicorn.exe">NUL
if "%ERRORLEVEL%"=="0" taskkill /F /IM uvicorn.exe >nul 2>&1

echo 服务已停止。
pause
