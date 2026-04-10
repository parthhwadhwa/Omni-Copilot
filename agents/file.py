import os
from .base import BaseAgent


class FileAgent(BaseAgent):
    name = "file"
    description = "Read and write local code/text files and handle images"
    tools = [
        {
            "action": "read",
            "description": "Read a file's contents",
            "params": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        },
        {
            "action": "write",
            "description": "Write content to a file",
            "params": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
        {
            "action": "list_dir",
            "description": "List files in a directory",
            "params": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                },
            },
        },
    ]

    SANDBOX = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sandbox")

    def _safe_path(self, path: str) -> str:
        os.makedirs(self.SANDBOX, exist_ok=True)
        resolved = os.path.realpath(os.path.join(self.SANDBOX, path))
        if not resolved.startswith(os.path.realpath(self.SANDBOX)):
            raise ValueError("Path escapes sandbox")
        return resolved

    def action_read(self, path: str) -> dict:
        full = self._safe_path(path)
        if not os.path.exists(full):
            return {"error": "File not found", "path": path}
        with open(full) as f:
            content = f.read()
        return {"path": path, "content": content, "size": len(content)}

    def action_write(self, path: str, content: str) -> dict:
        full = self._safe_path(path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(content)
        return {"path": path, "status": "written", "size": len(content)}

    def action_list_dir(self, path: str = ".") -> list:
        full = self._safe_path(path)
        if not os.path.isdir(full):
            return []
        return sorted(os.listdir(full))
