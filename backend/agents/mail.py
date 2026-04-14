import smtplib
import imaplib
import email
import email.header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from .base import BaseAgent, load_data, save_data


def _decode_header(value: str) -> str:
    if not value:
        return ""
    parts = email.header.decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(str(part))
    return " ".join(decoded)


def _get_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get("Content-Disposition"):
                try:
                    return part.get_payload(decode=True).decode(errors="replace")
                except Exception:
                    pass
    else:
        try:
            return msg.get_payload(decode=True).decode(errors="replace")
        except Exception:
            pass
    return ""


class MailAgent(BaseAgent):
    name = "mail"
    description = "Send and read real emails via Gmail SMTP/IMAP"
    tools = [
        {
            "action": "send",
            "description": "Send an email via Gmail SMTP",
            "params": {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
        },
        {
            "action": "read",
            "description": "Read recent emails from Gmail inbox",
            "params": {
                "type": "object",
                "properties": {
                    "folder": {"type": "string", "default": "inbox"},
                    "limit": {"type": "integer", "default": 10},
                },
            },
        },
    ]

    def action_status(self) -> dict:
        from config import EMAIL_USER, EMAIL_PASS
        if EMAIL_USER and EMAIL_PASS:
            return {"connected": True, "method": "IMAP/SMTP", "account": EMAIL_USER}
        return {"connected": False, "setup": "Add EMAIL_USER and EMAIL_PASS to .env"}

    def action_send(self, to: str, subject: str, body: str) -> dict:
        from config import EMAIL_USER, EMAIL_PASS

        # Save to local sent folder
        emails = load_data("emails.json")
        new_email = {
            "id": f"msg_{len(emails) + 1:05d}",
            "from": EMAIL_USER or "me",
            "to": to,
            "subject": subject,
            "body": body,
            "date": self._now(),
            "read": True,
            "folder": "sent",
        }
        emails.append(new_email)
        save_data("emails.json", emails)

        smtp_sent = False
        smtp_error = None
        if EMAIL_USER and EMAIL_PASS:
            try:
                msg = MIMEMultipart()
                msg["From"] = EMAIL_USER
                msg["To"] = to
                msg["Subject"] = subject
                msg.attach(MIMEText(body, "plain"))
                with smtplib.SMTP("smtp.gmail.com", 587) as server:
                    server.starttls()
                    server.login(EMAIL_USER, EMAIL_PASS)
                    server.send_message(msg)
                smtp_sent = True
            except Exception as e:
                smtp_error = str(e)

        return {
            "message_id": new_email["id"],
            "to": to,
            "subject": subject,
            "timestamp": self._now(),
            "smtp_sent": smtp_sent,
            "smtp_error": smtp_error,
            "status": "sent" if smtp_sent else "saved_locally",
        }

    def action_read(self, folder: str = "inbox", limit: int = 10) -> list:
        from config import EMAIL_USER, EMAIL_PASS

        # Try real Gmail IMAP first
        if EMAIL_USER and EMAIL_PASS:
            try:
                imap = imaplib.IMAP4_SSL("imap.gmail.com")
                imap.login(EMAIL_USER, EMAIL_PASS)

                imap_folder = "INBOX" if folder.lower() == "inbox" else folder
                imap.select(imap_folder, readonly=True)

                _, data = imap.search(None, "ALL")
                ids = data[0].split()
                # Get latest N
                ids = ids[-limit:] if len(ids) > limit else ids
                ids = list(reversed(ids))

                result = []
                for uid in ids:
                    _, msg_data = imap.fetch(uid, "(RFC822)")
                    if not msg_data or not msg_data[0]:
                        continue
                    raw = msg_data[0][1]
                    msg = email.message_from_bytes(raw)
                    subject = _decode_header(msg.get("Subject", "(no subject)"))
                    from_addr = _decode_header(msg.get("From", ""))
                    date = msg.get("Date", "")
                    body = _get_body(msg)
                    result.append({
                        "id": uid.decode(),
                        "from": from_addr,
                        "subject": subject,
                        "snippet": body[:100].strip(),
                        "date": date,
                        "read": False,
                    })

                imap.logout()
                return result

            except Exception as e:
                # Fall through to local if IMAP fails
                pass

        # Fallback: local store
        emails = load_data("emails.json")
        filtered = [e for e in emails if e.get("folder", "inbox") == folder]
        filtered.sort(key=lambda e: e.get("date", ""), reverse=True)
        return [
            {
                "id": e["id"],
                "from": e["from"],
                "subject": e["subject"],
                "snippet": e.get("body", "")[:100],
                "date": e["date"],
                "read": e.get("read", False),
            }
            for e in filtered[:limit]
        ]
