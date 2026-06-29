from __future__ import annotations

from fastapi import Request

from cloud.app.services.runtime import CloudRuntime


def get_runtime(request: Request) -> CloudRuntime:
    return request.app.state.runtime
