import json
import uuid
import urllib.request
import urllib.error
from .base import BaseAgent, load_data, save_data


NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _notion_request(method: str, path: str, token: str, body: dict = None) -> dict:
    url = f"{NOTION_API}/{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode())


class NotionAgent(BaseAgent):
    name = "notion"
    description = "Read and write real Notion pages via free Notion API"
    tools = [
        {
            "action": "list_pages",
            "description": "List all Notion pages the integration has access to",
            "params": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 10},
                },
            },
        },
        {
            "action": "read_page",
            "description": "Read a Notion page by ID",
            "params": {
                "type": "object",
                "properties": {
                    "page_id": {"type": "string"},
                },
                "required": ["page_id"],
            },
        },
        {
            "action": "write_page",
            "description": "Create a new Notion page with title and content",
            "params": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "parent_id": {"type": "string", "description": "Parent page or database ID"},
                },
                "required": ["title", "content"],
            },
        },
        {
            "action": "status",
            "description": "Check Notion API connection status",
            "params": {"type": "object", "properties": {}},
        },
    ]

    def action_status(self) -> dict:
        from config import NOTION_TOKEN
        if not NOTION_TOKEN:
            return {
                "connected": False,
                "setup": "Add NOTION_TOKEN to .env — free from notion.so/my-integrations",
            }
        try:
            _notion_request("GET", "users/me", NOTION_TOKEN)
            return {"connected": True, "method": "Notion API (free)"}
        except Exception as e:
            return {"connected": False, "error": str(e)}

    def action_list_pages(self, limit: int = 10) -> list:
        from config import NOTION_TOKEN
        if not NOTION_TOKEN:
            return self._local_list(limit)
        try:
            resp = _notion_request("POST", "search", NOTION_TOKEN, {
                "filter": {"value": "page", "property": "object"},
                "page_size": limit,
            })
            results = []
            for r in resp.get("results", []):
                title = ""
                props = r.get("properties", {})
                # Try common title property names
                for key in ("title", "Name", "Page", "Title"):
                    if key in props:
                        texts = props[key].get("title", [])
                        title = "".join(t.get("plain_text", "") for t in texts)
                        if title:
                            break
                results.append({
                    "page_id": r["id"],
                    "title": title or "(Untitled)",
                    "last_edited": r.get("last_edited_time", ""),
                    "url": r.get("url", ""),
                })
            return results
        except Exception as e:
            return [{"error": str(e), "note": "Check your NOTION_TOKEN and integration page access"}]

    def action_read_page(self, page_id: str) -> dict:
        from config import NOTION_TOKEN
        if not NOTION_TOKEN:
            return self._local_read(page_id)
        try:
            page = _notion_request("GET", f"pages/{page_id}", NOTION_TOKEN)
            blocks = _notion_request("GET", f"blocks/{page_id}/children", NOTION_TOKEN)
            content_parts = []
            for block in blocks.get("results", []):
                btype = block.get("type", "")
                bdata = block.get(btype, {})
                texts = bdata.get("rich_text", [])
                text = "".join(t.get("plain_text", "") for t in texts)
                if text:
                    content_parts.append(text)
            title = ""
            props = page.get("properties", {})
            for key in ("title", "Name", "Title"):
                if key in props:
                    texts = props[key].get("title", [])
                    title = "".join(t.get("plain_text", "") for t in texts)
                    if title:
                        break
            return {
                "page_id": page_id,
                "title": title or "(Untitled)",
                "content": "\n".join(content_parts),
                "url": page.get("url", ""),
                "last_edited": page.get("last_edited_time", ""),
            }
        except Exception as e:
            return {"page_id": page_id, "error": str(e)}

    def action_write_page(self, title: str, content: str, parent_id: str = None) -> dict:
        from config import NOTION_TOKEN
        if not NOTION_TOKEN:
            return self._local_write(title, content, parent_id)
        if not parent_id:
            # No parent_id — try to auto-find one, else save locally
            try:
                resp = _notion_request("POST", "search", NOTION_TOKEN, {
                    "filter": {"value": "page", "property": "object"}, "page_size": 1
                })
                results = resp.get("results", [])
                if results:
                    parent_id = results[0]["id"]
                else:
                    return self._local_write(title, content, None)
            except Exception:
                return self._local_write(title, content, None)
        try:
            # Build paragraph blocks from content lines
            paragraphs = [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": line}}]
                    },
                }
                for line in content.split("\n") if line.strip()
            ]
            body = {
                "parent": {"page_id": parent_id},
                "properties": {
                    "title": {
                        "title": [{"type": "text", "text": {"content": title}}]
                    }
                },
                "children": paragraphs[:100],  # Notion API limit
            }
            resp = _notion_request("POST", "pages", NOTION_TOKEN, body)
            return {
                "page_id": resp["id"],
                "title": title,
                "url": resp.get("url", ""),
                "status": "created",
            }
        except Exception as e:
            return {"error": str(e), "status": "failed"}

    # ── Local fallbacks (no token) ────────────────────────────────────────────

    def _local_list(self, limit: int) -> list:
        pages = load_data("notion.json")
        return [
            {"page_id": p["page_id"], "title": p["title"], "last_edited": p.get("last_edited", "")}
            for p in pages[-limit:]
        ]

    def _local_read(self, page_id: str) -> dict:
        pages = load_data("notion.json")
        for p in pages:
            if p["page_id"] == page_id:
                return {"page_id": p["page_id"], "title": p["title"], "content": p["content"], "last_edited": p.get("last_edited", "")}
        return {"page_id": page_id, "error": "Not found"}

    def _local_write(self, title: str, content: str, parent_id: str = None) -> dict:
        pages = load_data("notion.json")
        new_id = f"notion_{uuid.uuid4().hex[:8]}"
        new_page = {"page_id": new_id, "title": title, "content": content, "parent_id": parent_id, "last_edited": self._now()}
        pages.append(new_page)
        save_data("notion.json", pages)
        return {"page_id": new_id, "title": title, "status": "saved_locally", "note": "Add NOTION_TOKEN to .env to sync with real Notion"}
