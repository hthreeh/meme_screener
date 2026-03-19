@echo off
chcp 65001 >nul
setlocal

:: ==========================================
:: LAN Code Deploy Script (Dev PC -> Run PC)
:: Updated: 2026-01-22
:: ==========================================

:: 1. Source path
set SOURCE=E:\project_claude_0103

:: 2. Remote destination path
set DEST=\\LAPTOP-TO9U606I\python程序\project\DEX\project_claude_0118\project_claude_0103

:: 3. Log file (临时日志)
set LOGFILE=%TEMP%\deploy_log_%DATE:~0,4%%DATE:~5,2%%DATE:~8,2%_%TIME:~0,2%%TIME:~3,2%.txt

echo ========================================================
echo [Deploy] DEX Price Monitor - Code Sync
echo ========================================================
echo Source: %SOURCE%
echo Dest:   %DEST%
echo Time:   %DATE% %TIME%
echo ========================================================
echo.

:: Check if destination exists
if not exist "%DEST%" (
    echo [ERROR] Cannot connect to: %DEST%
    echo.
    echo Please check:
    echo   1. Remote PC is online
    echo   2. Folder is shared
    echo   3. Path is correct
    pause
    exit /b 1
)

echo [INFO] Starting file sync...
echo.

:: Robocopy sync with verbose output
:: /E   : Copy subdirectories including empty ones
:: /XO  : Exclude older files (only copy newer)
:: /FFT : Allow 2-second timestamp difference
:: /XD  : Exclude directories
:: /XF  : Exclude files
:: /V   : Verbose output (show files copied)
:: /NP  : No progress (cleaner output)
:: /TEE : Output to console AND log file
robocopy "%SOURCE%" "%DEST%" /E /XO /FFT /V /NP /TEE /LOG+:"%LOGFILE%" ^
    /XD .git .idea __pycache__ data logs venv .venv .gemini node_modules dist ^
    /XF *.log *.db .env deploy_to_remote.bat user_config.json *.pyc ^
    /R:3 /W:3

set ROBOCOPY_EXIT=%ERRORLEVEL%

echo.
echo ========================================================
echo [Summary]
echo ========================================================

:: Parse robocopy exit code
if %ROBOCOPY_EXIT% EQU 0 (
    echo Status: No changes - all files are up to date
) else if %ROBOCOPY_EXIT% EQU 1 (
    echo Status: SUCCESS - Files copied successfully
) else if %ROBOCOPY_EXIT% EQU 2 (
    echo Status: Extra files/dirs in destination (not an error)
) else if %ROBOCOPY_EXIT% EQU 3 (
    echo Status: SUCCESS - Some files copied, extra files in dest
) else if %ROBOCOPY_EXIT% LEQ 7 (
    echo Status: SUCCESS - Files synced with minor differences
) else (
    echo Status: ERROR - Deployment failed (code: %ROBOCOPY_EXIT%)
)

echo.
echo Log saved to: %LOGFILE%
echo.

:: Show what was copied (从日志提取)
echo [Files Updated]
echo --------------------------------------------------------
findstr /C:"New File" "%LOGFILE%" 2>nul
findstr /C:"Newer" "%LOGFILE%" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo (No files were updated)
)
echo --------------------------------------------------------

echo.
echo [Excluded Directories]
echo   .git, .idea, __pycache__, data, logs, venv, .venv
echo   .gemini, node_modules, dist
echo.
echo [Excluded Files]
echo   *.log, *.db, .env, deploy_to_remote.bat, user_config.json, *.pyc
echo.
echo ========================================================
if %ROBOCOPY_EXIT% LEQ 7 (
    echo [DONE] Deployment complete!
    echo.
    echo Next steps on remote machine:
    echo   1. cd to project directory
    echo   2. Run: pip install -r requirements.txt (if deps changed)
    echo   3. Run: cd web ^&^& npm install (if web deps changed)
    echo   4. Restart the services
) else (
    echo [FAIL] Deployment encountered errors. Check log for details.
)
echo ========================================================
pause
