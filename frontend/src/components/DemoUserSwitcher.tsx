import type { DemoUserSummary } from "../types/api";

interface DemoUserSwitcherProps {
  users: DemoUserSummary[];
  activeUserId: string;
  onChange: (userId: string) => void;
  usingFallbackUsers?: boolean;
}

export function DemoUserSwitcher({
  users,
  activeUserId,
  onChange,
  usingFallbackUsers = false,
}: DemoUserSwitcherProps) {
  const activeUser = users.find((user) => user.user_id === activeUserId);
  const initials =
    activeUser?.display_name
      .split(" ")
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join("") ?? "HR";

  return (
    <section className="persona-card">
      <div className="section-heading">
        <div>
          <span className="section-kicker">Identity</span>
          <h2>Demo persona</h2>
        </div>
        {activeUser ? <span className="status-badge status-badge--neutral">{activeUser.role}</span> : null}
      </div>

      <div className="persona-summary">
        <div className="persona-avatar" aria-hidden="true">
          {initials}
        </div>
        <div>
          <strong>{activeUser?.display_name ?? "Loading persona"}</strong>
          <span>{activeUser?.employee_id ?? "No employee id"}</span>
        </div>
      </div>

      <select
        className="select-input"
        value={activeUserId}
        onChange={(event) => onChange(event.target.value)}
        disabled={users.length === 0}
      >
        {users.length === 0 ? (
          <option value="">No demo personas available</option>
        ) : null}
        {users.map((user) => (
          <option key={user.user_id} value={user.user_id}>
            {user.display_name} - {user.role}
          </option>
        ))}
      </select>

      <p className="supporting-copy">{activeUser?.description ?? "Choose a seeded demo persona."}</p>
      {usingFallbackUsers ? (
        <p className="inline-warning">Built-in personas are shown until the backend responds.</p>
      ) : null}
    </section>
  );
}
