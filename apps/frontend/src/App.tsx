import { useEffect, useRef, useState, type FormEvent } from "react";

import { createEscalation, streamChat } from "./api";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [escalating, setEscalating] = useState(false);
  const [escalationId, setEscalationId] = useState<number | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  function appendToReply(text: string) {
    setMessages((current) => {
      const last = current[current.length - 1];
      if (last?.role === "assistant") {
        return [...current.slice(0, -1), { ...last, content: last.content + text }];
      }
      return [...current, { role: "assistant", content: text }];
    });
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    const message = input.trim();
    if (!message || streaming) return;

    setInput("");
    setError(null);
    setStreaming(true);
    setMessages((current) => [...current, { role: "user", content: message }]);
    try {
      await streamChat(message, conversationId, (chatEvent) => {
        if (chatEvent.type === "conversation") setConversationId(chatEvent.conversation_id);
        if (chatEvent.type === "delta") appendToReply(chatEvent.text);
        if (chatEvent.type === "error") setError(chatEvent.message);
      });
    } catch {
      setError("Couldn't reach ContextKiln. Please try again.");
    } finally {
      setStreaming(false);
    }
  }

  async function escalate() {
    if (!conversationId) return;
    setError(null);
    setEscalating(true);
    try {
      const escalation = await createEscalation(conversationId);
      setEscalationId(escalation.id);
    } catch {
      setError("Couldn't send your request to a human. Please try again.");
    } finally {
      setEscalating(false);
    }
  }

  return (
    <main className="chat">
      <header className="chat-header">
        <h1>ContextKiln</h1>
        <button
          type="button"
          onClick={escalate}
          disabled={!conversationId || streaming || escalating || escalationId !== null}
        >
          Talk to a human
        </button>
      </header>

      <div className="messages" aria-live="polite">
        {messages.length === 0 && (
          <p className="empty">Ask a software engineering or infrastructure question.</p>
        )}
        {messages.map((message, index) => (
          <div key={index} className={`message ${message.role}`}>
            {message.content}
          </div>
        ))}
        {streaming && messages[messages.length - 1]?.role === "user" && (
          <p className="status">Thinking…</p>
        )}
        {escalationId !== null && (
          <p className="status" role="status">
            Your request has been sent to a human (reference #{escalationId}).
          </p>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div ref={endRef} />
      </div>

      <form className="composer" onSubmit={send}>
        <input
          aria-label="Message"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask a question"
        />
        <button type="submit" disabled={streaming || !input.trim()}>
          Send
        </button>
      </form>
    </main>
  );
}
