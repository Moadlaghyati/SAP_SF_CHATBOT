import type { ChatMessage } from "../types/api";
import { MarkdownBlock } from "./MarkdownBlock";
import { StatusPill } from "./StatusPill";

interface MessageListProps {
  messages: ChatMessage[];
  pendingElapsedSeconds?: number;
}

export function MessageList({ messages, pendingElapsedSeconds = 0 }: MessageListProps) {
  return (
    <section className="chat-panel">
      <div className="chat-panel__header">
        <div>
          <span className="section-kicker">Assistant workspace</span>
          <h2>Conversation</h2>
        </div>
        <StatusPill label="Trace available" tone="success" />
      </div>
      <div className="message-list">
        {messages.length === 0 ? (
          <div className="empty-state">
            <strong>Ask a question or choose a suggested workflow.</strong>
            <span>The assistant will answer in chat while the inspector keeps traceability close by.</span>
          </div>
        ) : null}
        {messages.map((message) => (
          <article
            key={message.id}
            className={`message-card message-card--${message.role} ${message.pending ? "message-card--pending" : ""}`}
          >
            <div className="message-avatar" aria-hidden="true">
              {message.role === "user" ? "U" : "AI"}
            </div>
            <div className="message-card__meta">
              <span>{message.role === "user" ? "Manager" : "Assistant"}</span>
              {message.pending ? <span className="pending-indicator">Thinking locally... {pendingElapsedSeconds}s</span> : null}
              {message.status ? <StatusPill label={message.status} tone={message.status} /> : null}
            </div>
            <div className="message-card__text">
              {message.role === "assistant" && !message.pending ? (
                <MarkdownBlock text={message.text} />
              ) : (
                <p>{message.text}</p>
              )}
            </div>
            {message.role === "assistant" && !message.pending ? (
              <details className="why-answer">
                <summary>Why this answer?</summary>
                <p>Backend authorization, approved tools, and audit logging were used for this response.</p>
              </details>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}
