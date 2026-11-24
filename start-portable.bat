@echo off
chcp 65001 >nul
echo 圖書採購系統啟動中...
cd /d %~dp0
python\python.exe setup_first_run.py
if %errorlevel% neq 0 (
    echo [錯誤] 設定未完成，請重新執行。
    pause
    exit /b 1
)
echo 啟動伺服器，請稍候...
python\python.exe run_server.py
pause
