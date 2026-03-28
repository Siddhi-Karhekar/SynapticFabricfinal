import { useState, useRef, useEffect } from "react";

export default function Chatbot() {

  const [message, setMessage] = useState("");
  const [chat, setChat] = useState([]);
  const [loading, setLoading] = useState(false);

  const chatEndRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat]);

  const sendMessage = async () => {

    if (!message.trim()) return;

    const userMessage = message;

    // ✅ Add user message
    setChat(prev => [
      ...prev,
      { role: "user", text: userMessage }
    ]);

    setMessage("");
    setLoading(true);

    try {
      const response = await fetch("http://127.0.0.1:8000/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        // ✅ FIXED KEY
        body: JSON.stringify({ message: userMessage })
      });

      const data = await response.json();

      console.log("CHAT RESPONSE:", data); // 🔥 DEBUG

      setChat(prev => [
        ...prev,
        {
          role: "assistant",
          // ✅ FIXED KEY
          text: data?.response || "⚠️ Backend returned empty response"
        }
      ]);

    } catch (err) {
      console.error("CHAT ERROR:", err);

      setChat(prev => [
        ...prev,
        {
          role: "assistant",
          text: "⚠️ Backend connection error"
        }
      ]);
    }

    setLoading(false);
  };

  const handleKeyPress = (e) => {
    if (e.key === "Enter") sendMessage();
  };

  return (
    <div style={container}>

      <div style={header}>
        🤖 Industrial AI Assistant
      </div>

      <div style={chatArea}>
        {chat.map((msg, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
              marginBottom: 10
            }}
          >
            <div style={{
              ...bubble,
              background: msg.role === "user" ? "#2e7d32" : "#2a2a2a"
            }}>
              {msg.text}
            </div>
          </div>
        ))}

        {loading && (
          <div style={{ opacity: 0.6 }}>🤖 Thinking...</div>
        )}

        <div ref={chatEndRef} />
      </div>

      <div style={inputBar}>
        <input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyPress}
          placeholder="Ask about machine health..."
          style={input}
        />

        <button onClick={sendMessage} style={sendBtn}>
          Send
        </button>
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
  borderBottom: "1px solid #333"
};

const chatArea = {
  flex: 1,
  overflowY: "auto",
  padding: "10px",
  background: "#121212"
};

const bubble = {
  padding: "8px 12px",
  borderRadius: "12px",
  maxWidth: "75%",
  fontSize: "14px"
};

const inputBar = {
  display: "flex",
  padding: "10px",
  borderTop: "1px solid #333",
  gap: "8px"
};

const input = {
  flex: 1,
  padding: "8px",
  borderRadius: "6px",
  border: "none",
  outline: "none"
};

const sendBtn = {
  padding: "8px 14px",
  background: "#1976d2",
  color: "white",
  border: "none",
  borderRadius: "6px",
  cursor: "pointer"
};