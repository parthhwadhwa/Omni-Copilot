import { useState, useEffect } from "react";
import "./Sidebar.css";

const API = "http://localhost:8000";

const AGENTS = [
  { key: "mail", label: "Gmail", icon: "gmail", query: "Show my inbox" },
  { key: "calendar", label: "Calendar", icon: "gcalendar", query: "Show my calendar" },
  { key: "drive", label: "Drive", icon: "gdrive", query: "List my Drive files" },
  { key: "forms", label: "Forms", icon: "gforms", query: "List my forms" },
  { key: "meeting", label: "Meet", icon: "gmeet", query: "Show my meetings" },
  { key: "docs", label: "Docs", icon: "gdocs", query: "List my docs" },
  { key: "slack", label: "Slack", icon: "slack", query: "Check Slack status" },
  { key: "discord", label: "Discord", icon: "discord", query: "Check Discord status" },
  { key: "notion", label: "Notion", icon: "notion", query: "List my Notion pages" },
  { key: "github", label: "GitHub", icon: "github", query: "List my GitHub repos" },
  { key: "code", label: "Code", icon: "code", query: "List code files in current directory" },
  { key: "file", label: "Files", icon: "files", query: "List my files" },
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
  gmail: (
    <svg width="18" height="18" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path d="M24 5.457v13.909c0 .904-.732 1.636-1.636 1.636h-3.819V11.73L12 16.64l-6.545-4.91v9.273H1.636A1.636 1.636 0 0 1 0 19.366V5.457c0-2.023 2.309-3.178 3.927-1.964L5.455 4.64 12 9.548l6.545-4.91 1.528-1.145C21.69 2.28 24 3.434 24 5.457z" fill="#EA4335"/>
    </svg>
  ),
  gcalendar: (
    <svg width="18" height="18" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path d="M18 0H6L5 1v1H3a3 3 0 0 0-3 3v16a3 3 0 0 0 3 3h18a3 3 0 0 0 3-3V5a3 3 0 0 0-3-3h-2V1zM6 2h1v3H6zm11 0h1v3h-1zM3 4h2v2h14V4h2a1 1 0 0 1 1 1v3H2V5a1 1 0 0 1 1-1zm0 6h18v11a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1zm7 2v6h5v-1h-4v-2h3v-1h-3v-2z" fill="#4285F4"/>
      <rect x="2" y="10" width="20" height="1" fill="#EA4335"/>
    </svg>
  ),
  gdrive: (
    <svg width="18" height="18" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path d="M4.433 22.396l2-3.465H22l-2 3.465z" fill="#FBBC04"/>
      <path d="M1.994 18.931L8 8.348l3.5 6.062-6 10.386z" fill="#0F9D58"/>
      <path d="M12.994.604L22 17.07H4z" fill="#4285F4"/>
      <path d="M8 8.348l4-6.928 4 6.928H8z" fill="#1A73E8" opacity=".3"/>
    </svg>
  ),
  gforms: (
    <svg width="18" height="18" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path d="M14 0H4a2 2 0 0 0-2 2v20a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8z" fill="#673AB7"/>
      <path d="M14 0l6 6h-6z" fill="#512DA8"/>
      <rect x="6" y="11" width="12" height="1.5" rx=".75" fill="white" opacity=".9"/>
      <rect x="6" y="14" width="12" height="1.5" rx=".75" fill="white" opacity=".9"/>
      <rect x="6" y="17" width="8" height="1.5" rx=".75" fill="white" opacity=".9"/>
      <circle cx="7" cy="8.5" r="1.5" fill="white" opacity=".9"/>
    </svg>
  ),
  gmeet: (
    <svg width="18" height="18" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0z" fill="#00897B"/>
      <path d="M16.5 8.5H9a.5.5 0 0 0-.5.5v5.5l2-1.5v-3h4.5v4H11l-2 1.5H16.5a.5.5 0 0 0 .5-.5V9a.5.5 0 0 0-.5-.5z" fill="white"/>
      <path d="M17 10.5l3-2v7l-3-2v-3z" fill="white"/>
    </svg>
  ),
  gdocs: (
    <svg width="18" height="18" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path d="M14 0H4a2 2 0 0 0-2 2v20a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8z" fill="#4285F4"/>
      <path d="M14 0l6 6h-6z" fill="#1A6FD4"/>
      <rect x="6" y="11" width="12" height="1.5" rx=".75" fill="white" opacity=".9"/>
      <rect x="6" y="14" width="12" height="1.5" rx=".75" fill="white" opacity=".9"/>
      <rect x="6" y="17" width="8" height="1.5" rx=".75" fill="white" opacity=".9"/>
    </svg>
  ),
  slack: (
    <svg width="18" height="18" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52z" fill="#E01E5A"/>
      <path d="M6.313 15.165a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313z" fill="#E01E5A"/>
      <path d="M8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834z" fill="#36C5F0"/>
      <path d="M8.834 6.313a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312z" fill="#36C5F0"/>
      <path d="M18.956 8.834a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.522V8.834z" fill="#2EB67D"/>
      <path d="M17.688 8.834a2.528 2.528 0 0 1-2.523 2.521 2.527 2.527 0 0 1-2.52-2.521V2.522A2.527 2.527 0 0 1 15.165 0a2.528 2.528 0 0 1 2.523 2.522v6.312z" fill="#2EB67D"/>
      <path d="M15.165 18.956a2.528 2.528 0 0 1 2.523 2.522A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.52-2.522v-2.522h2.52z" fill="#ECB22E"/>
      <path d="M15.165 17.688a2.527 2.527 0 0 1-2.52-2.523 2.526 2.526 0 0 1 2.52-2.52h6.313A2.527 2.527 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.523h-6.313z" fill="#ECB22E"/>
    </svg>
  ),
  discord: (
    <svg width="18" height="18" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057c.002.022.015.043.032.055a19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03z" fill="#5865F2"/>
    </svg>
  ),
  notion: (
    <svg width="18" height="18" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path d="M4.459 4.208c.746.606 1.026.56 2.428.466l13.215-.793c.28 0 .047-.28-.046-.326L17.86 1.968c-.42-.326-.981-.7-2.055-.607L3.01 2.295c-.466.046-.56.28-.374.466zm.793 3.08v13.904c0 .747.373 1.027 1.214.98l14.523-.84c.841-.046.935-.56.935-1.167V6.354c0-.606-.233-.933-.748-.887l-15.177.887c-.56.047-.747.327-.747.933zm14.337.745c.093.42 0 .84-.42.888l-.7.14v10.264c-.608.327-1.168.514-1.635.514-.748 0-.935-.234-1.495-.933l-4.577-7.186v6.952L12.21 19s0 .84-1.168.84l-3.222.186c-.093-.186 0-.653.327-.746l.84-.233V9.854L7.822 9.76c-.094-.42.14-1.026.793-1.073l3.456-.233 4.764 7.279v-6.44l-1.215-.14c-.093-.514.28-.887.747-.933zM1.936 1.035l13.31-.98c1.634-.14 2.055-.047 3.082.7l4.249 2.986c.7.513.934.653.934 1.213v16.378c0 1.026-.373 1.634-1.68 1.726l-15.458.934c-.98.047-1.448-.093-1.962-.747l-3.129-4.06c-.56-.747-.793-1.306-.793-1.96V2.667c0-.839.374-1.54 1.447-1.632z" fill="#000"/>
    </svg>
  ),
  github: (
    <svg width="18" height="18" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844a9.59 9.59 0 0 1 2.504.337c1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.02 10.02 0 0 0 22 12.017C22 6.484 17.522 2 12 2z" fill="currentColor"/>
    </svg>
  ),
  code: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="16 18 22 12 16 6" />
      <polyline points="8 6 2 12 8 18" />
    </svg>
  ),
  files: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
    </svg>
  ),
  search: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.35-4.35" />
    </svg>
  ),
};

