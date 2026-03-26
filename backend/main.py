from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes.health import router as health_router
from backend.api.routes.signaling import router as signaling_router
from backend.core.config import get_settings
from backend.web.static_files import mount_frontend


def create_app() -> FastAPI:
    app = FastAPI(title="Chat WebSocket API")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(signaling_router)

    project_root = os.path.dirname(os.path.dirname(__file__))
    mount_frontend(app, project_root)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run("backend.main:app", host=settings.host, port=settings.port, reload=True)
