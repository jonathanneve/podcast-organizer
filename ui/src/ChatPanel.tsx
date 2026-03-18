import { useEffect, useRef, useState } from "react";
import "./ChatPanel.scss";

interface ChatMessage {
  source: "user" | "assistant";
  message: string;
}

interface Props {
  podcastId: number;
  episodeId: number;
}

export default function ChatPanel({ podcastId, episodeId }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const chatUrl = `/podcasts/${podcastId}/episodes/${episodeId}/chat`;

  useEffect(() => {
    fetch(chatUrl)
      .then((r) => r.json())
      .then(setMessages)
      .catch(console.error);
  }, [episodeId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async () => {
    const question = input.trim();
    if (!question || sending) return;

    setMessages((prev) => [...prev, { source: "user", message: question }]);
    setInput("");
    setSending(true);

    try {
      const resp = await fetch(chatUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      if (resp.ok) {
        const data = await resp.json();
        setMessages((prev) => [...prev, { source: "assistant", message: data.answer }]);
      } else {
        setMessages((prev) => [
          ...prev,
          { source: "assistant", message: "Sorry, I couldn't process that question." },
        ]);
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { source: "assistant", message: "An error occurred. Please try again." },
      ]);
    } finally {
      setSending(false);
    }
  };

  const clearHistory = async () => {
    try {
      const resp = await fetch(chatUrl, { method: "DELETE" });
      if (resp.ok) {
        setMessages([]);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <h3>Chat</h3>
        {messages.length > 0 && (
          <button className="chat-clear" onClick={clearHistory}>
            Clear History
          </button>
        )}
      </div>
      <div className="chat-messages">
        {messages.length === 0 && (
          <p className="chat-empty">Ask a question about this episode...</p>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`chat-msg chat-msg--${msg.source}`}>
            {msg.message}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>
      <div className="chat-input-row">
        <input
          className="chat-input"
          type="text"
          placeholder="Ask a question..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={sending}
        />
        <button
          className="chat-send"
          onClick={sendMessage}
          disabled={sending || !input.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
}
