from backend.core.config import get_settings
from backend.main import app


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run("backend.main:app", host=settings.host, port=settings.port, reload=True)
