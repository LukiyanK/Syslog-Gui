import uvicorn

from app.settings import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.web_host,
        port=settings.web_port,
    )
