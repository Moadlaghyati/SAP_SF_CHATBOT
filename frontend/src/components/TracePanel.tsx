import type { HealthResponse, RequestDetail, ToolTrace } from "../types/api";
import { StatusPill } from "./StatusPill";

interface TracePanelProps {
  trace: ToolTrace | null;
  request: RequestDetail | null;
  health: HealthResponse | null;
}

function JsonBlock({ value }: { value: unknown }) {
  return <pre className="trace-json">{JSON.stringify(value, null, 2)}</pre>;
}

function ProcessSteps({ steps }: { steps: ToolTrace["process_steps"] | undefined }) {
  if (!steps || steps.length === 0) {
    return <p>No workflow steps recorded yet.</p>;
  }

  return (
    <ol className="process-steps">
      {steps.map((step, index) => (
        <li className="process-step" key={`${step.step}-${index}`}>
          <div className="process-step__header">
            <span className="process-step__name">{step.step}</span>
            <StatusPill label={step.status} tone={step.status as never} />
          </div>
          <p>{step.detail}</p>
          {Object.keys(step.data ?? {}).length > 0 ? <JsonBlock value={step.data} /> : null}
        </li>
      ))}
    </ol>
  );
}

export function TracePanel({ trace, request, health }: TracePanelProps) {
  return (
    <section className="panel trace-panel">
      <div className="panel__header">
        <h2>Trace & Debug</h2>
        {request ? <StatusPill label={request.status} tone={request.status} /> : null}
      </div>

      <div className="trace-grid">
        <div className="trace-section">
          <h3>Trust Signals</h3>
          <p>Model inference: {trace?.model_inference ?? health?.model_inference ?? "local"}</p>
          <p>External AI calls: {trace?.external_ai_calls ?? health?.external_ai_calls ?? "none"}</p>
          <p>LLM backend: {trace?.llm_backend ?? health?.llm_backend ?? "unknown"}</p>
          <p>LLM model: {trace?.llm_model ?? health?.llm_model ?? "unknown"}</p>
          <p>Data source: {trace?.data_source ?? health?.connector_backend ?? "unknown"}</p>
        </div>

        <div className="trace-section">
          <h3>Request</h3>
          <p>{trace?.request_message ?? request?.question ?? "No request selected."}</p>
        </div>

        <div className="trace-section trace-section--wide">
          <h3>Workflow Steps</h3>
          <ProcessSteps steps={trace?.process_steps} />
        </div>

        <div className="trace-section">
          <h3>Parsed Intent & Entities</h3>
          <JsonBlock value={trace?.parsed_request ?? {}} />
        </div>

        <div className="trace-section">
          <h3>Tool Execution</h3>
          <p>Tool: {trace?.tool_name ?? "No tool selected"}</p>
          <JsonBlock value={trace?.tool_arguments ?? {}} />
        </div>

        <div className="trace-section">
          <h3>Authorization</h3>
          <p>Outcome: {trace?.authorization_outcome ?? "pending"}</p>
          <p>{trace?.authorization_reason ?? "Backend authorization is enforced before data retrieval."}</p>
        </div>

        <div className="trace-section">
          <h3>Minimized Result</h3>
          <JsonBlock value={trace?.minimized_result ?? {}} />
        </div>

        <div className="trace-section">
          <h3>Final Answer Metadata</h3>
          <JsonBlock value={trace?.answer_metadata ?? {}} />
        </div>

        <div className="trace-section">
          <h3>Errors</h3>
          <JsonBlock value={trace?.errors ?? []} />
        </div>
      </div>
    </section>
  );
}
