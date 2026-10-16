from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..realtime import manager
from ..security import decode_token

router = APIRouter()


@router.websocket("/ws")
async def websocket(ws: WebSocket, token: str):
    try:
        user_id = decode_token(token)
    except Exception:
        await ws.close(code=4401)
        return
    await manager.connect(user_id, ws)
    try:
        while True:
            await ws.receive_text()  # client pings keep the connection alive
    except WebSocketDisconnect:
        manager.disconnect(user_id, ws)
