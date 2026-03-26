from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def mount_frontend(app: FastAPI, project_root: str) -> None:
    frontend_dist = os.path.join(project_root, "frontend", "dist")
    assets_dir = os.path.join(frontend_dist, "assets")

    if not os.path.exists(frontend_dist):
        return

    @app.get("/")
    async def root() -> FileResponse:
        return FileResponse(os.path.join(frontend_dist, "index.html"))

    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")
