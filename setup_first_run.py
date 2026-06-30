"""
首次啟動設定：自動建立 config.yaml。
由 start.bat 呼叫，不需要使用者手動執行。
"""
import pathlib
import secrets
import shutil
import sys

CONFIG_PATH = pathlib.Path("config.yaml")
EXAMPLE_PATH = pathlib.Path("config.example.yaml")


def needs_setup():
    if not CONFIG_PATH.exists():
        return True
    content = CONFIG_PATH.read_text(encoding="utf-8")
    return "<change-me>" in content or "<generate-a-random-secret>" in content


def run_setup():
    print()
    print("=" * 50)
    print("  首次啟動設定")
    print("=" * 50)
    print()

    if not EXAMPLE_PATH.exists():
        print("[錯誤] 找不到 config.example.yaml，請確認專案資料夾完整。")
        return False

    while True:
        password = input("  請設定管理員登入密碼（至少 6 個字元）：").strip()
        if len(password) >= 6:
            break
        print("  密碼太短，請重新輸入。")

    secret_key = secrets.token_hex(32)

    shutil.copy(EXAMPLE_PATH, CONFIG_PATH)
    content = CONFIG_PATH.read_text(encoding="utf-8")
    content = content.replace("<change-me>", password)
    content = content.replace("<generate-a-random-secret>", secret_key)
    CONFIG_PATH.write_text(content, encoding="utf-8")

    print()
    print("  設定完成！")
    print(f"  登入帳號：admin")
    print("  登入密碼：您剛才設定的密碼")
    print()
    print("  請記住您的密碼，日後登入時需要使用。")
    print("=" * 50)
    print()
    return True


def main():
    if needs_setup():
        success = run_setup()
        if not success:
            sys.exit(1)


if __name__ == "__main__":
    main()
