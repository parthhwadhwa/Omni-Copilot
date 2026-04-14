import os
from .base import BaseAgent

DEFAULT_DIR = os.path.expanduser("~")


class FileAgent(BaseAgent):
    name = "file"
    description = "Read and list files from the local filesystem"
    tools = [
        {
            "action": "read",
            "description": "Read a file's contents",
            "params": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute file path"},
                },
                "required": ["path"],
            },
        },
        {
            "action": "list_dir",
            "description": "List files in a directory",
            "params": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path", "default": "~"},
                },
            },
        },
        {
            "action": "status",
            "description": "Check file agent status",
            "params": {"type": "object", "properties": {}},
        },
    ]

    def action_status(self) -> dict:
        return {"connected": True, "method": "local filesystem", "root": DEFAULT_DIR}

    def action_read(self, path: str) -> dict:
        path = os.path.expanduser(path)
        if not os.path.exists(path):
            return {"error": "File not found", "path": path}
        if not os.path.isfile(path):
            return {"error": "Not a file", "path": path}
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return {"path": path, "content": content, "size": len(content)}
        except Exception as e:
            return {"error": str(e), "path": path}

    def action_list_dir(self, path: str = "~") -> list:
        path = os.path.expanduser(path)
        if not path or path in (".", "current directory", "current dir"):
            path = DEFAULT_DIR
        if not os.path.isdir(path):
            return [{"error": f"Directory not found: {path}"}]
        try:
            entries = []
            for name in sorted(os.listdir(path)):
                full = os.path.join(path, name)
                entries.append({
                    "name": name,
                    "path": full,
                    "type": "directory" if os.path.isdir(full) else "file",
                    "size": os.path.getsize(full) if os.path.isfile(full) else None,
                })
            return entries[:50]
        except Exception as e:
            return [{"error": str(e)}]
