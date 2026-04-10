import "./Sidebar.css";

const AGENTS = [
  { key: "mail", label: "Mail", icon: "envelope", query: "Show my inbox" },
  { key: "calendar", label: "Calendar", icon: "calendar", query: "Show my calendar" },
  { key: "docs", label: "Docs & Drive", icon: "doc", query: "List my docs" },
  { key: "slack", label: "Slack", icon: "message", query: "Check Slack status" },
  { key: "discord", label: "Discord", icon: "discord", query: "Check Discord status" },
  { key: "notion", label: "Notion", icon: "note", query: "List my Notion pages" },
  { key: "meeting", label: "Meetings", icon: "video", query: "Show my meetings" },
  { key: "file", label: "Files", icon: "folder", query: "List my files" },
  { key: "forms", label: "Forms", icon: "list", query: "List my forms" },
  { key: "search", label: "Search", icon: "search", query: "Search everything" },
];

const COMMANDS = [
  { cmd: "/schedule", desc: "Schedule meeting" },
  { cmd: "/email", desc: "Send email" },
  { cmd: "/summarize", desc: "Search & summarize" },
  { cmd: "/inbox", desc: "Check inbox" },
  { cmd: "/calendar", desc: "List events" },
  { cmd: "/meet", desc: "Meet + invite" },
];

const ICONS = {
  envelope: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="4" width="20" height="16" rx="3" />
      <path d="m2 7 10 6 10-6" />
    </svg>
  ),
  calendar: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="18" rx="3" />
      <path d="M3 10h18M8 2v4M16 2v4" />
    </svg>
  ),
  doc: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
      <path d="M14 2v6h6M8 13h8M8 17h8M8 9h2" />
    </svg>
  ),
  message: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  ),
  note: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 4h16v16H4z" />
      <path d="M9 4v16M4 9h16" />
    </svg>
  ),
  video: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="6" width="14" height="12" rx="2" />
      <path d="m16 9 6-3v12l-6-3" />
    </svg>
  ),
  folder: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
    </svg>
  ),
  list: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 5h11M9 12h11M9 19h11M4 5h.01M4 12h.01M4 19h.01" />
    </svg>
  ),
  search: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.35-4.35" />
    </svg>
  ),
  discord: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
      <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057c.002.022.015.043.032.055a19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
    </svg>
  ),
};

export default function Sidebar({ open, onToggle, onClear, autoMode, onAutoModeToggle, onSend, theme, onThemeToggle }) {
  return (
    <>
      <aside className={`sidebar ${open ? "sidebar--open" : ""}`}>
        <div className="sidebar__header">
          <div className="sidebar__brand">
            <div className="sidebar__logo">O</div>
            <span className="sidebar__title">Omni Copilot</span>
          </div>
        </div>

        <button className="sidebar__new-chat" onClick={onClear}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M12 5v14M5 12h14" />
          </svg>
          New Chat
        </button>

        <div className="sidebar__section-label">Agents</div>
        <nav className="sidebar__agents">
          {AGENTS.map((a) => (
            <button
              key={a.key}
              className="sidebar__agent"
              onClick={() => onSend?.(a.query)}
            >
              <span className="sidebar__agent-icon">{ICONS[a.icon]}</span>
              <span className="sidebar__agent-label">{a.label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar__section-label">Quick Commands</div>
        <nav className="sidebar__commands">
          {COMMANDS.map((c) => (
            <button
              key={c.cmd}
              className="sidebar__command"
              onClick={() => onSend?.(c.cmd)}
            >
              <span className="sidebar__command-key">{c.cmd}</span>
              <span className="sidebar__command-desc">{c.desc}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar__footer">
          <button
            className={`sidebar__auto-toggle ${autoMode ? "sidebar__auto-toggle--on" : ""}`}
            onClick={onAutoModeToggle}
          >
            <span className="sidebar__auto-dot" />
            Auto Mode {autoMode ? "On" : "Off"}
          </button>
          <button className="sidebar__theme-toggle" onClick={onThemeToggle} aria-label="Toggle theme">
            {theme === "light" ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="5" />
                <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
              </svg>
            )}
          </button>
          <span className="sidebar__version">v0.2</span>
        </div>
      </aside>

      <button className={`sidebar-toggle ${open ? "" : "sidebar-toggle--closed"}`} onClick={onToggle} aria-label="Toggle sidebar">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
          <rect x="3" y="3" width="18" height="18" rx="3" />
          <path d="M9 3v18" />
        </svg>
      </button>
    </>
  );
}
