"""
Forms agent — Google Forms API v1 with local fallback.
Creates forms, reads responses. Uses shared OAuth token from auth_google.py.
Note: Google Forms API cannot submit responses (web only) — submit_response stays local.
"""

import json
import uuid
import urllib.request
from .base import BaseAgent, load_data, save_data
from .auth_google import get_access_token

FORMS_API = "https://forms.googleapis.com/v1"


def _forms(method: str, path: str, token: str, body: dict = None) -> dict:
    url = f"{FORMS_API}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw.strip() else {}


def _normalise_question(q) -> dict:
    """Accept a question as either a plain string or a dict."""
    if isinstance(q, str):
        return {"text": q, "type": "short_text"}
    if isinstance(q, dict):
        return q
    return {"text": str(q), "type": "short_text"}


def _question_to_gforms(q) -> dict:
    """Convert our question format to Google Forms API item format."""
    q = _normalise_question(q)
    qtype = q.get("type", "short_text")
    text = q.get("text") or q.get("question") or q.get("label") or ""

    item = {"title": text, "questionItem": {}}

    if qtype in ("short_text", "paragraph"):
        item["questionItem"]["question"] = {
            "required": False,
            "textQuestion": {"paragraph": qtype == "paragraph"},
        }
    elif qtype in ("multiple_choice", "checkbox"):
        options = [{"value": o} for o in q.get("options", [])]
        item["questionItem"]["question"] = {
            "required": False,
            "choiceQuestion": {
                "type": "RADIO" if qtype == "multiple_choice" else "CHECKBOX",
                "options": options,
            },
        }
    else:
        item["questionItem"]["question"] = {
            "required": False,
            "textQuestion": {"paragraph": False},
        }

    return item


