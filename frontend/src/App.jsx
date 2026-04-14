import { useState, useRef, useEffect } from "react";
import Sidebar from "./components/Sidebar";
import ChatArea from "./components/ChatArea";
import InputBar from "./components/InputBar";
import "./App.css";

const API = "http://localhost:8000";

export default function App() {
  const [messages, setMessages] = useState(() => {
    try {
      const saved = localStorage.getItem("chat_history");
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(window.innerWidth > 768);
  const [autoMode, setAutoMode] = useState(false);
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "light");
  const scrollRef = useRef(null);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  useEffect(() => {
    try {
      const trimmed = messages.slice(-50);
      localStorage.setItem("chat_history", JSON.stringify(trimmed));
    } catch {
      // storage full or unavailable
    }
  }, [messages]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const send = async (text) => {
    if (!text.trim() || loading) return;
    if (window.innerWidth <= 768) setSidebarOpen(false);

    const userMsg = { role: "user", content: text, ts: Date.now() };
    setMessages((prev) => [...prev, userMsg]);
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
      setMessages((prev) => [...prev, botMsg]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          plan: [],
          content: [{ ok: false, error: "Could not reach the server." }],
          log: [],
          ts: Date.now(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const clearChat = () => {
    setMessages([]);
    localStorage.removeItem("chat_history");
  };

  return (
    <div className="app">
      <Sidebar
        open={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
        onClear={clearChat}
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
