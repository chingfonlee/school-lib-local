@echo off
chcp 65001 >nul
echo 圖書採購系統啟動中...
cd /d %~dp0

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [錯誤] 找不到 Python，請先安裝 Python 3.10 或以上版本。
    pause
    exit /b 1
)

if not exist .venv\ (
    echo 首次啟動：正在建立虛擬環境...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [錯誤] 虛擬環境建立失敗。
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat
echo 安裝或更新依賴套件...
pip install -r requirements.txt --quiet

echo.
echo [提醒] 請確認已修改 config.yaml 中的 session_secret_key 為隨機字串。
echo.

echo 啟動伺服器，請稍候...
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8765
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765

pause