class FormsAgent(BaseAgent):
    name = "forms"
    description = "Create Google Forms, list forms, and read responses"
    tools = [
        {
            "action": "create",
            "description": "Create a Google Form with questions",
            "params": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "questions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "type": {"type": "string",
                                         "enum": ["short_text", "paragraph",
                                                  "multiple_choice", "checkbox"]},
                                "options": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["text", "type"],
                        },
                    },
                },
                "required": ["title", "questions"],
            },
        },
        {
            "action": "list_forms",
            "description": "List all created forms",
            "params": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 10},
                },
            },
        },
        {
            "action": "get_responses",
            "description": "Get responses for a form",
            "params": {
                "type": "object",
                "properties": {
                    "form_id": {"type": "string"},
                },
                "required": ["form_id"],
            },
        },
        {
            "action": "submit_response",
            "description": "Submit a response to a local form",
            "params": {
                "type": "object",
                "properties": {
                    "form_id": {"type": "string"},
                    "respondent": {"type": "string"},
                    "answers": {"type": "object"},
                },
                "required": ["form_id", "answers"],
            },
        },
        {
            "action": "status",
            "description": "Check Google Forms connection status",
            "params": {"type": "object", "properties": {}},
        },
    ]

    # ── Status ────────────────────────────────────────────────────────────────

    def action_status(self) -> dict:
        token = get_access_token()
        if not token:
            return {"connected": False, "method": "Google Forms",
                    "setup": "Run authorize_drive.py to authorize Google access"}
        return {"connected": True, "method": "Google Forms API v1"}

    # ── Create ────────────────────────────────────────────────────────────────

    def action_create(self, title: str, questions: list) -> dict:
        token = get_access_token()
        if not token:
            return self._local_create(title, questions)

        try:
            # Normalise questions — LLM sometimes sends plain strings
            questions = [_normalise_question(q) for q in (questions or [])]

            # Step 1: create the form shell
            form = _forms("POST", "/forms", token, {"info": {"title": title}})
            form_id = form.get("formId", "")
            responder_uri = form.get("responderUri", "")

            # Step 2: add questions via batchUpdate
            if questions:
                requests = [
                    {"createItem": {"item": _question_to_gforms(q), "location": {"index": i}}}
                    for i, q in enumerate(questions)
                ]
                _forms("POST", f"/forms/{form_id}:batchUpdate", token,
                       {"requests": requests})

            # Save locally for list/reference
            record = {
                "form_id": form_id,
                "title": title,
                "questions": questions,
                "link": responder_uri,
                "created_at": self._now(),
                "storage": "google_forms",
            }
            self._local_save(record)

            return {
                "form_id": form_id,
                "title": title,
                "question_count": len(questions),
                "link": responder_uri,
                "status": "created",
                "storage": "google_forms",
            }
        except Exception as e:
            result = self._local_create(title, questions)
            result["gforms_error"] = str(e)
            return result

    # ── List ──────────────────────────────────────────────────────────────────

    def action_list_forms(self, limit: int = 10) -> list:
        forms = load_data("forms.json")
        return [
            {
                "form_id": f["form_id"],
                "title": f["title"],
                "question_count": len(f.get("questions", [])),
                "link": f.get("link", ""),
                "created_at": f.get("created_at", ""),
                "storage": f.get("storage", "local"),
            }
            for f in forms[-limit:]
        ]

    # ── Get responses ─────────────────────────────────────────────────────────

    def action_get_responses(self, form_id: str) -> dict:
        token = get_access_token()

        # Try Google Forms API first (only works for forms created via API)
        if token and not form_id.startswith("form_"):
            try:
                result = _forms("GET", f"/forms/{form_id}/responses", token)
                responses = result.get("responses", [])
                formatted = []
                for r in responses:
                    answers = {}
                    for qid, ans in r.get("answers", {}).items():
                        text_ans = ans.get("textAnswers", {}).get("answers", [])
                        answers[qid] = [a.get("value", "") for a in text_ans]
                    formatted.append({
                        "response_id": r.get("responseId", ""),
                        "submitted_at": r.get("lastSubmittedTime", ""),
                        "answers": answers,
                    })
                return {
                    "form_id": form_id,
                    "response_count": len(formatted),
                    "responses": formatted,
                }
            except Exception:
                pass

        # Fallback to local responses
        responses = load_data("form_responses.json")
        matched = [r for r in responses if r.get("form_id") == form_id]
        return {
            "form_id": form_id,
            "response_count": len(matched),
            "responses": matched,
        }

    # ── Submit response (local only — Forms API doesn't support this) ─────────

    def action_submit_response(self, form_id: str, answers: dict,
                               respondent: str = "anonymous") -> dict:
        forms = load_data("forms.json")
        if not any(f["form_id"] == form_id for f in forms):
            return {"form_id": form_id, "status": "form_not_found"}

        responses = load_data("form_responses.json")
        response_id = f"resp_{uuid.uuid4().hex[:8]}"
        new_response = {
            "response_id": response_id,
            "form_id": form_id,
            "respondent": respondent,
            "answers": answers,
            "submitted_at": self._now(),
        }
        responses.append(new_response)
        save_data("form_responses.json", responses)
        return {"response_id": response_id, "form_id": form_id, "status": "submitted"}

    # ── Local fallbacks ───────────────────────────────────────────────────────

    def _local_create(self, title: str, questions: list) -> dict:
        questions = [_normalise_question(q) for q in (questions or [])]
        form_id = f"form_{uuid.uuid4().hex[:8]}"
        record = {
            "form_id": form_id,
            "title": title,
            "questions": questions,
            "link": "",
            "created_at": self._now(),
            "storage": "local",
        }
        self._local_save(record)
        return {
            "form_id": form_id,
            "title": title,
            "question_count": len(questions),
            "status": "created",
            "storage": "local",
        }

    def _local_save(self, record: dict) -> None:
        forms = load_data("forms.json")
        forms = [f for f in forms if f.get("form_id") != record.get("form_id")]
        forms.append(record)
        save_data("forms.json", forms)
