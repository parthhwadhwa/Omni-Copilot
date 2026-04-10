import { useState, useRef, useEffect } from "react";
import "./InputBar.css";

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

export default function InputBar({ onSend, loading }) {
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const inputRef = useRef(null);
  const recogRef = useRef(null);

  useEffect(() => {
    if (!SpeechRecognition) return;
    const recog = new SpeechRecognition();
    recog.lang = "en-US";
    recog.interimResults = true;
    recog.continuous = false;

    recog.onresult = (e) => {
      const transcript = Array.from(e.results)
        .map((r) => r[0].transcript)
        .join("");
      setText(transcript);
      // Auto-send on final result
      if (e.results[e.results.length - 1].isFinal) {
        setListening(false);
        if (transcript.trim()) {
          onSend(transcript.trim());
          setText("");
        }
      }
    };

    recog.onerror = () => setListening(false);
    recog.onend = () => setListening(false);

    recogRef.current = recog;
    return () => recog.abort();
  }, [onSend]);

  const toggleVoice = () => {
    if (!recogRef.current) return;
    if (listening) {
      recogRef.current.stop();
      setListening(false);
    } else {
      setText("");
      recogRef.current.start();
      setListening(true);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!text.trim() || loading) return;
    onSend(text.trim());
    setText("");
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      handleSubmit(e);
    }
  };

  return (
    <div className="input-bar-wrapper">
      <form className="input-bar" onSubmit={handleSubmit}>
        <textarea
          ref={inputRef}
          className="input-bar__field"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={listening ? "Listening..." : "Message Omni Copilot..."}
          rows={1}
          disabled={loading}
        />
        {SpeechRecognition && (
          <button
            type="button"
            className={`input-bar__mic ${listening ? "input-bar__mic--active" : ""}`}
            onClick={toggleVoice}
            disabled={loading}
            aria-label={listening ? "Stop listening" : "Voice input"}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
              <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
              <line x1="12" x2="12" y1="19" y2="22" />
            </svg>
          </button>
        )}
        <button
          className={`input-bar__send ${text.trim() ? "input-bar__send--active" : ""}`}
          type="submit"
          disabled={!text.trim() || loading}
          aria-label="Send"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 12h14M12 5l7 7-7 7" />
          </svg>
        </button>
      </form>
      <p className="input-bar__hint">
        Omni Copilot · powered by Groq
      </p>
    </div>
  );
}
