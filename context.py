"""
SharedContext: cross-agent state that flows through the entire execution pipeline.
All agents can read/write to this context during execution.
"""

from __future__ import annotations
from datetime import datetime


class SharedContext:
    """Mutable context object passed through all execution steps."""

    def __init__(self, user_input: str):
        self.user_input = user_input
        self.created_at = datetime.now().isoformat(timespec="seconds")
        self._store: dict[str, any] = {}
        self._step_outputs: list[dict] = []
        self._metadata: dict[str, str] = {}

    def set(self, key: str, value):
        """Store a value in shared context."""
        self._store[key] = value

    def get(self, key: str, default=None):
        """Read a value from shared context."""
        return self._store.get(key, default)

    def has(self, key: str) -> bool:
        return key in self._store

    def push_output(self, step_idx: int, agent: str, action: str, result: dict):
        """Record the output of a completed step."""
        self._step_outputs.append({
            "step": step_idx,
            "agent": agent,
            "action": action,
            "result": result,
            "ts": datetime.now().isoformat(timespec="seconds"),
        })
        # Also store by agent name for easy cross-agent access
        self._store[f"{agent}.{action}"] = result
        self._store[f"step_{step_idx}"] = result
        self._store["last_output"] = result

    def get_output(self, step_idx: int) -> dict | None:
        """Get the output of a specific step."""
        for o in self._step_outputs:
            if o["step"] == step_idx:
                return o["result"]
        return None

    def get_agent_output(self, agent: str, action: str = None) -> dict | None:
        """Get the most recent output from a specific agent."""
        if action:
            return self._store.get(f"{agent}.{action}")
        # Find last output from this agent
        for o in reversed(self._step_outputs):
            if o["agent"] == agent:
                return o["result"]
        return None

    @property
    def last_output(self):
        return self._store.get("last_output")

    @property
    def all_outputs(self) -> list[dict]:
        return list(self._step_outputs)

    def snapshot(self) -> dict:
        """Serializable snapshot of context for logging/debugging."""
        return {
            "user_input": self.user_input,
            "store_keys": list(self._store.keys()),
            "step_count": len(self._step_outputs),
        }
