import { Component } from "react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "center",
          justifyContent: "center", height: "100vh", gap: "12px",
          fontFamily: "system-ui, sans-serif", color: "#6e6e73",
        }}>
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#ff3b30" strokeWidth="1.5" strokeLinecap="round">
            <circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>
          </svg>
          <p style={{ fontSize: "15px", fontWeight: 500, color: "#1d1d1f" }}>Something went wrong</p>
          <p style={{ fontSize: "13px" }}>{this.state.error.message}</p>
          <button
            onClick={() => window.location.reload()}
            style={{
              marginTop: "8px", padding: "8px 18px", borderRadius: "8px",
              border: "1px solid rgba(0,0,0,0.1)", background: "#f5f5f7",
              cursor: "pointer", fontSize: "13px", fontWeight: 500,
            }}
          >
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
