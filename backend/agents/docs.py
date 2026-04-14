import os
import uuid
from .base import BaseAgent, load_data, save_data, DOCS_DIR


class DocsAgent(BaseAgent):
    name = "docs"
    description = "Create and read real files in /docs/, tracked in docs.json"
    tools = [
        {
            "action": "read_doc",
            "description": "Read a document by ID (from docs.json + file system)",
            "params": {
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string"},
                },
                "required": ["doc_id"],
            },
        },
        {
            "action": "write_doc",
            "description": "Create or update a document (writes real file to /docs/)",
            "params": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "doc_id": {"type": "string", "description": "Omit to create new"},
                },
                "required": ["title", "content"],
            },
        },
        {
            "action": "list_files",
            "description": "List documents from docs.json",
            "params": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
            },
        },
    ]

    def _slug(self, title: str) -> str:
        """Convert title to a safe filename."""
        slug = title.lower().strip()
        slug = "".join(c if c.isalnum() or c in (" ", "-", "_") else "" for c in slug)
        slug = slug.replace(" ", "_")
        return slug[:60] or "untitled"

    def _write_file(self, filename: str, content: str) -> str:
        """Write content to a real file in /docs/. Returns absolute path."""
        os.makedirs(DOCS_DIR, exist_ok=True)
        path = os.path.join(DOCS_DIR, filename)
        with open(path, "w") as f:
            f.write(content)
        return path

    def _read_file(self, filename: str) -> str | None:
        """Read content from a real file in /docs/."""
        path = os.path.join(DOCS_DIR, filename)
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return f.read()

    def action_read_doc(self, doc_id: str) -> dict:
        docs = load_data("docs.json")
        for d in docs:
            if d["doc_id"] == doc_id:
                # Try reading the real file
                filename = d.get("filename")
                content = self._read_file(filename) if filename else d.get("content", "")
                return {
                    "doc_id": d["doc_id"],
                    "title": d["title"],
                    "content": content or d.get("content", ""),
                    "filename": filename,
                    "file_path": os.path.join(DOCS_DIR, filename) if filename else None,
                    "last_modified": d.get("last_modified", ""),
                }
        return {"doc_id": doc_id, "error": "Not found"}

    def action_write_doc(self, title: str, content: str, doc_id: str = None) -> dict:
        docs = load_data("docs.json")

        if doc_id:
            # Update existing
            for d in docs:
                if d["doc_id"] == doc_id:
                    filename = d.get("filename") or f"{self._slug(title)}.md"
                    file_path = self._write_file(filename, content)
                    d["title"] = title
                    d["content"] = content[:200]  # Store preview in index
                    d["filename"] = filename
                    d["last_modified"] = self._now()
                    save_data("docs.json", docs)
                    return {
                        "doc_id": doc_id, "title": title, "status": "updated",
                        "filename": filename, "file_path": file_path,
                        "timestamp": self._now(),
                    }

        # Create new
        new_id = f"doc_{uuid.uuid4().hex[:8]}"
        filename = f"{self._slug(title)}.md"

        # Avoid filename collisions
        counter = 1
        base_filename = filename
        while os.path.exists(os.path.join(DOCS_DIR, filename)):
            name, ext = os.path.splitext(base_filename)
            filename = f"{name}_{counter}{ext}"
            counter += 1

        file_path = self._write_file(filename, content)

        new_doc = {
            "doc_id": new_id,
            "title": title,
            "type": "document",
            "content": content[:200],
            "filename": filename,
            "owner": "me@company.com",
            "last_modified": self._now(),
            "shared_with": [],
        }
        docs.append(new_doc)
        save_data("docs.json", docs)

        return {
            "doc_id": new_id, "title": title, "status": "created",
            "filename": filename, "file_path": file_path,
            "timestamp": self._now(),
        }

    def action_list_files(self, query: str = "", limit: int = 10) -> list:
        docs = load_data("docs.json")
        if query:
            q = query.lower()
            docs = [d for d in docs if q in d.get("title", "").lower() or q in d.get("content", "").lower()]
        return [
            {"id": d["doc_id"], "name": d["title"], "type": d.get("type", "document"),
             "filename": d.get("filename", ""), "last_modified": d.get("last_modified", "")}
            for d in docs[:limit]
        ]
