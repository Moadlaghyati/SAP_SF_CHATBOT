import type { AuditRecord } from "../types/api";
import { StatusPill } from "./StatusPill";

interface AuditViewerProps {
  records: AuditRecord[];
}

export function AuditViewer({ records }: AuditViewerProps) {
  return (
    <section className="audit-panel">
      <div className="section-heading">
        <div>
          <span className="section-kicker">Governance</span>
          <h2>Audit log</h2>
        </div>
        <span className="status-badge status-badge--success">Enabled</span>
      </div>
      {records.length === 0 ? (
        <div className="empty-state">
          <strong>No audit records yet.</strong>
          <span>Completed requests will appear here with authorization outcome and timing.</span>
        </div>
      ) : (
        <div className="audit-table-wrap">
          <div className="audit-table" role="table" aria-label="Audit records">
            <div className="audit-row audit-row--head" role="row">
              <span>Time</span>
              <span>User</span>
              <span>Action</span>
              <span>Authorization</span>
              <span>Status</span>
            </div>
            {records.slice(0, 8).map((record) => (
              <div className="audit-row" role="row" key={`${record.request_id}-${record.timestamp}`}>
                <span>{new Date(record.timestamp).toLocaleTimeString()}</span>
                <span>{record.acting_user}</span>
                <span>{record.tool_called ?? record.parsed_intent ?? "No tool"}</span>
                <span>{record.authorization_outcome}</span>
                <span>
                  <StatusPill label={record.final_status} tone={record.final_status} />
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
