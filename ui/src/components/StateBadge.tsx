const STATE_CLASSES: Record<string, string> = {
  submitted: "state-submitted",
  working: "state-working",
  completed: "state-completed",
  failed: "state-failed",
  canceled: "state-canceled",
  rejected: "state-rejected",
  "input-required": "state-input-required",
  "auth-required": "state-auth-required",
};

export function StateBadge({ state }: { state?: string }) {
  if (!state) return null;
  const cls = STATE_CLASSES[state] || "state-submitted";
  return <span className={`state-badge ${cls}`}>{state}</span>;
}
