from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cloud.app.api.routes import agents, alerts, robots, system, tasks, ui
from cloud.app.core.config import Settings
from cloud.app.services.runtime import CloudRuntime

settings = Settings.from_env()
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Bumi cloud-side control service. Includes REST APIs, WebSocket agent "
        "endpoint, Swagger docs, and a local task panel for debugging."
    ),
    openapi_tags=[
        {"name": "system", "description": "Service status and entry routes."},
        {"name": "robots", "description": "Robot tasking and state APIs."},
        {"name": "tasks", "description": "Task query APIs."},
        {"name": "alerts", "description": "Alert query APIs."},
        {"name": "ui", "description": "Local debug panel."},
    ],
)
app.state.runtime = CloudRuntime()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router)
app.include_router(ui.router)
app.include_router(robots.router)
app.include_router(tasks.router)
app.include_router(alerts.router)
app.include_router(agents.router)
