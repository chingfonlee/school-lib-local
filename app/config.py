from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent


def _resolve_path(raw: str) -> str:
    if not raw or raw == ":memory:":
        return raw
    p = Path(raw)
    if p.is_absolute():
        return raw
    return str((BASE_DIR / p).resolve())


class Config:
    def __init__(self, path: str | Path | None = None):
        config_path = Path(path) if path is not None else BASE_DIR / "config.yaml"
        try:
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"找不到設定檔 {config_path}，請先執行 setup_first_run.py 或從 config.example.yaml 複製設定檔。"
            ) from exc
        except yaml.YAMLError as exc:
            raise RuntimeError(
                f"設定檔 {config_path} 的 YAML 格式錯誤，請檢查縮排或引號（特別是密碼中的特殊字元）：{exc}"
            ) from exc

        if not isinstance(data, dict):
            raise RuntimeError(f"設定檔 {config_path} 內容為空或格式不正確，請參考 config.example.yaml。")

        try:
            self.server_host: str = data["server"]["host"]
            self.server_port: int = int(data["server"]["port"])
            self.database_path: str = _resolve_path(data["database"]["path"])
            self.default_admin_username: str = data["auth"]["default_admin_username"]
            self.default_admin_password: str = data["auth"]["default_admin_password"]
            self.session_secret_key: str = data["auth"]["session_secret_key"]
            self.local_culture_export_template: str = _resolve_path(data["source"]["local_culture_export_template"])
            self.export_output_dir: str = _resolve_path(data["export"]["output_dir"])
            self.default_price_field: str = data["export"]["default_price_field"]
            self.default_subtotal_mode: str = data["export"]["default_subtotal_mode"]
            self.default_project_name: str = data["default_project"]["name"]
            self.default_project_type: str = data["default_project"]["project_type"]
            self.default_project_export_template_name: str = data.get("default_project", {}).get(
                "export_template_name", ""
            )
            self.export_templates: list[dict] = data.get("export_templates", [])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"設定檔 {config_path} 缺少必要欄位或型別錯誤（{exc}），請對照 config.example.yaml 補齊。"
            ) from exc


_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config
