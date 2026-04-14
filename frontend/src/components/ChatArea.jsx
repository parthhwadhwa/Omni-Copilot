import MessageBubble from "./MessageBubble";
import "./ChatArea.css";

const OmniLogo = () => (
  <svg width="56" height="56" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect width="32" height="32" rx="8" fill="url(#chat-omni-grad)"/>
    <defs>
      <linearGradient id="chat-omni-grad" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#6366F1"/>
        <stop offset="100%" stopColor="#8B5CF6"/>
      </linearGradient>
    </defs>
    <circle cx="16" cy="16" r="10" stroke="white" strokeWidth="1.5" strokeOpacity="0.4" fill="none"/>
    <circle cx="16" cy="16" r="6" stroke="white" strokeWidth="1.5" strokeOpacity="0.7" fill="none"/>
    <circle cx="16" cy="16" r="2.5" fill="white"/>
    <line x1="16" y1="6" x2="16" y2="10" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeOpacity="0.9"/>
    <line x1="16" y1="22" x2="16" y2="26" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeOpacity="0.9"/>
    <line x1="6" y1="16" x2="10" y2="16" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeOpacity="0.9"/>
    <line x1="22" y1="16" x2="26" y2="16" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeOpacity="0.9"/>
  </svg>
);

const SUGGESTIONS = [
  "Check my inbox",
  "Schedule a meeting at 3pm",
  "Prepare a meeting with alice@acme.com",
  "Search for roadmap",
  "Send a Slack to #engineering",
  "/summarize project updates",
  "Show my calendar",
  "Schedule meeting and send email",
];

export default function ChatArea({ messages, loading, scrollRef, onChipClick }) {
  return (
    <div className="chat-area" ref={scrollRef}>
      {messages.length === 0 ? (
        <div className="chat-empty">
          <div className="chat-empty__icon"><OmniLogo /></div>
          <h1 className="chat-empty__title">Omni Copilot</h1>
          <p className="chat-empty__subtitle">
            Multi-agent workspace assistant with planning, memory, and
            cross-service search. Type naturally or use slash commands.
          </p>
          <div className="chat-empty__suggestions">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                className="chat-empty__chip"
                onClick={() => onChipClick?.(s)}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="chat-messages">
          {messages.map((msg, i) => (
            <MessageBubble key={i} message={msg} />
          ))}
          {loading && (
            <div className="chat-typing">
              <div className="chat-typing__dot" />
              <div className="chat-typing__dot" />
              <div className="chat-typing__dot" />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
