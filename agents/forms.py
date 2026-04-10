import uuid
from .base import BaseAgent, load_data, save_data


class FormsAgent(BaseAgent):
    name = "forms"
    description = "Create JSON-based forms and collect responses locally"
    tools = [
        {
            "action": "create",
            "description": "Create a form (persisted to forms.json)",
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
                                "type": {"type": "string", "enum": ["short_text", "paragraph", "multiple_choice", "checkbox"]},
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
            "action": "get_responses",
            "description": "Get responses for a form from form_responses.json",
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
            "description": "Submit a response to a form",
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
            "action": "list_forms",
            "description": "List all created forms",
            "params": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 10},
                },
            },
        },
    ]

    def action_create(self, title: str, questions: list) -> dict:
        forms = load_data("forms.json")
        form_id = f"form_{uuid.uuid4().hex[:8]}"
        new_form = {
            "form_id": form_id,
            "title": title,
            "questions": questions,
            "created_at": self._now(),
        }
        forms.append(new_form)
        save_data("forms.json", forms)
        return {
            "form_id": form_id,
            "title": title,
            "question_count": len(questions),
            "status": "created",
        }

    def action_get_responses(self, form_id: str) -> dict:
        responses = load_data("form_responses.json")
        matched = [r for r in responses if r.get("form_id") == form_id]
        return {
            "form_id": form_id,
            "response_count": len(matched),
            "responses": matched,
        }

    def action_submit_response(self, form_id: str, answers: dict, respondent: str = "anonymous") -> dict:
        # Verify form exists
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
        return {
            "response_id": response_id,
            "form_id": form_id,
            "status": "submitted",
        }

    def action_list_forms(self, limit: int = 10) -> list:
        forms = load_data("forms.json")
        return [
            {"form_id": f["form_id"], "title": f["title"],
             "question_count": len(f.get("questions", [])), "created_at": f.get("created_at", "")}
            for f in forms[-limit:]
        ]
