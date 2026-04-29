import { useState, useRef, useEffect } from "react";

export default function Chatbot() {
  const [message, setMessage] = useState("");
  const [chat, setChat] = useState([]);
  const [streaming, setStreaming] = useState(false);
  const chatEndRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat]);

  const sendMessage = async () => {
    const text = message.trim();
    if (!text || streaming) return;

    setChat(prev => [
      ...prev,
      { role: "user", text },
      { role: "assistant", text: "" }, // placeholder grows as tokens arrive
    ]);
    setMessage("");
    setStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const apiHost = window.location.hostname;
      const apiProtocol = window.location.protocol;
      const apiUrl = `${apiProtocol}//${apiHost}:8000/chat/stream`;

      const response = await fetch(apiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        if (!chunk) continue;

        setChat(prev => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last && last.role === "assistant") {
            next[next.length - 1] = { ...last, text: last.text + chunk };
          }
          return next;
        });
      }
    } catch (err) {
      if (err.name !== "AbortError") {
        console.error("CHAT ERROR:", err);
        setChat(prev => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last && last.role === "assistant" && !last.text) {
            next[next.length - 1] = {
              ...last,
              text: "Backend connection error",
            };
          }
          return next;
        });
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const stopStream = () => {
    abortRef.current?.abort();
  };

  return (
    <div style={container}>
      <div style={header}>Industrial AI Assistant</div>

      <div style={chatArea}>
        {chat.length === 0 && (
          <div style={hint}>
            Ask about machines, trends, or what to do next.
            <br />
            e.g. "why is M_3 hot?", "which machine is worst?", "what
            happened in the last 10 minutes?"
          </div>
        )}

        {chat.map((msg, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
              marginBottom: 10,
            }}
          >
            <div
              style={{
                ...bubble,
                background: msg.role === "user" ? "#2e7d32" : "#2a2a2a",
                whiteSpace: "pre-wrap",
              }}
            >
              {msg.text || (streaming && i === chat.length - 1 ? "..." : "")}
            </div>
          </div>
        ))}

        <div ref={chatEndRef} />
      </div>

      <div style={inputBar}>
        <input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyPress}
          placeholder="Ask about machine health, history, or what to do..."
          style={input}
          disabled={streaming}
        />
        {streaming ? (
          <button onClick={stopStream} style={stopBtn}>
            Stop
          </button>
        ) : (
          <button onClick={sendMessage} style={sendBtn}>
            Send
          </button>
        )}
      </div>
    </div>
  );
}

// ================= STYLES =================

const container = {
  height: "100%",
  display: "flex",
  flexDirection: "column",
  background: "#1e1e1e",
  color: "white",
};

const header = {
  padding: "10px",
  background: "#2c2c2c",
  fontWeight: "bold",
  borderBottom: "1px solid #333",
};

const chatArea = {
  flex: 1,
  overflowY: "auto",
  padding: "10px",
  background: "#121212",
};

const hint = {
  opacity: 0.55,
  fontSize: "13px",
  lineHeight: 1.5,
  padding: "8px 4px",
};

const bubble = {
  padding: "8px 12px",
  borderRadius: "12px",
  maxWidth: "80%",
  fontSize: "14px",
  lineHeight: 1.4,
};

const inputBar = {
  display: "flex",
  padding: "10px",
  borderTop: "1px solid #333",
  gap: "8px",
};

const input = {
  flex: 1,
  padding: "8px",
  borderRadius: "6px",
  border: "none",
  outline: "none",
};

const sendBtn = {
  padding: "8px 14px",
  background: "#1976d2",
  color: "white",
  border: "none",
  borderRadius: "6px",
  cursor: "pointer",
};

const stopBtn = {
  padding: "8px 14px",
  background: "#b71c1c",
  color: "white",
  border: "none",
  borderRadius: "6px",
  cursor: "pointer",
};
