from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Mapping

ListenProtocol = Literal["udp", "tcp"]


def resolve_messages_file_path(data_dir: Path, user_path: str) -> Path:
    """Путь к файлу логов: относительный — относительно DATA_DIR, иначе абсолютный."""
    stripped = user_path.strip()
    if not stripped:
        return (data_dir / "logs" / "syslog.log").resolve()
    p = Path(stripped)
    if p.is_absolute():
        return p.resolve()
    return (data_dir / stripped).resolve()


@dataclass
class SyslogConfig:
    # По умолчанию непривилегированный порт (порт <1024 обычно требует root).
    listen_port: int = 5514
    listen_protocol: ListenProtocol = "udp"
    # Запись входящих сообщений в файл (одна строка на сообщение).
    persist_to_file: bool = False
    # Путь к файлу на диске (или относительно DATA_DIR); пусто — data_dir/logs/syslog.log
    messages_file_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def syslog_config_from_mapping(m: Mapping[str, Any]) -> SyslogConfig:
    """Разбор и валидация тела POST /api/config."""
    if "listen_port" not in m or "listen_protocol" not in m:
        raise ValueError("Нужны поля listen_port и listen_protocol")
    try:
        port = int(m["listen_port"])
    except (TypeError, ValueError) as e:
        raise ValueError("listen_port должен быть целым числом") from e
    proto_raw = m["listen_protocol"]
    if proto_raw not in ("udp", "tcp"):
        raise ValueError('listen_protocol должен быть "udp" или "tcp"')
    listen_protocol: ListenProtocol = "udp" if proto_raw == "udp" else "tcp"
    if not (1 <= port <= 65535):
        raise ValueError("listen_port должен быть от 1 до 65535")

    persist_raw = m.get("persist_to_file", False)
    if isinstance(persist_raw, str):
        persist_to_file = persist_raw.lower() in ("1", "true", "yes", "on")
    else:
        persist_to_file = bool(persist_raw)

    path_raw = m.get("messages_file_path", "")
    if path_raw is None:
        messages_file_path = ""
    elif not isinstance(path_raw, str):
        raise ValueError("messages_file_path должен быть строкой")
    else:
        messages_file_path = path_raw

    return SyslogConfig(
        listen_port=port,
        listen_protocol=listen_protocol,
        persist_to_file=persist_to_file,
        messages_file_path=messages_file_path,
    )


def syslog_config_from_file_dict(m: Mapping[str, Any]) -> SyslogConfig:
    """Загрузка из config.json с значениями по умолчанию."""
    try:
        merged = {
            "listen_port": m.get("listen_port", 5514),
            "listen_protocol": m.get("listen_protocol", "udp"),
            "persist_to_file": m.get("persist_to_file", False),
            "messages_file_path": m.get("messages_file_path", "") or "",
        }
        return syslog_config_from_mapping(merged)
    except ValueError:
        return SyslogConfig()
