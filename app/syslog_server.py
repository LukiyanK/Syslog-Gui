from __future__ import annotations

import asyncio
import json
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque, List, Optional, Set

from starlette.websockets import WebSocket

from .models import ListenProtocol, SyslogConfig, resolve_messages_file_path
from .settings import settings


@dataclass
class LogEntry:
    received_at: str
    remote: str
    protocol: ListenProtocol
    message: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_log_line(entry: LogEntry) -> str:
    return (
        f"{entry.received_at}\t{entry.protocol.upper()}\t{entry.remote}\t{entry.message}\n"
    )


def format_entries_as_text(entries: List[LogEntry]) -> str:
    return "".join(_format_log_line(e) for e in entries)


def _append_line_to_file(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line)


@dataclass
class SyslogReceiver:
    max_messages: int = 2000
    _messages: Deque[LogEntry] = field(default_factory=deque)
    _udp_transport: Optional[asyncio.DatagramTransport] = None
    _tcp_server: Optional[asyncio.AbstractServer] = None
    _listen_host: str = "0.0.0.0"
    _config: SyslogConfig = field(default_factory=SyslogConfig)
    _websockets: Set[WebSocket] = field(default_factory=set)

    def __post_init__(self) -> None:
        self._lock = asyncio.Lock()

    def set_config(self, config: SyslogConfig) -> None:
        self._config = config

    @property
    def messages(self) -> List[LogEntry]:
        return list(self._messages)

    async def snapshot_messages(self) -> List[LogEntry]:
        async with self._lock:
            return list(self._messages)

    async def clear_messages(self) -> None:
        async with self._lock:
            self._messages.clear()
        await self._broadcast_json({"type": "cleared"})

    async def _broadcast_json(self, payload: dict) -> None:
        text = json.dumps(payload, ensure_ascii=False)
        dead: List[WebSocket] = []
        for ws in self._websockets:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._websockets.discard(ws)

    async def add_websocket(self, ws: WebSocket) -> None:
        self._websockets.add(ws)
        hist = [e.__dict__ for e in self.messages[-500:]]
        try:
            await ws.send_text(
                json.dumps({"type": "history", "entries": hist}, ensure_ascii=False)
            )
        except Exception:
            self._websockets.discard(ws)

    def remove_websocket(self, ws: WebSocket) -> None:
        self._websockets.discard(ws)

    async def append(
        self, remote: str, protocol: ListenProtocol, raw: bytes
    ) -> None:
        text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        entry = LogEntry(
            received_at=_utc_now_iso(),
            remote=remote,
            protocol=protocol,
            message=text,
        )
        async with self._lock:
            self._messages.append(entry)
            while len(self._messages) > self.max_messages:
                self._messages.popleft()
        cfg = self._config
        if cfg.persist_to_file:
            path = resolve_messages_file_path(
                settings.data_dir, cfg.messages_file_path, cfg.persist_format
            )
            if cfg.persist_format == "json":
                line = json.dumps(entry.__dict__, ensure_ascii=False) + "\n"
            else:
                line = _format_log_line(entry)

            def _write() -> None:
                _append_line_to_file(path, line)

            try:
                await asyncio.to_thread(_write)
            except OSError:
                pass

        await self._broadcast_json({"type": "message", "entry": entry.__dict__})

    async def start(self, config: SyslogConfig) -> None:
        self._config = config
        await self.stop()
        if config.listen_protocol == "udp":
            await self._start_udp(config.listen_port)
        else:
            await self._start_tcp(config.listen_port)

    async def stop(self) -> None:
        if self._udp_transport is not None:
            self._udp_transport.close()
            self._udp_transport = None
        if self._tcp_server is not None:
            self._tcp_server.close()
            await self._tcp_server.wait_closed()
            self._tcp_server = None

    async def _start_udp(self, port: int) -> None:
        loop = asyncio.get_running_loop()
        receiver = self

        class Proto(asyncio.DatagramProtocol):
            def datagram_received(self, data: bytes, addr) -> None:  # type: ignore[no-untyped-def]
                remote = f"{addr[0]}:{addr[1]}"
                asyncio.create_task(receiver.append(remote, "udp", data))

            def error_received(self, exc: Exception) -> None:
                pass

        self._udp_transport, _ = await loop.create_datagram_endpoint(
            Proto,
            local_addr=(self._listen_host, port),
        )

    async def _start_tcp(self, port: int) -> None:
        receiver = self

        async def handle(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            peer = writer.get_extra_info("peername")
            remote = f"{peer[0]}:{peer[1]}" if peer else "unknown"
            try:
                while True:
                    line = await reader.readline()
                    if not line:
                        break
                    await receiver.append(remote, "tcp", line)
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

        self._tcp_server = await asyncio.start_server(
            handle,
            host=self._listen_host,
            port=port,
        )
