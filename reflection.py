"""
Reflection + Retry engine: evaluates step results, retries on failure.
"""

from __future__ import annotations
from context import SharedContext


class StepResult:
    """Outcome of executing + reflecting on a single step."""

    def __init__(self, status: str, result: dict, retries: int = 0, reflection: str = ""):
        self.status = status        # "success" | "retried" | "failed" | "skipped"
        self.result = result
        self.retries = retries
        self.reflection = reflection

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "result": self.result,
            "retries": self.retries,
            "reflection": self.reflection,
        }


def evaluate_result(result: dict, step: dict, ctx: SharedContext) -> tuple[str, str]:
    """
    Evaluate the quality of a step result.
    Returns (quality, reason) where quality is "good" | "poor" | "fail".
    """
    if not result.get("ok"):
        error = result.get("error", "Unknown error")
        return ("fail", f"Step failed: {error}")

    data = result.get("result")

    # Empty results
    if data is None:
        return ("poor", "Result was None")

    if isinstance(data, list) and len(data) == 0:
        return ("poor", "Empty result list — no data returned")

    if isinstance(data, dict):
        # Check for error keys embedded in result
        if "error" in data:
            return ("poor", f"Result contains error: {data['error']}")

        # Check if a required output is missing
        if data.get("status") == "not_found":
            return ("poor", "Resource not found")

    return ("good", "Step completed successfully")


def build_retry_params(original_params: dict, step: dict, failure_reason: str, ctx: SharedContext) -> dict:
    """
    Attempt to improve params for a retry based on the failure reason.
    """
    improved = dict(original_params)
    agent = step.get("agent", "")
    action = step.get("action", "")

    # If doc not found, try fallback ID
    if "not found" in failure_reason.lower() and agent == "docs":
        improved["doc_id"] = "doc_00001"

    # If event not found, try listing first
    if "not found" in failure_reason.lower() and agent == "calendar":
        improved["event_id"] = "evt_00001"

    # If empty results on search, broaden query
    if "empty" in failure_reason.lower() and agent == "search":
        q = improved.get("query", "")
        # Try just the first word
        words = q.split()
        if len(words) > 1:
            improved["query"] = words[0]

    # For mail, ensure required fields
    if agent == "mail" and action == "send":
        improved.setdefault("to", "team@acme.com")
        improved.setdefault("subject", "Update from Omni Copilot")
        improved.setdefault("body", "Auto-generated message")

    # For slack, ensure channel
    if agent == "slack":
        improved.setdefault("channel", "general")

    return improved


def reflect_and_retry(
    agent,
    action: str,
    params: dict,
    first_result: dict,
    step: dict,
    ctx: SharedContext,
    execute_fn,
) -> StepResult:
    """
    Evaluate result, retry once if poor/fail, return final StepResult.
    execute_fn(agent, action, params) -> dict
    """
    quality, reason = evaluate_result(first_result, step, ctx)

    if quality == "good":
        return StepResult(
            status="success",
            result=first_result,
            retries=0,
            reflection=reason,
        )

    # Attempt retry with improved params
    improved_params = build_retry_params(params, step, reason, ctx)
    retry_result = execute_fn(agent, action, improved_params)

    retry_quality, retry_reason = evaluate_result(retry_result, step, ctx)

    if retry_quality == "good":
        return StepResult(
            status="retried",
            result=retry_result,
            retries=1,
            reflection=f"Retry succeeded: {retry_reason} (original: {reason})",
        )

    # Failed after retry
    return StepResult(
        status="failed",
        result=retry_result,
        retries=1,
        reflection=f"Failed after retry: {retry_reason} (original: {reason})",
    )
