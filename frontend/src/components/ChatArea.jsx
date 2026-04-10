import MessageBubble from "./MessageBubble";
import "./ChatArea.css";

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
          <div className="chat-empty__icon">O</div>
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
