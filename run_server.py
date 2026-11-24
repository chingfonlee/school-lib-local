"""
統一啟動入口：讀取 config.yaml、偵測 Port 衝突、待 /api/health 就緒後自動開啟瀏覽器。
由 start.bat 與 start-portable.bat 呼叫。
"""

import json
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

import uvicorn

from app.config import get_config


def build_browser_url(host: str, port: int) -> str:
    browser_host = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    return f"http://{browser_host}:{port}"


def check_health(url: str, timeout: float = 1.0) -> bool:
    health_url = f"{url.rstrip('/')}/api/health"
    try:
        with urllib.request.urlopen(health_url, timeout=timeout) as resp:
            if resp.status != 200:
                return False
            data = json.loads(resp.read().decode("utf-8"))
            return isinstance(data, dict) and data.get("status") == "ok"
    except Exception:
        return False


def is_port_in_use(host: str, port: int, timeout: float = 0.5) -> bool:
    probe_host = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    try:
        with socket.create_connection((probe_host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_and_open_browser(url: str, max_wait_seconds: float = 60.0, poll_interval: float = 0.5) -> bool:
    deadline = time.monotonic() + max_wait_seconds
    while time.monotonic() < deadline:
        if check_health(url, timeout=1.0):
            webbrowser.open(url)
            return True
        time.sleep(poll_interval)
    return False


def main() -> int:
    try:
        cfg = get_config()
    except RuntimeError as exc:
        print(f"[錯誤] {exc}")
        return 1

    host = cfg.server_host
    port = cfg.server_port
    url = build_browser_url(host, port)

    if is_port_in_use(host, port):
        if check_health(url):
            print(f"系統已在執行中（{url}），已為您開啟瀏覽器。")
            webbrowser.open(url)
            return 0
        print(f"[錯誤] Port {port} 已被其他程式佔用，無法啟動圖書採購系統。")
        print("請依下列步驟處理：")
        print(f"  1. 關閉佔用 Port {port} 的程式，或")
        print("  2. 以記事本開啟 config.yaml，修改 server.port 為其他未使用的數字（例如 8766），存檔後重新啟動。")
        return 1

    watcher = threading.Thread(target=wait_and_open_browser, args=(url,), daemon=True)
    watcher.start()

    uvicorn.run("app.main:app", host=host, port=port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
