import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { motion, AnimatePresence } from "motion/react";
import "./MessageBubble.css";

// ── Copy button ────────────────────────────────────────────────────────────
function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <button className="copy-btn" onClick={copy} title="Copy">
      {copied ? (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20 6 9 17l-5-5" />
        </svg>
      ) : (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
          <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
        </svg>
      )}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

// ── Collapsible detail toggle ───────────────────────────────────────────────
function DetailToggle({ label, children }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="detail-toggle">
      <button className="detail-toggle__btn" onClick={() => setOpen(!open)}>
        <svg
          width="12" height="12" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="2" strokeLinecap="round"
          style={{ transform: open ? "rotate(90deg)" : "none", transition: "transform 150ms" }}
        >
          <path d="m9 18 6-6-6-6" />
        </svg>
        {label}
      </button>
      {open && <div className="detail-toggle__body">{children}</div>}
    </div>
  );
}

// ── HTML email renderer (sandboxed iframe — blocks JS, allows images) ──────
function EmailHtml({ html }) {
  const ref = useRef(null);
  useEffect(() => {
    const iframe = ref.current;
    if (!iframe) return;
    const doc = iframe.contentDocument;
    if (!doc) return;
    const rootStyles = getComputedStyle(document.documentElement);
    const textColor = rootStyles.getPropertyValue("--text-primary").trim() || "#202124";
    const linkColor = rootStyles.getPropertyValue("--accent").trim() || "#1a73e8";
    const bgColor = rootStyles.getPropertyValue("--surface").trim() || "#ffffff";
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";

    // Strip scripts; strip inline color/bgcolor attrs so dark mode stays readable
    let cleaned = html.replace(/<script[\s\S]*?<\/script>/gi, "");
    if (isDark) {
      cleaned = cleaned
        .replace(/\scolor\s*=\s*"[^"]*"/gi, "")
        .replace(/\sbgcolor\s*=\s*"[^"]*"/gi, "")
        .replace(/(background(?:-color)?\s*:\s*)[^;"']+/gi, "$1transparent")
        .replace(/(color\s*:\s*)(?!inherit|transparent)[^;"']+/gi, `$1${textColor}`);
    }
    doc.open();
    doc.write(`<!DOCTYPE html><html><head><base target="_blank"><style>
      html, body { background: ${bgColor} !important; }
      body { font-family: -apple-system, Segoe UI, sans-serif; font-size: 13px; color: ${textColor}; margin: 0; padding: 6px 8px; word-wrap: break-word; }
      body * { color: ${textColor} !important; background-color: transparent !important; }
      body a, body a * { color: ${linkColor} !important; }
      body img { max-width: 100% !important; height: auto !important; filter: ${isDark ? "brightness(0.92)" : "none"}; }
      body table { max-width: 100% !important; }
    </style></head><body>${cleaned}</body></html>`);
    doc.close();
    // Auto-size iframe to content height (capped)
    const resize = () => {
      try {
        const h = Math.min(doc.body.scrollHeight + 8, 520);
        iframe.style.height = `${h}px`;
      } catch {}
    };
    resize();
    const t = setTimeout(resize, 300);
    return () => clearTimeout(t);
  }, [html]);
  return (
    <iframe
      ref={ref}
      sandbox="allow-same-origin allow-popups"
      title="email body"
      className="email-iframe"
    />
  );
}

// ── Structured result cards ─────────────────────────────────────────────────
const LABEL_KEYS = ["title", "name", "subject", "from", "path", "full_name"];
const SECONDARY_KEYS = ["start", "date", "snippet", "url", "link", "description", "body"];

function formatVal(key, val) {
  if (!val) return "";
  const s = String(val);

  // ISO datetime: 2026-04-15T10:00:00 — must match YYYY-MM-DDTHH exactly
  if ((key === "start" || key === "date") && /^\d{4}-\d{2}-\d{2}T/.test(s)) {
    const [d, t] = s.split("T");
    try {
      const time = new Date(`1970-01-01T${t}`).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      return `${d} · ${time}`;
    } catch { return s; }
  }

  // RFC 2822 / email date: "Tue, 14 Apr 2026 08:54:46 -0700 (PDT)"
  if (key === "date") {
    const cleaned = s.replace(/\s*\([^)]*\)\s*$/, "").trim();
    const d = new Date(cleaned);
    if (!isNaN(d.getTime())) {
      return d.toLocaleDateString([], { month: "short", day: "numeric" }) +
        " · " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }
    // Try extracting date parts manually: "Thu, 16 Apr 2026 02:32:12 -0700"
    const m = cleaned.match(/(\d{1,2})\s+(\w{3})\s+(\d{4})\s+(\d{2}):(\d{2})/);
    if (m) {
      return `${m[2]} ${m[1]} · ${m[4]}:${m[5]}`;
    }
  }

  // Truncate long strings
  return s.length > 60 ? s.slice(0, 57) + "…" : s;
}

function ResultCards({ results }) {
  const [expanded, setExpanded] = useState({});
  const [openItem, setOpenItem] = useState({});

  const lists = results
    .filter((r) => r.ok && Array.isArray(r.result) && r.result.length > 0)
    .map((r) => r.result);

  if (lists.length === 0) return null;

  return (
    <>
      {lists.map((list, li) => {
        const first = typeof list[0] === "object" ? list[0] : {};
        const labelKey = LABEL_KEYS.find((k) => first[k]);
        const isEmail = !!(first.from && first.subject);
        const secondKey = isEmail ? "date" : SECONDARY_KEYS.find((k) => {
          if (!first[k] || k === labelKey) return false;
          const formatted = formatVal(k, first[k]);
          return formatted && !formatted.startsWith("Invalid");
        });

        const showAll = expanded[li];
        const visible = showAll ? list : list.slice(0, 8);
        const extra = list.length - 8;

        return (
          <motion.div
            key={li}
            className="result-cards"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, ease: "easeOut" }}
          >
            <div className="result-cards__header">{list.length} result{list.length !== 1 ? "s" : ""}</div>
            {visible.map((item, i) => {
              if (typeof item !== "object") {
                return <div key={i} className="result-card result-card--simple">{String(item)}</div>;
              }
              const label = labelKey ? item[labelKey] : Object.values(item)[0];
              const secondary = secondKey ? item[secondKey] : null;
              const secondaryFormatted = secondary ? formatVal(secondKey, secondary) : null;
              const link = item.url || item.link || item.html_url;
              const sender = isEmail ? (item.from || "").replace(/\s*<[^>]+>\s*$/, "").trim() : null;
              const key = `${li}-${i}`;
              const isOpen = !!openItem[key];
              const canOpen = isEmail && (item.body || item.snippet);
              const fullBody = item.body || item.snippet || "";

              return (
                <motion.div
                  key={i}
                  className={`result-card ${canOpen ? "result-card--clickable" : ""} ${isOpen ? "result-card--open" : ""}`}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.18, delay: i * 0.04, ease: "easeOut" }}
                >
                  <div
                    className="result-card__row"
                    onClick={canOpen ? () => setOpenItem((p) => ({ ...p, [key]: !p[key] })) : undefined}
                    role={canOpen ? "button" : undefined}
                  >
                    <div className="result-card__main">
                      <span className="result-card__label">
                        {link ? <a href={link} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>{label}</a> : label}
                      </span>
                      {sender && <span className="result-card__sender">{sender}</span>}
                    </div>
                    {secondaryFormatted && !secondaryFormatted.startsWith("Invalid") && (
                      <span className="result-card__secondary">{secondaryFormatted}</span>
                    )}
                  </div>
                  {canOpen && isOpen && (
                    <div className="result-card__body">
                      {isEmail && (
                        <div className="result-card__body-meta">
                          <div><span>From:</span> {item.from || "—"}</div>
                          {item.date && <div><span>Date:</span> {item.date}</div>}
                        </div>
                      )}
                      {isEmail && item.html ? (
                        <EmailHtml html={item.html} />
                      ) : (
                        <pre className="result-card__body-text">{fullBody}</pre>
                      )}
                    </div>
                  )}
                </motion.div>
              );
            })}
            {extra > 0 && (
              <button
                className="result-card result-card--more"
                onClick={() => setExpanded((p) => ({ ...p, [li]: !p[li] }))}
              >
                {showAll ? "Show less" : `+${extra} more`}
              </button>
            )}
          </motion.div>
        );
      })}
    </>
  );
}

