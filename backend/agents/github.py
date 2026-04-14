"""
GitHub agent — access repos, files, issues, PRs, commits via GitHub API v3.
"""

import json
import base64
import urllib.request
import urllib.parse
from .base import BaseAgent

GITHUB_API = "https://api.github.com"


def _gh(method: str, path: str, token: str, body: dict = None) -> dict | list:
    url = f"{GITHUB_API}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw.strip() else {}


class GitHubAgent(BaseAgent):
    name = "github"
    description = "Access GitHub repos, files, issues, PRs, and commits"
    tools = [
        {
            "action": "list_repos",
            "description": "List your GitHub repositories",
            "params": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 20},
                    "sort": {"type": "string", "default": "updated",
                             "enum": ["updated", "created", "pushed", "full_name"]},
                },
            },
        },
        {
            "action": "get_repo",
            "description": "Get details about a specific repository",
            "params": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "owner/repo format e.g. torvalds/linux"},
                },
                "required": ["repo"],
            },
        },
        {
            "action": "list_files",
            "description": "List files in a repository directory",
            "params": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "owner/repo"},
                    "path": {"type": "string", "default": "", "description": "directory path"},
                    "branch": {"type": "string", "default": "main"},
                },
                "required": ["repo"],
            },
        },
        {
            "action": "read_file",
            "description": "Read content of a file in a repository",
            "params": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "owner/repo"},
                    "path": {"type": "string", "description": "file path"},
                    "branch": {"type": "string", "default": "main"},
                },
                "required": ["repo", "path"],
            },
        },
        {
            "action": "list_issues",
            "description": "List issues in a repository",
            "params": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "owner/repo"},
                    "state": {"type": "string", "default": "open", "enum": ["open", "closed", "all"]},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["repo"],
            },
        },
        {
            "action": "create_issue",
            "description": "Create an issue in a repository",
            "params": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "owner/repo"},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "labels": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["repo", "title"],
            },
        },
        {
            "action": "list_prs",
            "description": "List pull requests in a repository",
            "params": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "owner/repo"},
                    "state": {"type": "string", "default": "open", "enum": ["open", "closed", "all"]},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["repo"],
            },
        },
        {
            "action": "list_commits",
            "description": "List recent commits in a repository",
            "params": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "owner/repo"},
                    "branch": {"type": "string", "default": "main"},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["repo"],
            },
        },
        {
            "action": "search_code",
            "description": "Search code across GitHub repositories",
            "params": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "search query e.g. 'filename:main.py repo:user/repo'"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        },
        {
            "action": "status",
            "description": "Check GitHub connection status",
            "params": {"type": "object", "properties": {}},
        },
    ]

    def _token(self) -> str | None:
        from config import GITHUB_TOKEN
        return GITHUB_TOKEN or None

    def action_status(self) -> dict:
        token = self._token()
        if not token:
            return {"connected": False, "method": "GitHub",
                    "setup": "Add GITHUB_TOKEN to .env"}
        try:
            r = _gh("GET", "/user", token)
            return {"connected": True, "method": f"GitHub ({r.get('login', '')})",
                    "name": r.get("name", ""), "public_repos": r.get("public_repos", 0)}
        except Exception as e:
            return {"connected": False, "method": "GitHub", "error": str(e)}

    def action_list_repos(self, limit: int = 20, sort: str = "updated") -> list:
        token = self._token()
        if not token:
            return [{"error": "GitHub token not configured"}]
        try:
            results = _gh("GET", f"/user/repos?per_page={min(limit,100)}&sort={sort}", token)
            return [
                {
                    "repo": r.get("full_name", ""),
                    "description": r.get("description", ""),
                    "language": r.get("language", ""),
                    "stars": r.get("stargazers_count", 0),
                    "updated": r.get("updated_at", ""),
                    "private": r.get("private", False),
                    "link": r.get("html_url", ""),
                }
                for r in (results if isinstance(results, list) else [])
            ]
        except Exception as e:
            return [{"error": str(e)}]

    def action_get_repo(self, repo: str) -> dict:
        token = self._token()
        if not token:
            return {"error": "GitHub token not configured"}
        try:
            r = _gh("GET", f"/repos/{repo}", token)
            return {
                "repo": r.get("full_name", ""),
                "description": r.get("description", ""),
                "language": r.get("language", ""),
                "stars": r.get("stargazers_count", 0),
                "forks": r.get("forks_count", 0),
                "open_issues": r.get("open_issues_count", 0),
                "default_branch": r.get("default_branch", "main"),
                "updated": r.get("updated_at", ""),
                "link": r.get("html_url", ""),
            }
        except Exception as e:
            return {"error": str(e)}

    def action_list_files(self, repo: str, path: str = "", branch: str = "main") -> list:
        token = self._token()
        if not token:
            return [{"error": "GitHub token not configured"}]
        try:
            endpoint = f"/repos/{repo}/contents/{path}?ref={branch}"
            results = _gh("GET", endpoint, token)
            if isinstance(results, dict):
                results = [results]
            return [
                {
                    "name": f.get("name", ""),
                    "path": f.get("path", ""),
                    "type": f.get("type", ""),
                    "size": f.get("size", 0),
                    "link": f.get("html_url", ""),
                }
                for f in results
            ]
        except Exception as e:
            return [{"error": str(e)}]

    def action_read_file(self, repo: str, path: str, branch: str = "main") -> dict:
        token = self._token()
        if not token:
            return {"error": "GitHub token not configured"}
        try:
            r = _gh("GET", f"/repos/{repo}/contents/{path}?ref={branch}", token)
            content_b64 = r.get("content", "")
            content = base64.b64decode(content_b64).decode("utf-8", errors="replace")
            return {
                "repo": repo,
                "path": path,
                "branch": branch,
                "size": r.get("size", 0),
                "content": content,
                "link": r.get("html_url", ""),
            }
        except Exception as e:
            return {"error": str(e)}

    def action_list_issues(self, repo: str, state: str = "open", limit: int = 20) -> list:
        token = self._token()
        if not token:
            return [{"error": "GitHub token not configured"}]
        try:
            results = _gh("GET", f"/repos/{repo}/issues?state={state}&per_page={min(limit,100)}", token)
            return [
                {
                    "issue_id": i.get("number", ""),
                    "title": i.get("title", ""),
                    "state": i.get("state", ""),
                    "author": i.get("user", {}).get("login", ""),
                    "created": i.get("created_at", ""),
                    "labels": [l.get("name", "") for l in i.get("labels", [])],
                    "link": i.get("html_url", ""),
                }
                for i in (results if isinstance(results, list) else [])
                if "pull_request" not in i  # exclude PRs from issues list
            ]
        except Exception as e:
            return [{"error": str(e)}]

    def action_create_issue(self, repo: str, title: str, body: str = "",
                            labels: list = None) -> dict:
        token = self._token()
        if not token:
            return {"error": "GitHub token not configured"}
        try:
            payload = {"title": title, "body": body}
            if labels:
                payload["labels"] = labels
            r = _gh("POST", f"/repos/{repo}/issues", token, payload)
            return {
                "issue_id": r.get("number", ""),
                "title": r.get("title", ""),
                "state": r.get("state", ""),
                "link": r.get("html_url", ""),
                "status": "created",
            }
        except Exception as e:
            return {"error": str(e)}

    def action_list_prs(self, repo: str, state: str = "open", limit: int = 20) -> list:
        token = self._token()
        if not token:
            return [{"error": "GitHub token not configured"}]
        try:
            results = _gh("GET", f"/repos/{repo}/pulls?state={state}&per_page={min(limit,100)}", token)
            return [
                {
                    "pr_id": p.get("number", ""),
                    "title": p.get("title", ""),
                    "state": p.get("state", ""),
                    "author": p.get("user", {}).get("login", ""),
                    "branch": p.get("head", {}).get("ref", ""),
                    "created": p.get("created_at", ""),
                    "link": p.get("html_url", ""),
                }
                for p in (results if isinstance(results, list) else [])
            ]
        except Exception as e:
            return [{"error": str(e)}]

    def action_list_commits(self, repo: str, branch: str = "main", limit: int = 20) -> list:
        token = self._token()
        if not token:
            return [{"error": "GitHub token not configured"}]
        try:
            results = _gh("GET", f"/repos/{repo}/commits?sha={branch}&per_page={min(limit,100)}", token)
            return [
                {
                    "sha": c.get("sha", "")[:7],
                    "message": c.get("commit", {}).get("message", "").split("\n")[0],
                    "author": c.get("commit", {}).get("author", {}).get("name", ""),
                    "date": c.get("commit", {}).get("author", {}).get("date", ""),
                    "link": c.get("html_url", ""),
                }
                for c in (results if isinstance(results, list) else [])
            ]
        except Exception as e:
            return [{"error": str(e)}]

    def action_search_code(self, query: str, limit: int = 10) -> list:
        token = self._token()
        if not token:
            return [{"error": "GitHub token not configured"}]
        try:
            q = urllib.parse.quote(query)
            results = _gh("GET", f"/search/code?q={q}&per_page={min(limit,30)}", token)
            return [
                {
                    "repo": i.get("repository", {}).get("full_name", ""),
                    "path": i.get("path", ""),
                    "name": i.get("name", ""),
                    "link": i.get("html_url", ""),
                }
                for i in results.get("items", [])
            ]
        except Exception as e:
            return [{"error": str(e)}]
