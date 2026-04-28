interface ChatComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  loading: boolean;
}

export function ChatComposer({ value, onChange, onSubmit, loading }: ChatComposerProps) {
  return (
    <section className="composer">
      <textarea
        className="composer__input"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Ask about absences, leave balances, access rights, or policy questions..."
        rows={4}
      />
      <div className="composer__actions">
        <span className="composer__hint">Strict tools only. Backend authorization runs before HR data access.</span>
        <button className="primary-button" type="button" onClick={onSubmit} disabled={loading}>
          {loading ? "Processing" : "Send"}
        </button>
      </div>
    </section>
  );
}
