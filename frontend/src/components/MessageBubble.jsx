import { useState } from "react";
import "./MessageBubble.css";

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

function ResultSummary({ results }) {
  if (!results || results.length === 0) return null;

  const hasErrors = results.some((r) => !r.ok && r.status !== "retried");
  if (hasErrors) {
    const errors = results.filter((r) => !r.ok).map((r) => r.error || "Unknown error");
    return (
      <div className="result-errors">
        {errors.map((err, i) => (
          <p key={i} className="result-errors__text">{err}</p>
        ))}
      </div>
    );
  }
  return null;
}

export default function MessageBubble({ message }) {
  const isUser = message.role === "user";

  return (
    <div className={`bubble ${isUser ? "bubble--user" : "bubble--assistant"}`}>
      {isUser ? (
        <p className="bubble__text">{message.content}</p>
      ) : (
        <div className="bubble__results">
          {message.reply && (
            <p className="bubble__reply">{message.reply}</p>
          )}
          <ResultSummary results={message.content} />
          {((message.plan && message.plan.length > 0) || (message.log && message.log.length > 0)) && (
            <DetailToggle label="Details">
              {message.plan && message.plan.length > 0 && (
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
              {message.log && message.log.length > 0 && (
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
      )}
    </div>
  );
}
