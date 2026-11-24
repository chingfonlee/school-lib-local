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
    echo 請至 https://www.python.org/downloads/ 下載，安裝時請勾選「Add Python to PATH」。
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('%PYTHON_CMD% --version 2^>^&1') do set "PYTHON_VERSION=%%v"
echo 使用 Python %PYTHON_VERSION%
echo %PYTHON_VERSION% | findstr /b "3.14" >nul
if %errorlevel% equ 0 (
    echo [錯誤] 偵測到 Python 3.14 預覽版，目前尚不相容。
    echo 請安裝 Python 3.12 或 3.11 後再執行。
    pause
    exit /b 1
)

if not exist .venv\ (
    echo 首次啟動：正在建立虛擬環境，請稍候...
    %PYTHON_CMD% -m venv .venv
    if %errorlevel% neq 0 (
        echo [錯誤] 虛擬環境建立失敗。
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat

set "NEED_INSTALL=0"
set "REQ_HASH="
set "SAVED_HASH="
for /f "delims=" %%h in ('python -c "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest())"') do set "REQ_HASH=%%h"
if exist .venv\.req_hash (
    set /p SAVED_HASH=<.venv\.req_hash
)
if not "%REQ_HASH%"=="%SAVED_HASH%" set "NEED_INSTALL=1"
python -c "import uvicorn" >nul 2>&1
if %errorlevel% neq 0 set "NEED_INSTALL=1"

if "%NEED_INSTALL%"=="1" (
    echo 安裝或更新依賴套件，請稍候...
    pip install -r requirements.txt --quiet
    if %errorlevel% neq 0 (
        echo [錯誤] 依賴套件安裝失敗，請檢查網路連線或 requirements.txt。
        pause
        exit /b 1
    )
    python -c "import pathlib; pathlib.Path('.venv/.req_hash').write_text('%REQ_HASH%', encoding='utf-8')"
)

python setup_first_run.py
if %errorlevel% neq 0 (
    echo [錯誤] 設定未完成，請重新執行。
    pause
    exit /b 1
)

echo 啟動伺服器，請稍候...
python run_server.py
if %errorlevel% neq 0 (
    pause
    exit /b 1
)

pause
