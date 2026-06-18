import yaml
import os
from pathlib import Path


class Config:
    def __init__(self, path: str = "config.yaml"):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.server_host: str = data["server"]["host"]
        self.server_port: int = data["server"]["port"]
        self.database_path: str = data["database"]["path"]
        self.default_admin_username: str = data["auth"]["default_admin_username"]
        self.default_admin_password: str = data["auth"]["default_admin_password"]
        self.session_secret_key: str = data["auth"]["session_secret_key"]
        self.local_culture_export_template: str = data["source"]["local_culture_export_template"]
        self.export_output_dir: str = data["export"]["output_dir"]
        self.default_price_field: str = data["export"]["default_price_field"]
        self.default_subtotal_mode: str = data["export"]["default_subtotal_mode"]
        self.default_project_name: str = data["default_project"]["name"]
        self.default_project_type: str = data["default_project"]["project_type"]


_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config
