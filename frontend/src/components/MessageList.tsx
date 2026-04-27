import type { ChatMessage } from "../types/api";
import { StatusPill } from "./StatusPill";

interface MessageListProps {
  messages: ChatMessage[];
  pendingElapsedSeconds?: number;
}

export function MessageList({ messages, pendingElapsedSeconds = 0 }: MessageListProps) {
  return (
    <section className="panel chat-panel">
      <div className="panel__header">
        <h2>Conversation</h2>
        <span className="panel__eyebrow">Manager demo view</span>
      </div>
      <div className="message-list">
        {messages.length === 0 ? (
          <div className="empty-state">
            <strong>Start with one of the seeded prompts.</strong>
            <span>The assistant will show the parsed intent, tool path, and authorization outcome.</span>
          </div>
        ) : null}
        {messages.map((message) => (
          <article
            key={message.id}
            className={`message-card message-card--${message.role} ${message.pending ? "message-card--pending" : ""}`}
          >
            <div className="message-card__meta">
              <span>{message.role === "user" ? "Manager" : "Assistant"}</span>
              {message.pending ? <span className="pending-indicator">Thinking locally... {pendingElapsedSeconds}s</span> : null}
              {message.status ? <StatusPill label={message.status} tone={message.status} /> : null}
            </div>
            <p className="message-card__text">{message.text}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
