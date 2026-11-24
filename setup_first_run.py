"""
首次啟動設定：自動建立 config.yaml。
由 start.bat 呼叫，不需要使用者手動執行。
"""

import json
import pathlib
import re
import secrets
import shutil
import sys

import yaml

BASE_DIR = pathlib.Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.yaml"
EXAMPLE_PATH = BASE_DIR / "config.example.yaml"

PASSWORD_PLACEHOLDER = "<change-me>"
SECRET_PLACEHOLDER = "<generate-a-random-secret>"


def _load_auth_section(config_path: pathlib.Path) -> dict | None:
    if not config_path.exists():
        return None
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    auth = data.get("auth")
    return auth if isinstance(auth, dict) else None


def needs_setup(config_path: pathlib.Path | None = None) -> bool:
    path = config_path or CONFIG_PATH
    auth = _load_auth_section(path)
    if auth is None:
        return True
    password = auth.get("default_admin_password")
    secret = auth.get("session_secret_key")
    if not isinstance(password, str) or not password.strip() or password == PASSWORD_PLACEHOLDER:
        return True
    if not isinstance(secret, str) or not secret.strip() or secret == SECRET_PLACEHOLDER:
        return True
    return False


def _replace_yaml_scalar(content: str, key: str, value: str) -> str:
    escaped = json.dumps(value, ensure_ascii=False)
    pattern = rf"^([ \t]*{re.escape(key)}:[ \t]*).*$"
    updated, count = re.subn(pattern, lambda m: f"{m.group(1)}{escaped}", content, count=1, flags=re.MULTILINE)
    if count == 0:
        raise ValueError(f"設定檔中找不到欄位 {key}")
    return updated


def apply_setup_values(
    config_path: pathlib.Path,
    password: str | None = None,
    secret_key: str | None = None,
    example_path: pathlib.Path | None = None,
) -> None:
    src_example = example_path or EXAMPLE_PATH
    if not config_path.exists():
        if not src_example.exists():
            raise FileNotFoundError(f"找不到範本設定檔：{src_example}")
        shutil.copy(src_example, config_path)

    content = config_path.read_text(encoding="utf-8")
    if password is not None:
        content = _replace_yaml_scalar(content, "default_admin_password", password)
    if secret_key is not None:
        content = _replace_yaml_scalar(content, "session_secret_key", secret_key)
    config_path.write_text(content, encoding="utf-8")


def run_setup() -> bool:
    print()
    print("=" * 50)
    print("  首次啟動設定")
    print("=" * 50)
    print()

    if not CONFIG_PATH.exists() and not EXAMPLE_PATH.exists():
        print("[錯誤] 找不到 config.example.yaml，請確認專案資料夾完整。")
        return False

    auth = _load_auth_section(CONFIG_PATH) or {}
    cur_password = auth.get("default_admin_password")
    cur_secret = auth.get("session_secret_key")

    password: str | None = None
    if not isinstance(cur_password, str) or not cur_password.strip() or cur_password == PASSWORD_PLACEHOLDER:
        while True:
            entered = input("  請設定管理員登入密碼（至少 6 個字元）：").strip()
            if len(entered) >= 6:
                password = entered
                break
            print("  密碼太短，請重新輸入。")

    secret_key: str | None = None
    if not isinstance(cur_secret, str) or not cur_secret.strip() or cur_secret == SECRET_PLACEHOLDER:
        secret_key = secrets.token_hex(32)

    apply_setup_values(CONFIG_PATH, password=password, secret_key=secret_key, example_path=EXAMPLE_PATH)

    print()
    print("  設定完成！")
    print("  登入帳號：admin")
    if password is not None:
        print("  登入密碼：您剛才設定的密碼")
    print()
    print("  請記住您的密碼，日後登入時需要使用。")
    print("=" * 50)
    print()
    return True


def main() -> None:
    if needs_setup():
        success = run_setup()
        if not success:
            sys.exit(1)


if __name__ == "__main__":
    main()
