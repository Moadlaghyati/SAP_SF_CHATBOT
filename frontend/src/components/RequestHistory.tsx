import type { RequestDetail, RequestListItem } from "../types/api";
import { MarkdownBlock } from "./MarkdownBlock";
import { StatusPill } from "./StatusPill";

interface RequestHistoryProps {
  items: RequestListItem[];
  selectedRequestId: string | null;
  selectedRequest: RequestDetail | null;
  onSelect: (requestId: string) => void;
}

function titleFromQuestion(item: RequestListItem): string {
  const intentLabel = item.parsed_intent
    ?.split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
  const cleanedQuestion = item.question
    .replace(/[?.!]+$/g, "")
    .replace(/\s+/g, " ")
    .trim();

  if (intentLabel && cleanedQuestion.length > 0) {
    return `${intentLabel}: ${cleanedQuestion.slice(0, 48)}${cleanedQuestion.length > 48 ? "..." : ""}`;
  }

  return cleanedQuestion.slice(0, 58) || "Untitled conversation";
}

function formatConversationTime(value: string): string {
  return new Date(value).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function RequestHistory({ items, selectedRequestId, selectedRequest, onSelect }: RequestHistoryProps) {
  return (
    <section className="history-panel">
      <div className="section-heading">
        <div>
          <span className="section-kicker">Timeline</span>
          <h2>Conversation history</h2>
        </div>
        <span className="status-badge status-badge--neutral">{items.length} saved</span>
      </div>
      <div className="history-list">
        {items.length === 0 ? (
          <div className="empty-state">
            <strong>No conversations yet.</strong>
            <span>Ask the assistant one question and a titled conversation will appear here.</span>
          </div>
        ) : null}
        {items.map((item) => (
          <article
            key={item.request_id}
            className={`history-item ${selectedRequestId === item.request_id ? "history-item--active" : ""}`}
          >
            <button className="history-item__button" type="button" onClick={() => onSelect(item.request_id)}>
              <div className="history-item__header">
                <strong>{titleFromQuestion(item)}</strong>
                <StatusPill label={item.status} tone={item.status} />
              </div>
              <div className="history-item__meta">
                <span>{formatConversationTime(item.created_at)}</span>
                <span>{item.acting_user}</span>
                <span>{item.tool_name ?? "No tool run"}</span>
                <span>{item.authorization_outcome}</span>
              </div>
            </button>
            {selectedRequestId === item.request_id && selectedRequest ? (
              <div className="history-conversation">
                <div className="history-turn history-turn--user">
                  <span>User</span>
                  <p>{selectedRequest.question}</p>
                </div>
                <div className="history-turn history-turn--assistant">
                  <span>Assistant</span>
                  {selectedRequest.answer ? (
                    <MarkdownBlock text={selectedRequest.answer} />
                  ) : (
                    <p>No answer was stored for this conversation.</p>
                  )}
                </div>
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}
