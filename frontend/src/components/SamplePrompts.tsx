interface SamplePromptsProps {
  prompts: string[];
  onPick: (prompt: string) => void;
}

export function SamplePrompts({ prompts, onPick }: SamplePromptsProps) {
  return (
    <section className="panel">
      <div className="panel__header">
        <h2>Sample Prompts</h2>
        <span className="panel__eyebrow">Demo ready</span>
      </div>
      <div className="prompt-grid">
        {prompts.map((prompt) => (
          <button key={prompt} className="prompt-card" type="button" onClick={() => onPick(prompt)}>
            {prompt}
          </button>
        ))}
      </div>
    </section>
  );
}
