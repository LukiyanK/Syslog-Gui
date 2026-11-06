from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

from .config_store import load_config, save_config
from .models import syslog_config_from_mapping
from .settings import settings
from .syslog_server import SyslogReceiver, format_entries_as_text

receiver = SyslogReceiver()

static_dir = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: Starlette):
    config = load_config()
    await receiver.start(config)
    yield
    await receiver.stop()


async def index(_: Request):
    index_path = static_dir / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(str(index_path))


async def get_config(_: Request):
    return JSONResponse(load_config().to_dict())


async def post_config(request: Request):
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Некорректный JSON") from e
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400, detail="Тело запроса должно быть объектом JSON"
        )
    try:
        new_cfg = syslog_config_from_mapping(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    try:
        await receiver.start(new_cfg)
    except OSError as e:
        try:
            await receiver.start(load_config())
        except Exception:
            pass
        raise HTTPException(
            status_code=400,
            detail=(
                f"Не удалось запустить syslog на порту {new_cfg.listen_port}: {e}"
            ),
        ) from e
    save_config(new_cfg)
    return JSONResponse(new_cfg.to_dict())


async def logs_websocket(websocket: WebSocket):
    await websocket.accept()
    await receiver.add_websocket(websocket)
    try:
        while True:
            await websocket.receive()
    except WebSocketDisconnect:
        pass
    finally:
        receiver.remove_websocket(websocket)


async def list_messages(request: Request):
    raw_limit = request.query_params.get("limit", "200")
    try:
        limit = int(raw_limit)
    except ValueError:
        limit = 200
    if limit < 1:
        limit = 1
    if limit > 1000:
        limit = 1000
    items = receiver.messages[-limit:]
    return JSONResponse([e.__dict__ for e in items])


async def export_messages(request: Request):
    fmt = request.query_params.get("format", "txt").lower()
    items = await receiver.snapshot_messages()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if fmt == "json":
        body = json.dumps(
            [e.__dict__ for e in items], ensure_ascii=False, indent=2
        )
        return Response(
            content=body,
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="syslog-messages-{stamp}.json"'
                )
            },
        )
    body = format_entries_as_text(items)
    return Response(
        content=body,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="syslog-messages-{stamp}.txt"'
            )
        },
    )


async def clear_messages(_: Request):
    await receiver.clear_messages()
    return JSONResponse({"ok": True, "cleared": True})


async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


routes = [
    Mount("/static", StaticFiles(directory=str(static_dir)), name="static"),
    Route("/", index),
    Route("/api/config", get_config, methods=["GET"]),
    Route("/api/config", post_config, methods=["POST"]),
    Route("/api/messages", list_messages, methods=["GET"]),
    Route("/api/messages/export", export_messages, methods=["GET"]),
    Route("/api/messages/clear", clear_messages, methods=["POST"]),
    WebSocketRoute("/ws/logs", logs_websocket),
]

app = Starlette(
    routes=routes,
    lifespan=lifespan,
    exception_handlers={HTTPException: http_exception_handler},
)
