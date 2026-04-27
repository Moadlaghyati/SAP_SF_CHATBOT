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

  return (
    <section className="panel panel--compact">
      <div className="panel__header">
        <h2>Demo User</h2>
        {activeUser ? <span className="panel__eyebrow">{activeUser.role}</span> : null}
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
      <p className="muted-text">{activeUser?.description ?? "Choose a seeded demo persona."}</p>
      {usingFallbackUsers ? (
        <p className="muted-text">
          Showing built-in demo personas because the backend could not be reached yet.
        </p>
      ) : null}
    </section>
  );
}
