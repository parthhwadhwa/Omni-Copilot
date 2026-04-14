"""
Google Drive agent — create, read, list files via Drive API v3.
Uses OAuth2 user credentials (works with personal Gmail, no Workspace needed).
Falls back to local /docs/ storage when credentials are not configured.
"""

import json
import os
import uuid
import urllib.request
from .base import BaseAgent, load_data, save_data, DOCS_DIR
from .auth_google import get_access_token as _get_access_token

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3"


def _drive_request(method: str, url: str, token: str,
                   body: dict | bytes = None) -> dict:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw.strip() else {}


class DriveAgent(BaseAgent):
    name = "drive"
    description = "Create, read, and list files in Google Drive"
    tools = [
        {
            "action": "create_doc",
            "description": "Create a document in Google Drive",
            "params": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "File name"},
                    "content": {"type": "string", "description": "Document content"},
                },
                "required": ["name", "content"],
            },
        },
        {
            "action": "upload_file",
            "description": "Upload a file to Google Drive",
            "params": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "File name"},
                    "content": {"type": "string", "description": "File content"},
                },
                "required": ["name", "content"],
            },
        },
        {
            "action": "list_files",
            "description": "List files in Google Drive",
            "params": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 10},
                    "query": {"type": "string", "description": "Search query"},
                },
            },
        },
        {
            "action": "read_file",
            "description": "Read a file from Google Drive by ID",
            "params": {
                "type": "object",
                "properties": {
                    "file_id": {"type": "string"},
                },
                "required": ["file_id"],
            },
        },
        {
            "action": "status",
            "description": "Check Google Drive API connection status",
            "params": {"type": "object", "properties": {}},
        },
    ]

    def action_status(self) -> dict:
        token = _get_access_token()
        if not token:
            return {
                "connected": False,
                "method": "Google Drive",
                "setup": "Add GOOGLE_SERVICE_ACCOUNT_FILE to .env (OAuth2 client or service account JSON)",
            }
        try:
            r = _drive_request("GET", f"{DRIVE_API}/about?fields=user", token)
            email = r.get("user", {}).get("emailAddress", "")
            return {"connected": True, "method": f"Google Drive ({email})"}
        except Exception as e:
            return {"connected": False, "method": "Google Drive", "error": str(e)}

    def action_create_doc(self, name: str, content: str) -> dict:
        return self._upload(name, content)

    def action_upload_file(self, name: str, content: str) -> dict:
        return self._upload(name, content)

    def action_list_files(self, limit: int = 10, query: str = "") -> list:
        token = _get_access_token()
        if not token:
            return self._local_list(limit, query)
        try:
            params = f"pageSize={limit}&fields=files(id,name,mimeType,modifiedTime,webViewLink)"
            if query:
                q = urllib.parse.quote(f"name contains '{query}'")
                params += f"&q={q}"
            resp = _drive_request("GET", f"{DRIVE_API}/files?{params}", token)
            return [
                {
                    "file_id": f["id"],
                    "name": f.get("name", ""),
                    "type": f.get("mimeType", ""),
                    "last_modified": f.get("modifiedTime", ""),
                    "link": f.get("webViewLink", ""),
                }
                for f in resp.get("files", [])
            ]
        except Exception:
            return self._local_list(limit, query)

    def action_read_file(self, file_id: str) -> dict:
        token = _get_access_token()
        if not token:
            return self._local_read(file_id)
        try:
            meta = _drive_request(
                "GET",
                f"{DRIVE_API}/files/{file_id}?fields=id,name,mimeType,webViewLink",
                token,
            )
            mime = meta.get("mimeType", "")
            if "google-apps" in mime:
                url = f"{DRIVE_API}/files/{file_id}/export?mimeType=text/plain"
            else:
                url = f"{DRIVE_API}/files/{file_id}?alt=media"
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode()
            return {
                "file_id": file_id,
                "name": meta.get("name", ""),
                "content": content,
                "link": meta.get("webViewLink", ""),
            }
        except Exception as e:
            local = self._local_read(file_id)
            return local if "error" not in local else {"file_id": file_id, "error": str(e)}

    # ── Upload helper ─────────────────────────────────────────────────────────

    def _upload(self, name: str, content: str) -> dict:
        token = _get_access_token()
        if not token:
            return self._local_create(name, content)
        try:
            boundary = "omni_" + uuid.uuid4().hex[:8]
            metadata = json.dumps({"name": name})
            body = (
                f"--{boundary}\r\n"
                f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
                f"{metadata}\r\n"
                f"--{boundary}\r\n"
                f"Content-Type: text/plain; charset=UTF-8\r\n\r\n"
                f"{content}\r\n"
                f"--{boundary}--"
            ).encode("utf-8")
            url = f"{DRIVE_UPLOAD}/files?uploadType=multipart&fields=id,name,webViewLink"
            req = urllib.request.Request(url, data=body, method="POST", headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": f"multipart/related; boundary={boundary}",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())

            file_id = result["id"]
            link = result.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"

            # Backup locally
            self._local_create(name, content)

            return {
                "file_id": file_id,
                "name": result.get("name", name),
                "link": link,
                "status": "uploaded",
                "storage": "google_drive",
            }
        except Exception as e:
            result = self._local_create(name, content)
            result["drive_error"] = str(e)
            return result

    # ── Local fallbacks ───────────────────────────────────────────────────────

    def _local_create(self, name: str, content: str) -> dict:
        os.makedirs(DOCS_DIR, exist_ok=True)
        file_id = f"drive_{uuid.uuid4().hex[:8]}"
        slug = name.lower().replace(" ", "_")[:50]
        ext = ".txt" if "." not in slug else ""
        filename = f"{slug}{ext}"
        counter = 1
        base = filename
        while os.path.exists(os.path.join(DOCS_DIR, filename)):
            n, e = os.path.splitext(base)
            filename = f"{n}_{counter}{e}"
            counter += 1
        with open(os.path.join(DOCS_DIR, filename), "w") as f:
            f.write(content)
        records = load_data("drive.json")
        records.append({"file_id": file_id, "name": name, "filename": filename,
                        "created_at": self._now()})
        save_data("drive.json", records)
        return {"file_id": file_id, "name": name, "filename": filename,
                "status": "saved_locally", "storage": "local"}

    def _local_list(self, limit: int, query: str = "") -> list:
        records = load_data("drive.json")
        if query:
            q = query.lower()
            records = [r for r in records if q in r.get("name", "").lower()]
        return [{"file_id": r["file_id"], "name": r["name"],
                 "last_modified": r.get("created_at", "")}
                for r in records[-limit:]]

    def _local_read(self, file_id: str) -> dict:
        for r in load_data("drive.json"):
            if r["file_id"] == file_id:
                path = os.path.join(DOCS_DIR, r.get("filename", ""))
                content = ""
                if os.path.exists(path):
                    with open(path) as f:
                        content = f.read()
                return {"file_id": file_id, "name": r["name"], "content": content}
        return {"file_id": file_id, "error": "Not found"}
