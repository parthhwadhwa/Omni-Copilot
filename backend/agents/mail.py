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


def _strip_html(html: str) -> str:
    """Quick HTML → text without external deps."""
    import re
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.I | re.S)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p>", "\n\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    import html as _h
    s = _h.unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


_FOOTER_MARKERS = [
    "unsubscribe",
    "manage your preferences",
    "manage preferences",
    "you are receiving this",
    "you received this email",
    "this email was sent to",
    "to stop receiving",
    "update your email preferences",
    "click here to unsubscribe",
]


def _trim_footer(text: str) -> str:
    """Remove unsubscribe/marketing footer from plain-text email body."""
    if not text:
        return text
    lower = text.lower()
    cut = len(text)
    for marker in _FOOTER_MARKERS:
        idx = lower.find(marker)
        if idx != -1 and idx < cut:
            # Walk back to the start of that line
            line_start = text.rfind("\n", 0, idx) + 1
            if line_start < cut:
                cut = line_start
    return text[:cut].rstrip()


def _get_body(msg) -> tuple[str, str]:
    """Return (plain_text, html) for an email message."""
    plain = ""
    html = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "").lower()
            if "attachment" in disp:
                continue
            try:
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            except Exception:
                continue
            if ctype == "text/plain" and not plain:
                plain = text
            elif ctype == "text/html" and not html:
                html = text
    else:
        try:
            payload = msg.get_payload(decode=True)
            text = payload.decode(msg.get_content_charset() or "utf-8", errors="replace") if payload else ""
            if msg.get_content_type() == "text/html":
                html = text
            else:
                plain = text
        except Exception:
            pass

    if not plain.strip() and html.strip():
        plain = _strip_html(html)
    return _trim_footer(plain), html


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
                    "html": {"type": "string"},
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

    def action_send(self, to: str, subject: str, body: str,
                     html: str = "", **_kwargs) -> dict:
        from config import EMAIL_USER, EMAIL_PASS, SENDER_NAME

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
                msg = MIMEMultipart("alternative") if html else MIMEMultipart("mixed")
                from_header = f"{SENDER_NAME} <{EMAIL_USER}>" if SENDER_NAME else EMAIL_USER
                msg["From"] = from_header
                msg["To"] = to
                msg["Subject"] = subject

                msg.attach(MIMEText(body, "plain", "utf-8"))
                if html:
                    msg.attach(MIMEText(html, "html", "utf-8"))

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
                    body, html = _get_body(msg)
                    result.append({
                        "id": uid.decode(),
                        "from": from_addr,
                        "subject": subject,
                        "snippet": body[:160].strip(),
                        "body": body[:8000].strip(),
                        "html": html[:50000] if html else "",
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
