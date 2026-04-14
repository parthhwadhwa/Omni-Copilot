from .mail import MailAgent
from .calendar import CalendarAgent
from .docs import DocsAgent
from .slack import SlackAgent
from .discord import DiscordAgent
from .notion import NotionAgent
from .meeting import MeetingAgent
from .file import FileAgent
from .forms import FormsAgent
from .drive import DriveAgent
from .github import GitHubAgent
from .code import CodeAgent

ALL_AGENTS = {
    "mail": MailAgent,
    "calendar": CalendarAgent,
    "docs": DocsAgent,
    "slack": SlackAgent,
    "discord": DiscordAgent,
    "notion": NotionAgent,
    "meeting": MeetingAgent,
    "file": FileAgent,
    "forms": FormsAgent,
    "drive": DriveAgent,
    "github": GitHubAgent,
    "code": CodeAgent,
}
