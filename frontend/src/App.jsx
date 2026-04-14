import { useState, useRef, useEffect, useCallback } from "react";
import Sidebar from "./components/Sidebar";
import ChatArea from "./components/ChatArea";
import InputBar from "./components/InputBar";
import "./App.css";

const API = "http://localhost:8000";

function newSession() {
  return { id: Date.now().toString(), title: "New Chat", messages: [], createdAt: Date.now() };
}

function loadSessions() {
  try {
    const raw = localStorage.getItem("sessions");
    const sessions = raw ? JSON.parse(raw) : [];
    return sessions.length > 0 ? sessions : [newSession()];
  } catch {
    return [newSession()];
  }
}

function saveSessions(sessions) {
  try {
    // Keep last 50 messages per session, max 30 sessions
    const trimmed = sessions.slice(-30).map((s) => ({
      ...s,
      messages: s.messages.slice(-50),
    }));
    localStorage.setItem("sessions", JSON.stringify(trimmed));
  } catch {
    // storage full
  }
}

export default function App() {
  const [sessions, setSessions] = useState(loadSessions);
  const [activeId, setActiveId] = useState(() => {
    const s = loadSessions();
    return s[s.length - 1].id;
  });
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(window.innerWidth > 768);
  const [autoMode, setAutoMode] = useState(false);
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "light");
  const scrollRef = useRef(null);

  const activeSession = sessions.find((s) => s.id === activeId) || sessions[sessions.length - 1];
  const messages = activeSession?.messages || [];

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  useEffect(() => {
    saveSessions(sessions);
  }, [sessions]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const updateSession = useCallback((id, updater) => {
    setSessions((prev) => prev.map((s) => (s.id === id ? updater(s) : s)));
  }, []);

  const send = async (text) => {
    if (!text.trim() || loading) return;
    if (window.innerWidth <= 768) setSidebarOpen(false);

    const sessionId = activeId;
    const userMsg = { role: "user", content: text, ts: Date.now() };

    // Set title from first user message
    setSessions((prev) =>
      prev.map((s) => {
        if (s.id !== sessionId) return s;
        const title = s.messages.length === 0 ? text.slice(0, 40) : s.title;
        return { ...s, title, messages: [...s.messages, userMsg] };
      })
    );
    setLoading(true);

    try {
      const res = await fetch(`${API}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, auto_mode: autoMode }),
      });
      const data = await res.json();
      const botMsg = {
        role: "assistant",
        reply: data.reply || "",
        plan: data.plan || [],
        content: data.results || [],
        log: data.log || [],
        ts: Date.now(),
      };
      updateSession(sessionId, (s) => ({ ...s, messages: [...s.messages, botMsg] }));
    } catch {
      updateSession(sessionId, (s) => ({
        ...s,
        messages: [
          ...s.messages,
          { role: "assistant", plan: [], content: [{ ok: false, error: "Could not reach the server." }], log: [], ts: Date.now() },
        ],
      }));
    } finally {
      setLoading(false);
    }
  };

  const newChat = () => {
    const session = newSession();
    setSessions((prev) => [...prev, session]);
    setActiveId(session.id);
  };

  const loadSession = (id) => {
    setActiveId(id);
    if (window.innerWidth <= 768) setSidebarOpen(false);
  };

  const deleteSession = (id) => {
    setSessions((prev) => {
      const remaining = prev.filter((s) => s.id !== id);
      if (remaining.length === 0) {
        const fresh = newSession();
        setActiveId(fresh.id);
        return [fresh];
      }
      if (id === activeId) {
        setActiveId(remaining[remaining.length - 1].id);
      }
      return remaining;
    });
  };

  return (
    <div className="app">
      <Sidebar
        open={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
        onNewChat={newChat}
        sessions={sessions}
        activeSessionId={activeId}
        onLoadSession={loadSession}
        onDeleteSession={deleteSession}
        autoMode={autoMode}
        onAutoModeToggle={() => setAutoMode(!autoMode)}
        onSend={send}
        theme={theme}
        onThemeToggle={() => setTheme(theme === "light" ? "dark" : "light")}
      />
      {sidebarOpen && (
        <div className="sidebar-backdrop" onClick={() => setSidebarOpen(false)} />
      )}
      <main className={`main ${sidebarOpen ? "" : "main--expanded"}`}>
        <ChatArea messages={messages} loading={loading} scrollRef={scrollRef} onChipClick={send} />
        <InputBar onSend={send} loading={loading} />
      </main>
    </div>
  );
}
