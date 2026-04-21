import { useState, useRef, useEffect, useCallback } from "react";
import Sidebar from "./components/Sidebar";
import ChatArea from "./components/ChatArea";
import InputBar from "./components/InputBar";
import "./App.css";

const API = "http://localhost:8001";

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
      messages: s.messages.slice(-50).map(({ _typewriter, _id, _planning, _steps, ...m }) => m),
    }));
    localStorage.setItem("sessions", JSON.stringify(trimmed));
  } catch {
    // storage full
  }
}

export default function App() {
  const [sessions, setSessions] = useState(loadSessions);
  const [activeId, setActiveId] = useState(() => sessions[sessions.length - 1]?.id ?? null);
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(window.innerWidth > 768);
  const [autoMode, setAutoMode] = useState(false);
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "light");
  const scrollRef = useRef(null);
  const abortRef = useRef(null);

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

    const sessionId = activeId || sessions[sessions.length - 1]?.id;
    if (!sessionId) return;
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

    const controller = new AbortController();
    abortRef.current = controller;

    // Insert a live-progress placeholder immediately
    const placeholderId = `ph-${Date.now()}`;
    updateSession(sessionId, (s) => ({
      ...s,
      messages: [...s.messages, {
        role: "assistant", _id: placeholderId,
        reply: "", plan: [], content: [], log: [], ts: Date.now(),
        _steps: [], _planning: true,
      }],
    }));

    try {
      const res = await fetch(`${API}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, auto_mode: autoMode }),
        signal: controller.signal,
      });

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n\n");
        buf = lines.pop();
        for (const line of lines) {
          const data = line.replace(/^data: /, "").trim();
          if (!data) continue;
          try {
            const evt = JSON.parse(data);
            if (evt.type === "planning") {
              updateSession(sessionId, (s) => ({
                ...s,
                messages: s.messages.map((m) =>
                  m._id === placeholderId ? { ...m, _planning: true, _steps: [] } : m
                ),
              }));
            } else if (evt.type === "step") {
              updateSession(sessionId, (s) => ({
                ...s,
                messages: s.messages.map((m) =>
                  m._id === placeholderId
                    ? { ...m, _planning: false, _steps: [...(m._steps || []), evt] }
                    : m
                ),
              }));
            } else if (evt.type === "done") {
              updateSession(sessionId, (s) => ({
                ...s,
                messages: s.messages.map((m) =>
                  m._id === placeholderId
                    ? {
                        role: "assistant",
                        reply: evt.reply || "",
                        plan: evt.plan || [],
                        content: evt.results || [],
                        log: evt.log || [],
                        ts: Date.now(),
                        _typewriter: true,
                      }
                    : m
                ),
              }));
            }
          } catch { /* ignore parse errors */ }
        }
      }
    } catch (err) {
      const aborted = err?.name === "AbortError";
      updateSession(sessionId, (s) => ({
        ...s,
        messages: s.messages.map((m) =>
          m._id === placeholderId
            ? {
                role: "assistant", plan: [], log: [], ts: Date.now(),
                content: [{ ok: false, error: aborted ? "Request stopped." : "Could not reach the server." }],
                retryOf: aborted ? undefined : text,
              }
            : m
        ),
      }));
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  };

  const stop = () => {
    abortRef.current?.abort();
  };

  const newChat = () => {
    const session = newSession();
    setSessions((prev) => [...prev, session]);
    setActiveId(session.id);
  };

  const renameSession = (id, title) => {
    updateSession(id, (s) => ({ ...s, title: title.slice(0, 60) || "New Chat" }));
  };

  // Keyboard shortcuts: Cmd/Ctrl+K new chat, Escape closes sidebar on mobile
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        newChat();
      } else if (e.key === "Escape" && window.innerWidth <= 768) {
        setSidebarOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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
        onRenameSession={renameSession}
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
        <ChatArea messages={messages} loading={loading} scrollRef={scrollRef} onChipClick={send} onRetry={send} />
        <InputBar onSend={send} onStop={stop} loading={loading} />
      </main>
    </div>
  );
}
