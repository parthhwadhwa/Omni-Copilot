import MessageBubble from "./MessageBubble";
import { motion, AnimatePresence } from "motion/react";
import "./ChatArea.css";

const SERVICES = ["Gmail", "Calendar", "Meet", "Drive", "Docs", "Slack", "GitHub", "Notion"];

const SUGGESTIONS = [
  "Read my inbox",
  "List upcoming calendar events",
  "Schedule a meeting tomorrow at 4pm with someone@gmail.com and email them the invite",
  "Create a Google Doc called Sprint Notes and share it on Slack",
  "List my GitHub repos",
  "Send a message to #general saying hello from OmniCopilot",
];

const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.07, delayChildren: 0.15 } },
};
const fadeUp = {
  hidden: { opacity: 0, y: 18 },
  show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 320, damping: 26 } },
};

export default function ChatArea({ messages, loading, scrollRef, onChipClick, onRetry }) {
  return (
    <div className="chat-area" ref={scrollRef}>
      <AnimatePresence mode="wait">
        {messages.length === 0 ? (
          <motion.div
            key="empty"
            className="chat-empty"
            variants={container}
            initial="hidden"
            animate="show"
            exit={{ opacity: 0, scale: 0.97, transition: { duration: 0.15 } }}
          >
            <motion.div className="chat-empty__wordmark" variants={fadeUp}>
              <span className="chat-empty__wordmark-omni">Omni</span>
              <span className="chat-empty__wordmark-copilot">Copilot</span>
            </motion.div>

            <motion.p className="chat-empty__tagline" variants={fadeUp}>
              One prompt. Multiple agents. Real results.
            </motion.p>

            <motion.div className="chat-empty__services" variants={fadeUp}>
              {SERVICES.map((name, i) => (
                <span key={name} className="chat-empty__service-item">
                  {i > 0 && <span className="chat-empty__service-dot" />}
                  {name}
                </span>
              ))}
            </motion.div>

            <motion.p className="chat-empty__try" variants={fadeUp}>Try asking</motion.p>

            <motion.div className="chat-empty__suggestions" variants={container}>
              {SUGGESTIONS.map((text) => (
                <motion.button
                  key={text}
                  className="chat-empty__chip"
                  onClick={() => onChipClick?.(text)}
                  disabled={loading}
                  variants={fadeUp}
                  whileHover={{ scale: 1.02, y: -1 }}
                  whileTap={{ scale: 0.97 }}
                >
                  <span className="chat-empty__chip-text">{text}</span>
                  <svg className="chat-empty__chip-arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M5 12h14M12 5l7 7-7 7" />
                  </svg>
                </motion.button>
              ))}
            </motion.div>
          </motion.div>
        ) : (
          <motion.div
            key="messages"
            className="chat-messages"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.2 }}
          >
            {messages.map((msg, i) => (
              <MessageBubble key={i} message={msg} onRetry={onRetry} />
            ))}
            {loading && (
              <motion.div
                className="chat-typing"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
              >
                <div className="chat-typing__dot" />
                <div className="chat-typing__dot" />
                <div className="chat-typing__dot" />
              </motion.div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
