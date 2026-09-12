from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.tasks.broadcaster import event_broadcaster

router = APIRouter(prefix="/events", tags=["Events"])


@router.get("/stream")
async def events_stream(request: Request):
    """Server-Sent Events (SSE) stream endpoint for real-time task and system events"""
    client_queue = event_broadcaster.subscribe()
    return StreamingResponse(
        event_broadcaster.event_generator(client_queue, request=request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
