import type { AuditRecord } from "../types/api";
import { StatusPill } from "./StatusPill";

interface AuditViewerProps {
  records: AuditRecord[];
}

export function AuditViewer({ records }: AuditViewerProps) {
  return (
    <section className="panel audit-panel">
      <div className="panel__header">
        <h2>Audit Viewer</h2>
        <span className="panel__eyebrow">Visible by design</span>
      </div>
      <div className="audit-list">
        {records.length === 0 ? (
          <div className="empty-state">
            <strong>No audit records yet.</strong>
            <span>Completed requests will appear here with authorization outcome and timing.</span>
          </div>
        ) : null}
        {records.slice(0, 8).map((record) => (
          <article key={`${record.request_id}-${record.timestamp}`} className="audit-item">
            <div className="audit-item__header">
              <strong>{record.acting_user}</strong>
              <StatusPill label={record.final_status} tone={record.final_status} />
            </div>
            <p>{record.original_question}</p>
            <div className="audit-item__meta">
              <span>{record.parsed_intent ?? "n/a"}</span>
              <span>{record.tool_called ?? "no tool"}</span>
              <span>{record.authorization_outcome}</span>
              <span>{record.duration_ms} ms</span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
