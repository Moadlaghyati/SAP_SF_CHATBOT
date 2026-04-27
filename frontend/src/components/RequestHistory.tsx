import type { RequestListItem } from "../types/api";
import { StatusPill } from "./StatusPill";

interface RequestHistoryProps {
  items: RequestListItem[];
  selectedRequestId: string | null;
  onSelect: (requestId: string) => void;
}

export function RequestHistory({ items, selectedRequestId, onSelect }: RequestHistoryProps) {
  return (
    <section className="panel history-panel">
      <div className="panel__header">
        <h2>Request History</h2>
        <span className="panel__eyebrow">SQLite-backed</span>
      </div>
      <div className="history-list">
        {items.length === 0 ? (
          <div className="empty-state">
            <strong>No requests yet.</strong>
            <span>Ask the assistant one question and it will appear here with its trace metadata.</span>
          </div>
        ) : null}
        {items.map((item) => (
          <button
            key={item.request_id}
            className={`history-item ${selectedRequestId === item.request_id ? "history-item--active" : ""}`}
            type="button"
            onClick={() => onSelect(item.request_id)}
          >
            <div className="history-item__header">
              <strong>{item.question}</strong>
              <StatusPill label={item.status} tone={item.status} />
            </div>
            <div className="history-item__meta">
              <span>{new Date(item.created_at).toLocaleString()}</span>
              <span>{item.acting_user}</span>
              <span>{item.tool_name ?? "No tool run"}</span>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}