function hasListResults(results) {
  return results?.some((r) => r.ok && Array.isArray(r.result) && r.result.length > 0);
}

// ── Action buttons: extract every URL/link from results ────────────────────
const LINK_KEYS = ["link", "url", "html_url", "calendar_link", "join_url", "web_url", "permalink"];

const BRAND = {
  meet: {
    label: "Join Google Meet", sub: "meet.google.com",
    color: "#00897B", bg: "linear-gradient(135deg, #00897B 0%, #00BFA5 100%)",
    icon: (<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M16.5 8.5H9a.5.5 0 0 0-.5.5v5.5l2-1.5v-3h4.5v4H11l-2 1.5H16.5a.5.5 0 0 0 .5-.5V9a.5.5 0 0 0-.5-.5z"/><path d="M17 10.5l3-2v7l-3-2v-3z"/></svg>),
  },
  zoom: {
    label: "Join Zoom", sub: "zoom.us",
    color: "#2D8CFF", bg: "linear-gradient(135deg, #2D8CFF 0%, #0B5CFF 100%)",
    icon: (<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M3 7v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3l4 3V7l-4 3V7a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2z"/></svg>),
  },
  docs: {
    label: "Open Google Doc", sub: "docs.google.com",
    color: "#4285F4", bg: "linear-gradient(135deg, #4285F4 0%, #1A6FD4 100%)",
    icon: (<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M14 0H4a2 2 0 0 0-2 2v20a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8z"/><rect x="6" y="11" width="12" height="1.5" rx=".75" fill="white" opacity=".9"/><rect x="6" y="14" width="12" height="1.5" rx=".75" fill="white" opacity=".9"/><rect x="6" y="17" width="8" height="1.5" rx=".75" fill="white" opacity=".9"/></svg>),
  },
  forms: {
    label: "Open Google Form", sub: "forms.google.com",
    color: "#673AB7", bg: "linear-gradient(135deg, #673AB7 0%, #512DA8 100%)",
    icon: (<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M14 0H4a2 2 0 0 0-2 2v20a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8z"/><rect x="6" y="11" width="12" height="1.5" rx=".75" fill="white" opacity=".9"/><rect x="6" y="14" width="12" height="1.5" rx=".75" fill="white" opacity=".9"/><rect x="6" y="17" width="8" height="1.5" rx=".75" fill="white" opacity=".9"/><circle cx="7" cy="8.5" r="1.5" fill="white" opacity=".9"/></svg>),
  },
  drive: {
    label: "Open in Drive", sub: "drive.google.com",
    color: "#0F9D58", bg: "linear-gradient(135deg, #0F9D58 0%, #4285F4 100%)",
    icon: (<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M4.4 22.4 6.4 19H22l-2 3.4z" opacity=".85"/><path d="M2 19 8 8.3l3.5 6.1L5.5 24.8z" opacity=".7"/><path d="M13 .6 22 17H4z"/></svg>),
  },
  calendar: {
    label: "View in Calendar", sub: "calendar.google.com",
    color: "#EA4335", bg: "linear-gradient(135deg, #4285F4 0%, #EA4335 100%)",
    icon: (<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M18 0H6L5 1v1H3a3 3 0 0 0-3 3v16a3 3 0 0 0 3 3h18a3 3 0 0 0 3-3V5a3 3 0 0 0-3-3h-2V1zM3 4h2v2h14V4h2a1 1 0 0 1 1 1v3H2V5a1 1 0 0 1 1-1zm0 6h18v11a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1z"/></svg>),
  },
  github: {
    label: "Open on GitHub", sub: "github.com",
    color: "#24292f", bg: "linear-gradient(135deg, #24292f 0%, #57606a 100%)",
    icon: (<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12c0 4.42 2.87 8.17 6.84 9.5.5.09.68-.22.68-.48v-1.7c-2.78.6-3.37-1.34-3.37-1.34-.45-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.89 1.52 2.34 1.08 2.91.83.09-.65.35-1.08.63-1.33-2.22-.25-4.56-1.11-4.56-4.94 0-1.09.39-1.98 1.03-2.68-.1-.25-.45-1.27.1-2.64 0 0 .84-.27 2.75 1.02A9.57 9.57 0 0 1 12 6.8c.85 0 1.71.11 2.51.34 1.91-1.29 2.75-1.02 2.75-1.02.55 1.37.2 2.39.1 2.64.64.7 1.03 1.59 1.03 2.68 0 3.84-2.34 4.69-4.57 4.94.36.31.68.92.68 1.85V21c0 .27.18.58.69.48A10 10 0 0 0 22 12c0-5.52-4.48-10-10-10z"/></svg>),
  },
  notion: {
    label: "Open in Notion", sub: "notion.so",
    color: "#000", bg: "linear-gradient(135deg, #2f2f2f 0%, #000 100%)",
    icon: (<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M4.5 4.2c.7.6 1 .6 2.4.5l13.2-.8c.3 0 .05-.3-.05-.33L17.9 2a2.5 2.5 0 0 0-2-.6L3 2.3c-.5.05-.6.3-.4.5zm.8 3v13.9c0 .75.4 1 1.2 1l14.5-.85c.85-.05.9-.55.9-1.17V6.35c0-.6-.2-.95-.75-.9L5.97 6.3c-.55.05-.75.3-.75.9z"/></svg>),
  },
  slack: {
    label: "Open in Slack", sub: "slack.com",
    color: "#611f69", bg: "linear-gradient(135deg, #E01E5A 0%, #ECB22E 50%, #2EB67D 100%)",
    icon: (<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M5 15a2.5 2.5 0 1 1-2.5-2.5H5V15zm1.3 0a2.5 2.5 0 0 1 5 0v6.3a2.5 2.5 0 1 1-5 0V15zm2.5-10.1a2.5 2.5 0 1 1 2.5-2.5v2.5H8.8zm0 1.3a2.5 2.5 0 0 1 0 5H2.5a2.5 2.5 0 1 1 0-5h6.3zm10.1 2.5a2.5 2.5 0 1 1 2.5 2.5H19v-2.5zm-1.3 0a2.5 2.5 0 0 1-5 0V2.4a2.5 2.5 0 0 1 5 0v6.3zm-2.5 10.1a2.5 2.5 0 1 1-2.5 2.5v-2.5h2.5zm0-1.3a2.5 2.5 0 0 1 0-5h6.3a2.5 2.5 0 1 1 0 5H15z"/></svg>),
  },
  discord: {
    label: "Open in Discord", sub: "discord.com",
    color: "#5865F2", bg: "linear-gradient(135deg, #5865F2 0%, #404EED 100%)",
    icon: (<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M20.3 4.4a19.8 19.8 0 0 0-4.9-1.5l-.25.3a14.4 14.4 0 0 0-5.5 0l-.25-.3A19.8 19.8 0 0 0 4.5 4.4C.8 9.6-.2 14.7.3 19.8A20 20 0 0 0 6.3 22c.5-.7.95-1.4 1.3-2.2-.75-.3-1.45-.65-2.1-1 .2-.15.35-.3.5-.4 3.95 1.8 8.2 1.8 12.1 0 .15.15.3.3.5.4-.65.35-1.35.7-2.1 1 .35.8.8 1.5 1.3 2.2a20 20 0 0 0 6-2.2c.5-5.2-.45-10.3-3.5-15.4z"/></svg>),
  },
  generic: {
    label: "Open link", sub: "",
    color: "#0071e3", bg: "linear-gradient(135deg, #0071e3 0%, #2997ff 100%)",
    icon: (<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10 14 21 3"/><path d="M15 3h6v6"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>),
  },
};

function classifyUrl(url, res) {
  if (res?.platform === "google_meet" || url.includes("meet.google.com")) return "meet";
  if (res?.platform === "zoom" || url.includes("zoom.us")) return "zoom";
  if (url.includes("docs.google.com/forms") || url.includes("forms.google.com")) return "forms";
  if (url.includes("docs.google.com")) return "docs";
  if (url.includes("drive.google.com")) return "drive";
  if (url.includes("calendar.google.com")) return "calendar";
  if (url.includes("github.com")) return "github";
  if (url.includes("notion.so") || url.includes("notion.site")) return "notion";
  if (url.includes("slack.com")) return "slack";
  if (url.includes("discord.com") || url.includes("discord.gg")) return "discord";
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return "generic"; }
}

function ActionButtons({ results }) {
  const actions = [];
  const seen = new Set();

  for (const r of results || []) {
    if (!r?.ok) continue;
    const res = r.result;
    if (!res || typeof res !== "object" || Array.isArray(res)) continue;
    for (const key of LINK_KEYS) {
      const val = res[key];
      if (typeof val !== "string" || !val.startsWith("http") || seen.has(val)) continue;
      seen.add(val);
      const kind = classifyUrl(val, res);
      const brand = BRAND[kind] || { ...BRAND.generic, sub: kind };
      actions.push({ ...brand, url: val, title: res.title || res.name || res.subject || "" });
    }
  }

  if (actions.length === 0) return null;
  return (
    <motion.div
      className="action-buttons"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: "easeOut" }}
    >
      {actions.map((a, i) => (
        <motion.a
          key={i}
          className="action-card"
          href={a.url}
          target="_blank"
          rel="noreferrer"
          style={{ background: a.bg }}
          title={a.url}
          initial={{ opacity: 0, scale: 0.94 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.2, delay: i * 0.06, ease: "easeOut" }}
          whileHover={{ scale: 1.02, y: -2 }}
          whileTap={{ scale: 0.97 }}
        >
          <span className="action-card__icon">{a.icon}</span>
          <span className="action-card__text">
            <span className="action-card__label">{a.label}</span>
            <span className="action-card__sub">{a.title || a.sub}</span>
          </span>
          <span className="action-card__arrow">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M7 17 17 7" />
              <path d="M7 7h10v10" />
            </svg>
          </span>
        </motion.a>
      ))}
    </motion.div>
  );
}

function formatTime(ts) {
  if (!ts) return "";
  return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// ── Meeting conflict notice ──────────────────────────────────────────────────
function formatMeetingWhen(start) {
  if (!start || typeof start !== "string") return "";
  if (!/^\d{4}-\d{2}-\d{2}T/.test(start)) return start;
  const [d, t] = start.split("T");
  try {
    const time = new Date(`1970-01-01T${t}`).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    return `${d} · ${time}`;
  } catch { return start; }
}

function ConflictNotice({ existing, proposed, onReplace, disabled }) {
  const [busy, setBusy] = useState(false);
  const replace = () => {
    if (busy || disabled || !existing?.meeting_id) return;
    setBusy(true);
    onReplace?.(`/replace ${existing.meeting_id}`);
  };
  return (
    <motion.div
      className="conflict-notice"
      initial={{ opacity: 0, y: 10, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 380, damping: 28 }}
    >
      <div className="conflict-notice__header">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 8v4" />
          <path d="M12 16h.01" />
        </svg>
        <span>Time already booked</span>
      </div>
      <div className="conflict-notice__body">
        <div className="conflict-notice__row">
          <span className="conflict-notice__tag">Existing</span>
          <div className="conflict-notice__detail">
            <span className="conflict-notice__title">{existing?.title || "Meeting"}</span>
            <span className="conflict-notice__when">{formatMeetingWhen(existing?.start)}</span>
          </div>
        </div>
        <div className="conflict-notice__row">
          <span className="conflict-notice__tag conflict-notice__tag--new">New</span>
          <div className="conflict-notice__detail">
            <span className="conflict-notice__title">{proposed?.title || "Meeting"}</span>
            <span className="conflict-notice__when">{formatMeetingWhen(proposed?.start)}</span>
          </div>
        </div>
      </div>
      <motion.button
        className="conflict-notice__replace"
        onClick={replace}
        disabled={busy || disabled || !existing?.meeting_id}
        whileHover={{ scale: 1.03 }}
        whileTap={{ scale: 0.97 }}
      >
        {busy ? "Replacing…" : "Replace existing meeting"}
      </motion.button>
    </motion.div>
  );
}

function extractConflicts(results) {
  if (!Array.isArray(results)) return [];
  return results
    .filter((r) => r?.ok && r?.result && typeof r.result === "object" && r.result.conflict === true)
    .map((r) => r.result);
}

// ── Live step progress indicator ────────────────────────────────────────────
function StepProgress({ steps, planning }) {
  if (planning && (!steps || steps.length === 0)) {
    return (
      <div className="step-progress">
        <div className="step-progress__planning">
          <span className="step-progress__spinner" />
          Planning…
        </div>
      </div>
    );
  }
  if (!steps?.length) return null;
  const lastIndex = steps.length - 1;
  return (
    <div className="step-progress">
      <AnimatePresence initial={false}>
        {steps.map((s, i) => {
          const isActive = i === lastIndex;
          return (
            <motion.div
              key={i}
              className={`step-progress__item ${isActive ? "" : "step-progress__item--done"}`}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.22, ease: "easeOut" }}
            >
              <span className="step-progress__icon">{s.icon}</span>
              <span className="step-progress__label">{s.label}</span>
              {isActive ? (
                <span className="step-progress__dot" />
              ) : (
                <motion.svg
                  className="step-progress__check"
                  width="14" height="14" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                  initial={{ scale: 0, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ type: "spring", stiffness: 500, damping: 30 }}
                >
                  <path d="M20 6 9 17l-5-5" />
                </motion.svg>
              )}
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}

// ── Typewriter text ──────────────────────────────────────────────────────────
function TypewriterReply({ text }) {
  const [displayed, setDisplayed] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    setDisplayed("");
    setDone(false);
    if (!text) { setDone(true); return; }
    const words = text.split(" ");
    let i = 0;
    const tick = () => {
      i++;
      setDisplayed(words.slice(0, i).join(" "));
      if (i < words.length) {
        setTimeout(tick, 18 + Math.random() * 14);
      } else {
        setDone(true);
      }
    };
    const t = setTimeout(tick, 40);
    return () => clearTimeout(t);
  }, [text]);

  return (
    <div className="bubble__reply">
      <ReactMarkdown>{displayed}</ReactMarkdown>
      {!done && <span className="typewriter-cursor" />}
    </div>
  );
}

// ── Main bubble ─────────────────────────────────────────────────────────────
export default function MessageBubble({ message, onRetry }) {
  const isUser = message.role === "user";
  const isLive = !!(message._planning || message._steps?.length);
  const conflicts = extractConflicts(message.content);

  return (
    <motion.div
      className={`bubble ${isUser ? "bubble--user" : "bubble--assistant"}`}
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 340, damping: 28 }}
    >
      {isUser ? (
        <div className="bubble__user-wrap">
          <p className="bubble__text">{message.content}</p>
          {message.ts && <span className="bubble__ts">{formatTime(message.ts)}</span>}
        </div>
      ) : (
        <div className="bubble__results">
          {isLive && (
            <StepProgress steps={message._steps} planning={message._planning} />
          )}

          {message.reply && !hasListResults(message.content) && (
            message._typewriter
              ? <TypewriterReply text={message.reply} />
              : <div className="bubble__reply"><ReactMarkdown>{message.reply}</ReactMarkdown></div>
          )}

          {conflicts.map((c, i) => (
            <ConflictNotice
              key={`conflict-${i}`}
              existing={c.existing}
              proposed={c.proposed}
              onReplace={onRetry}
            />
          ))}

          <ResultCards results={message.content || []} />

          <ActionButtons results={message.content || []} />

          {message.content?.some((r) => !r.ok) && (
            <div className="result-errors">
              {message.content.filter((r) => !r.ok).map((r, i) => (
                <p key={i} className="result-errors__text">{r.error || "Unknown error"}</p>
              ))}
              {message.retryOf && onRetry && (
                <button className="result-errors__retry" onClick={() => onRetry(message.retryOf)}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
                    <path d="M3 3v5h5" />
                  </svg>
                  Try again
                </button>
              )}
            </div>
          )}

          <div className="bubble__actions">
            {message.ts && <span className="bubble__ts">{formatTime(message.ts)}</span>}
            {message.reply && <CopyButton text={message.reply} />}
            {((message.plan?.length > 0) || (message.log?.length > 0)) && (
              <DetailToggle label="Details">
                {message.plan?.length > 0 && (
                  <div className="detail-section">
                    <span className="detail-section__label">Steps</span>
                    {message.plan.map((s, i) => (
                      <div key={i} className="detail-step">
                        <span className="detail-step__num">{s.step}</span>
                        <span className="detail-step__label">{s.label}</span>
                      </div>
                    ))}
                  </div>
                )}
                {message.log?.length > 0 && (
                  <div className="detail-section">
                    <span className="detail-section__label">Log</span>
                    {message.log.map((entry, i) => (
                      <div key={i} className="detail-log-entry">
                        <span className="detail-log-entry__event">{entry.event}</span>
                        <span className="detail-log-entry__detail">{entry.detail}</span>
                      </div>
                    ))}
                  </div>
                )}
              </DetailToggle>
            )}
          </div>
        </div>
      )}
    </motion.div>
  );
}
