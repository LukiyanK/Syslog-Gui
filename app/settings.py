import os
from pathlib import Path


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class Settings:
    web_host: str = os.environ.get("WEB_HOST") or "0.0.0.0"
    web_port: int = _int_env("WEB_PORT", 8080)
    data_dir: Path = Path(os.environ.get("DATA_DIR") or "./data")
    config_file: str = os.environ.get("CONFIG_FILE") or "config.json"

    @property
    def config_path(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir / self.config_file


settings = Settings()
