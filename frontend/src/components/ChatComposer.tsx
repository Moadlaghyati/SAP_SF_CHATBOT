import type { KeyboardEvent } from "react";

interface ChatComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  loading: boolean;
}

export function ChatComposer({ value, onChange, onSubmit, loading }: ChatComposerProps) {
  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!loading && value.trim()) {
        onSubmit();
      }
    }
  }

  return (
    <div className="inline-composer">
      <textarea
        className="inline-composer__input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask about absences, time off, or say hello..."
        rows={1}
        disabled={loading}
      />
      <button
        className="inline-composer__send"
        type="button"
        onClick={onSubmit}
        disabled={loading || !value.trim()}
        title="Send"
      >
        {loading ? "⏳" : "➤"}
      </button>
    </div>
  );
}
