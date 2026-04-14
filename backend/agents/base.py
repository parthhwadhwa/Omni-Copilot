from __future__ import annotations
import json
import os
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(ROOT_DIR, "data")
DOCS_DIR = os.path.join(ROOT_DIR, "docs")


def load_data(filename: str) -> list[dict]:
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def save_data(filename: str, data: list[dict]):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, filename), "w") as f:
        json.dump(data, f, indent=2, default=str)


class BaseAgent:
    """Base class every agent inherits from."""

    name: str = "base"
    description: str = ""
    tools: list[dict] = []

    def handle(self, action: str, params: dict) -> dict:
        method = getattr(self, f"action_{action}", None)
        if method is None:
            return {"ok": False, "error": f"Unknown action '{action}' for {self.name}"}
        try:
            return {"ok": True, "result": method(**params)}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def tool_definitions(self) -> list[dict]:
        return [
            {
                "name": f"{self.name}.{t['action']}",
                "description": t["description"],
                "input_schema": t["params"],
            }
            for t in self.tools
        ]
