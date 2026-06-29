from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from cloud.app.services.runtime import CloudRuntime
from shared.protocol import Envelope

router = APIRouter()


@router.websocket("/ws/agents/{robot_id}")
async def agent_websocket(
    websocket: WebSocket,
    robot_id: str,
) -> None:
    runtime: CloudRuntime = websocket.app.state.runtime
    await runtime.connect(robot_id, websocket)
    try:
        while True:
            message = await websocket.receive_json()
            envelope = Envelope.model_validate(message)
            await runtime.handle_agent_message(envelope)
    except WebSocketDisconnect:
        await runtime.disconnect(robot_id)
    except ValidationError as exc:
        await runtime.disconnect(robot_id)
        await websocket.close(code=1003, reason=str(exc))
