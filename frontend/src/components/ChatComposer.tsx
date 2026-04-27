interface ChatComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  loading: boolean;
}

export function ChatComposer({ value, onChange, onSubmit, loading }: ChatComposerProps) {
  return (
    <section className="panel composer">
      <div className="panel__header">
        <h2>Ask the Assistant</h2>
        <span className="panel__eyebrow">Natural language in, strict tools out</span>
      </div>
      <textarea
        className="composer__input"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Say hello, ask what the assistant can do, or ask about absences, date ranges, and breakdowns..."
        rows={4}
      />
      <div className="composer__actions">
        <span className="muted-text">Only approved internal tools can access employee data.</span>
        <button className="primary-button" type="button" onClick={onSubmit} disabled={loading}>
          {loading ? "Waiting for local model..." : "Send"}
        </button>
      </div>
    </section>
  );
}
