"""StudyPilot app. Run: uvicorn server:app --reload"""
import contextlib
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from chat import router as chat_router
from server_mcp import mcp


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="StudyPilot", lifespan=lifespan)
app.mount("/mcp", mcp.streamable_http_app())
app.include_router(chat_router)


@app.get("/")
def simulator():
    return FileResponse(Path(__file__).parent / "static" / "index.html")
