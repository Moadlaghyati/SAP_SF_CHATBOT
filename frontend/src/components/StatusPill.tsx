import type { RequestStatus } from "../types/api";

interface StatusPillProps {
  label: string;
  tone?: RequestStatus | "neutral" | "completed" | "running" | "stopped" | "needs_clarification";
}

export function StatusPill({ label, tone = "neutral" }: StatusPillProps) {
  return <span className={`status-pill status-pill--${tone}`}>{label}</span>;
}