// OmniCopilot Logo SVG
const OmniLogo = () => (
  <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect width="32" height="32" rx="8" fill="url(#omni-grad)"/>
    <defs>
      <linearGradient id="omni-grad" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#6366F1"/>
        <stop offset="100%" stopColor="#8B5CF6"/>
      </linearGradient>
    </defs>
    {/* Outer ring */}
    <circle cx="16" cy="16" r="10" stroke="white" strokeWidth="1.5" strokeOpacity="0.4" fill="none"/>
    {/* Inner ring */}
    <circle cx="16" cy="16" r="6" stroke="white" strokeWidth="1.5" strokeOpacity="0.7" fill="none"/>
    {/* Center dot */}
    <circle cx="16" cy="16" r="2.5" fill="white"/>
    {/* Four connector lines */}
    <line x1="16" y1="6" x2="16" y2="10" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeOpacity="0.9"/>
    <line x1="16" y1="22" x2="16" y2="26" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeOpacity="0.9"/>
    <line x1="6" y1="16" x2="10" y2="16" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeOpacity="0.9"/>
    <line x1="22" y1="16" x2="26" y2="16" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeOpacity="0.9"/>
  </svg>
);

const STATUS_AGENTS = [
  "mail", "calendar", "drive", "forms", "meeting", "docs",
  "slack", "discord", "notion", "github", "code", "file",
];

function useAgentStatus() {
  const [status, setStatus] = useState({});
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    fetch(`${API}/status`)
      .then((r) => r.json())
      .then((d) => setStatus(d.agents || {}))
      .catch(() => setStatus({}));
  }, [open]);

  return { status, open, setOpen };
}

export default function Sidebar({ open, onToggle, onClear, autoMode, onAutoModeToggle, onSend, theme, onThemeToggle }) {
  const agentStatus = useAgentStatus();

  return (
    <>
      <aside className={`sidebar ${open ? "sidebar--open" : ""}`}>
        <div className="sidebar__header">
          <div className="sidebar__brand">
            <div className="sidebar__logo">
              <OmniLogo />
            </div>
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

        <button
          className="sidebar__section-label sidebar__status-toggle"
          onClick={() => agentStatus.setOpen(!agentStatus.open)}
        >
          Agent Status
          <span className={`sidebar__status-arrow ${agentStatus.open ? "sidebar__status-arrow--open" : ""}`}>▾</span>
        </button>
        {agentStatus.open && (
          <div className="sidebar__status-grid">
            {STATUS_AGENTS.map((key) => {
              const connected = agentStatus.status[key];
              return (
                <div key={key} className="sidebar__status-item">
                  <span className={`sidebar__status-dot ${connected ? "sidebar__status-dot--on" : "sidebar__status-dot--off"}`} />
                  <span className="sidebar__status-name">{key}</span>
                </div>
              );
            })}
          </div>
        )}

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
