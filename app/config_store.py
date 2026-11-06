import json

from .models import SyslogConfig, syslog_config_from_file_dict
from .settings import settings


def load_config() -> SyslogConfig:
    path = settings.config_path
    if not path.exists():
        return SyslogConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return SyslogConfig()
        return syslog_config_from_file_dict(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return SyslogConfig()


def save_config(config: SyslogConfig) -> None:
    path = settings.config_path
    path.write_text(
        json.dumps(config.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
