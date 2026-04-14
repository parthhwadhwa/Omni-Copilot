"""
Code agent — read, write, search, and list local code files.
Works on the local filesystem. Supports all common code file types.
"""

import os
from .base import BaseAgent

CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h",
    ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".r", ".m",
    ".sh", ".bash", ".zsh", ".sql", ".html", ".css", ".scss", ".json",
    ".yaml", ".yml", ".toml", ".xml", ".md", ".env", ".gitignore",
    ".dockerfile", ".tf", ".vue", ".svelte",
}

MAX_FILE_SIZE = 100_000  # 100KB limit for reading

# Default to the project root (two levels above this file: agents/ → backend/ → project/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def _resolve_dir(directory: str) -> str:
    """Resolve directory, treating natural-language inputs as project root."""
    if not directory or directory.lower() in (".", "current directory", "current dir", "here", "cwd"):
        return PROJECT_ROOT
    return os.path.expanduser(directory)


class CodeAgent(BaseAgent):
    name = "code"
    description = "Read, write, search, and list local code files on the filesystem"
    tools = [
        {
            "action": "read_file",
            "description": "Read the content of a local code file",
            "params": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative file path"},
                },
                "required": ["path"],
            },
        },
        {
            "action": "write_file",
            "description": "Write or overwrite a local code file",
            "params": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write"},
                    "content": {"type": "string", "description": "File content"},
                },
                "required": ["path", "content"],
            },
        },
        {
            "action": "list_files",
            "description": "List code files in a directory",
            "params": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "Directory path", "default": "."},
                    "extension": {"type": "string", "description": "Filter by extension e.g. .py"},
                    "recursive": {"type": "boolean", "default": False},
                    "limit": {"type": "integer", "default": 50},
                },
            },
        },
        {
            "action": "search_in_files",
            "description": "Search for a string or pattern inside code files",
            "params": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Text to search for"},
                    "directory": {"type": "string", "description": "Directory to search in", "default": "."},
                    "extension": {"type": "string", "description": "Filter by extension e.g. .py"},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["query"],
            },
        },
        {
            "action": "summarize_file",
            "description": "Get a summary of a code file (line count, functions, classes)",
            "params": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                },
                "required": ["path"],
            },
        },
    ]

    def action_status(self) -> dict:
        return {"connected": True, "method": "local filesystem", "root": PROJECT_ROOT}

    def action_read_file(self, path: str) -> dict:
        path = os.path.expanduser(path)
        if not os.path.exists(path):
            return {"error": f"File not found: {path}"}
        if not os.path.isfile(path):
            return {"error": f"Not a file: {path}"}
        size = os.path.getsize(path)
        if size > MAX_FILE_SIZE:
            return {"error": f"File too large ({size} bytes). Max is {MAX_FILE_SIZE} bytes."}
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return {
                "path": path,
                "size": size,
                "lines": content.count("\n") + 1,
                "content": content,
            }
        except Exception as e:
            return {"error": str(e)}

    def action_write_file(self, path: str, content: str) -> dict:
        path = os.path.expanduser(path)
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return {
                "path": path,
                "size": len(content.encode("utf-8")),
                "lines": content.count("\n") + 1,
                "status": "written",
            }
        except Exception as e:
            return {"error": str(e)}

    def action_list_files(self, directory: str = ".", extension: str = "",
                          recursive: bool = False, limit: int = 50) -> list:
        directory = _resolve_dir(directory)
        if not os.path.exists(directory):
            return [{"error": f"Directory not found: {directory}"}]

        results = []
        ext = extension.lower() if extension else ""

        try:
            if recursive:
                for root, dirs, files in os.walk(directory):
                    # Skip hidden dirs and common non-code dirs
                    dirs[:] = [d for d in dirs if not d.startswith(".")
                                and d not in ("node_modules", "__pycache__", "venv", ".git", "dist", "build")]
                    for fname in files:
                        fpath = os.path.join(root, fname)
                        fext = os.path.splitext(fname)[1].lower()
                        if ext and fext != ext:
                            continue
                        if not ext and fext not in CODE_EXTENSIONS:
                            continue
                        results.append(self._file_info(fpath))
                        if len(results) >= limit:
                            break
                    if len(results) >= limit:
                        break
            else:
                for fname in os.listdir(directory):
                    fpath = os.path.join(directory, fname)
                    if not os.path.isfile(fpath):
                        continue
                    fext = os.path.splitext(fname)[1].lower()
                    if ext and fext != ext:
                        continue
                    if not ext and fext not in CODE_EXTENSIONS:
                        continue
                    results.append(self._file_info(fpath))
                    if len(results) >= limit:
                        break
        except Exception as e:
            return [{"error": str(e)}]

        return sorted(results, key=lambda x: x.get("name", ""))

    def action_search_in_files(self, query: str, directory: str = ".",
                               extension: str = "", limit: int = 20) -> list:
        directory = _resolve_dir(directory)
        if not os.path.exists(directory):
            return [{"error": f"Directory not found: {directory}"}]

        ext = extension.lower() if extension else ""
        matches = []
        query_lower = query.lower()

        try:
            for root, dirs, files in os.walk(directory):
                dirs[:] = [d for d in dirs if not d.startswith(".")
                            and d not in ("node_modules", "__pycache__", "venv", ".git", "dist", "build")]
                for fname in files:
                    fpath = os.path.join(root, fname)
                    fext = os.path.splitext(fname)[1].lower()
                    if ext and fext != ext:
                        continue
                    if not ext and fext not in CODE_EXTENSIONS:
                        continue
                    if os.path.getsize(fpath) > MAX_FILE_SIZE:
                        continue
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                            for lineno, line in enumerate(f, 1):
                                if query_lower in line.lower():
                                    matches.append({
                                        "path": fpath,
                                        "line": lineno,
                                        "match": line.strip(),
                                    })
                                    if len(matches) >= limit:
                                        return matches
                    except Exception:
                        continue
        except Exception as e:
            return [{"error": str(e)}]

        return matches

    def action_summarize_file(self, path: str) -> dict:
        path = os.path.expanduser(path)
        result = self.action_read_file(path)
        if "error" in result:
            return result

        content = result["content"]
        lines = content.splitlines()
        ext = os.path.splitext(path)[1].lower()

        summary = {
            "path": path,
            "lines": len(lines),
            "size": result["size"],
            "extension": ext,
        }

        # Language-specific parsing
        if ext == ".py":
            functions = [l.strip() for l in lines if l.strip().startswith("def ")]
            classes = [l.strip() for l in lines if l.strip().startswith("class ")]
            imports = [l.strip() for l in lines if l.strip().startswith(("import ", "from "))]
            summary["functions"] = functions[:20]
            summary["classes"] = classes[:10]
            summary["imports"] = imports[:20]
        elif ext in (".js", ".ts", ".jsx", ".tsx"):
            functions = [l.strip() for l in lines if "function " in l or "=>" in l]
            imports = [l.strip() for l in lines if l.strip().startswith("import ")]
            summary["functions"] = functions[:20]
            summary["imports"] = imports[:20]
        elif ext in (".java", ".cs", ".kt"):
            classes = [l.strip() for l in lines if "class " in l]
            methods = [l.strip() for l in lines if "void " in l or "public " in l or "private " in l]
            summary["classes"] = classes[:10]
            summary["methods"] = methods[:20]

        return summary

    def _file_info(self, path: str) -> dict:
        stat = os.stat(path)
        return {
            "name": os.path.basename(path),
            "path": path,
            "extension": os.path.splitext(path)[1].lower(),
            "size": stat.st_size,
            "modified": self._now(),
        }
