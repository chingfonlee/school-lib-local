@echo off
chcp 65001 >nul
echo 圖書採購系統啟動中...
cd /d %~dp0

set "PYTHON_CMD="

py -V:Astral/CPython3.12.13 --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_CMD=py -V:Astral/CPython3.12.13"
) else (
    py -3.12 --version >nul 2>&1
    if %errorlevel% equ 0 (
        set "PYTHON_CMD=py -3.12"
    ) else (
        where python >nul 2>&1
        if %errorlevel% equ 0 (
            set "PYTHON_CMD=python"
        )
    )
)

if "%PYTHON_CMD%"=="" (
    echo [錯誤] 找不到 Python，請先安裝 Python 3.10 或以上版本。
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('%PYTHON_CMD% --version 2^>^&1') do set "PYTHON_VERSION=%%v"
echo 使用 Python %PYTHON_VERSION%
echo %PYTHON_VERSION% | findstr /b "3.14" >nul
if %errorlevel% equ 0 (
    echo [錯誤] 偵測到 Python 3.14 預覽版，目前 FastAPI/Pydantic 尚不相容。
    echo 請安裝 Python 3.12 或 3.11 後再執行。
    pause
    exit /b 1
)

if not exist .venv\ (
    echo 首次啟動：正在建立虛擬環境...
    %PYTHON_CMD% -m venv .venv
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
