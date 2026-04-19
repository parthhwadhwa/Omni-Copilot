import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import "./InputBar.css";

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

const PLACEHOLDERS = [
  "Schedule a meeting tomorrow at 3pm and email the invite…",
  "Read my inbox and summarize unread emails…",
  "Create a Google Doc and share it on Slack…",
  "List my GitHub repos and open issues…",
  "Post a message to #general on Slack…",
  "Search across my workspace…",
];

const letterVariants = {
  initial: { opacity: 0, filter: "blur(8px)", y: 6 },
  animate: {
    opacity: 1, filter: "blur(0px)", y: 0,
    transition: { opacity: { duration: 0.2 }, filter: { duration: 0.3 }, y: { type: "spring", stiffness: 100, damping: 20 } },
  },
  exit: {
    opacity: 0, filter: "blur(8px)", y: -6,
    transition: { opacity: { duration: 0.15 }, filter: { duration: 0.2 } },
  },
};

const containerVariants = {
  initial: {},
  animate: { transition: { staggerChildren: 0.022 } },
  exit:    { transition: { staggerChildren: 0.012, staggerDirection: -1 } },
};

export default function InputBar({ onSend, onStop, loading }) {
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const [focused, setFocused] = useState(false);
  const [placeholderIdx, setPlaceholderIdx] = useState(0);
  const [showPlaceholder, setShowPlaceholder] = useState(true);
  const inputRef = useRef(null);
  const recogRef = useRef(null);
  const onSendRef = useRef(onSend);
  useEffect(() => { onSendRef.current = onSend; }, [onSend]);

  // Cycle placeholder when idle
  useEffect(() => {
    if (focused || text || listening) return;
    const id = setInterval(() => {
      setShowPlaceholder(false);
      setTimeout(() => {
        setPlaceholderIdx((i) => (i + 1) % PLACEHOLDERS.length);
        setShowPlaceholder(true);
      }, 400);
    }, 3200);
    return () => clearInterval(id);
  }, [focused, text, listening]);

  // Auto-grow textarea
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [text]);

  // Cmd+/ focus shortcut
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "/") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Voice recognition
  useEffect(() => {
    if (!SpeechRecognition) return;
    const recog = new SpeechRecognition();
    recog.lang = "en-US";
    recog.interimResults = true;
    recog.continuous = false;
    recog.onresult = (e) => {
      const transcript = Array.from(e.results).map((r) => r[0].transcript).join("");
      setText(transcript);
      if (e.results[e.results.length - 1].isFinal) {
        setListening(false);
        if (transcript.trim()) { onSendRef.current?.(transcript.trim()); setText(""); }
      }
    };
    recog.onerror = () => setListening(false);
    recog.onend = () => setListening(false);
    recogRef.current = recog;
    return () => recog.abort();
  }, []);

  const toggleVoice = () => {
    if (!recogRef.current) return;
    if (listening) { recogRef.current.stop(); setListening(false); }
    else { setText(""); recogRef.current.start(); setListening(true); }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!text.trim() || loading) return;
    onSend(text.trim());
    setText("");
    if (inputRef.current) inputRef.current.style.height = "auto";
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) handleSubmit(e);
  };

  const showAnimatedPlaceholder = !text && !listening && !focused && showPlaceholder;

  return (
    <div className="input-bar-wrapper">
      <motion.form
        className="input-bar"
        onSubmit={handleSubmit}
        animate={focused ? { boxShadow: "var(--shadow-md), 0 0 0 3px rgba(0,113,227,0.1)", borderColor: "rgba(0,113,227,0.45)" } : { boxShadow: "var(--shadow-md)", borderColor: "var(--border-strong)" }}
        transition={{ duration: 0.2 }}
      >
        <div className="input-bar__field-wrap">
          <textarea
            ref={inputRef}
            className="input-bar__field"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            placeholder=""
            rows={1}
            disabled={loading && !text}
          />

          {/* Animated cycling placeholder */}
          <AnimatePresence mode="wait">
            {showAnimatedPlaceholder && (
              <motion.span
                key={placeholderIdx}
                className="input-bar__placeholder"
                variants={containerVariants}
                initial="initial"
                animate="animate"
                exit="exit"
                aria-hidden
              >
                {PLACEHOLDERS[placeholderIdx].split("").map((ch, i) => (
                  <motion.span key={i} variants={letterVariants} style={{ display: "inline-block" }}>
                    {ch === " " ? "\u00A0" : ch}
                  </motion.span>
                ))}
              </motion.span>
            )}
          </AnimatePresence>
        </div>

        {SpeechRecognition && (
          <motion.button
            type="button"
            className={`input-bar__mic ${listening ? "input-bar__mic--active" : ""}`}
            onClick={toggleVoice}
            disabled={loading}
            aria-label={listening ? "Stop listening" : "Voice input"}
            whileHover={{ scale: 1.08 }}
            whileTap={{ scale: 0.92 }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
              <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
              <line x1="12" x2="12" y1="19" y2="22" />
            </svg>
          </motion.button>
        )}

        <AnimatePresence mode="wait">
          {loading ? (
            <motion.button
              key="stop"
              type="button"
              className="input-bar__send input-bar__send--stop"
              onClick={onStop}
              aria-label="Stop"
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.8, opacity: 0 }}
              transition={{ duration: 0.15 }}
              whileHover={{ scale: 1.08 }}
              whileTap={{ scale: 0.92 }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                <rect x="5" y="5" width="14" height="14" rx="2" />
              </svg>
            </motion.button>
          ) : (
            <motion.button
              key="send"
              className={`input-bar__send ${text.trim() ? "input-bar__send--active" : ""}`}
              type="submit"
              disabled={!text.trim()}
              aria-label="Send"
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.8, opacity: 0 }}
              transition={{ duration: 0.15 }}
              whileHover={text.trim() ? { scale: 1.08 } : {}}
              whileTap={text.trim() ? { scale: 0.92 } : {}}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </motion.button>
          )}
        </AnimatePresence>
      </motion.form>

      <p className="input-bar__hint">Omni Copilot · powered by Groq</p>
    </div>
  );
}
