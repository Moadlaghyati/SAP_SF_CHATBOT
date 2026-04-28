export interface PromptGroup {
  title: string;
  prompts: string[];
}

interface SamplePromptsProps {
  groups: PromptGroup[];
  onPick: (prompt: string) => void;
}

export function SamplePrompts({ groups, onPick }: SamplePromptsProps) {
  return (
    <section className="prompt-panel" aria-label="Suggested HR questions">
      <div className="section-heading">
        <div>
          <span className="section-kicker">Suggested questions</span>
          <h2>Start a workflow</h2>
        </div>
      </div>

      <div className="prompt-groups">
        {groups.map((group) => (
          <div className="prompt-group" key={group.title}>
            <h3>{group.title}</h3>
            <div className="prompt-chip-row">
              {group.prompts.map((prompt) => (
                <button key={prompt} className="prompt-chip" type="button" onClick={() => onPick(prompt)}>
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
