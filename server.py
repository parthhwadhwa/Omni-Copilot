"""FastAPI layer over the orchestrator v3."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from orchestrator import Orchestrator

app = FastAPI(title="Omni Copilot API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

orch = Orchestrator()


class ChatRequest(BaseModel):
    message: str
    auto_mode: bool = False


@app.post("/chat")
def chat(req: ChatRequest):
    orch.set_auto_mode(req.auto_mode)
    response = orch.process(req.message)
    return response


@app.get("/tools")
def tools():
    return orch.get_all_tools()


@app.get("/memory")
def memory(query: str = "", limit: int = 10):
    return {"memory": orch.get_memory(query, limit)}


@app.post("/auto-mode")
def toggle_auto_mode(enabled: bool = True):
    orch.set_auto_mode(enabled)
    return {"auto_mode": orch.auto_mode}
