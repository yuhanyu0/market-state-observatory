type Props = {
  label: string;
  state: "ready" | "blocked" | "neutral" | "warning";
};

export function StatusBadge({ label, state }: Props) {
  return <span className={`status-badge status-${state}`}><span aria-hidden="true" />{label}</span>;
}
