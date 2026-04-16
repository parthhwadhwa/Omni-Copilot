import { useState } from "react";
import ReactMarkdown from "react-markdown";
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
          <div key={li} className="result-cards">
            <div className="result-cards__header">{list.length} result{list.length !== 1 ? "s" : ""}</div>
            {visible.map((item, i) => {
              if (typeof item !== "object") {
                return <div key={i} className="result-card result-card--simple">{String(item)}</div>;
              }
              const label = labelKey ? item[labelKey] : Object.values(item)[0];
              const secondary = secondKey ? item[secondKey] : null;
              const secondaryFormatted = secondary ? formatVal(secondKey, secondary) : null;
              const link = item.url || item.link || item.html_url;
              // For emails, show sender below subject
              const sender = isEmail ? (item.from || "").replace(/<[^>]+>/, "").trim() : null;
              return (
                <div key={i} className="result-card">
                  <div className="result-card__main">
                    <span className="result-card__label">
                      {link ? <a href={link} target="_blank" rel="noreferrer">{label}</a> : label}
                    </span>
                    {sender && <span className="result-card__sender">{sender}</span>}
                  </div>
                  {secondaryFormatted && !secondaryFormatted.startsWith("Invalid") && (
                    <span className="result-card__secondary">{secondaryFormatted}</span>
                  )}
                </div>
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
          </div>
        );
      })}
    </>
  );
}

function hasListResults(results) {
  return results?.some((r) => r.ok && Array.isArray(r.result) && r.result.length > 0);
}

function formatTime(ts) {
  if (!ts) return "";
  return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// ── Main bubble ─────────────────────────────────────────────────────────────
export default function MessageBubble({ message }) {
  const isUser = message.role === "user";

  return (
    <div className={`bubble ${isUser ? "bubble--user" : "bubble--assistant"}`}>
      {isUser ? (
        <div className="bubble__user-wrap">
          <p className="bubble__text">{message.content}</p>
          {message.ts && <span className="bubble__ts">{formatTime(message.ts)}</span>}
        </div>
      ) : (
        <div className="bubble__results">
          {message.reply && !hasListResults(message.content) && (
            <div className="bubble__reply">
              <ReactMarkdown>{message.reply}</ReactMarkdown>
            </div>
          )}

          <ResultCards results={message.content || []} />

          {message.content?.some((r) => !r.ok) && (
            <div className="result-errors">
              {message.content.filter((r) => !r.ok).map((r, i) => (
                <p key={i} className="result-errors__text">{r.error || "Unknown error"}</p>
              ))}
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
    </div>
  );
}
