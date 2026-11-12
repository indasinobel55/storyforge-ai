export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) return "—";
  const total = Math.round(seconds);
  const min = Math.floor(total / 60);
  const sec = total % 60;
  return min > 0 ? `${min}m ${sec}s` : `${sec}s`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

export function titleCase(value: string): string {
  return value
    .toLowerCase()
    .split(/[_\s]+/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export const ACTIVE_STATUSES = new Set(["PLANNING", "QUEUED", "GENERATING", "PROCESSING", "VALIDATING"]);

export const STATUS_STYLES: Record<string, string> = {
  DRAFT: "bg-ink-700 text-slate-300",
  PLANNING: "bg-amber-500/15 text-amber-300",
  AWAITING_APPROVAL: "bg-sky-500/15 text-sky-300",
  QUEUED: "bg-indigo-500/15 text-indigo-300",
  GENERATING: "bg-ember-500/15 text-ember-400",
  DOWNLOADING: "bg-ember-500/15 text-ember-400",
  PROCESSING: "bg-purple-500/15 text-purple-300",
  VALIDATING: "bg-cyan-500/15 text-cyan-300",
  SUCCEEDED: "bg-mint-500/15 text-mint-400",
  COMPLETED: "bg-mint-500/15 text-mint-400",
  FAILED: "bg-rose-500/15 text-rose-300",
  PAUSED: "bg-slate-500/15 text-slate-300",
  CANCELLED: "bg-slate-500/15 text-slate-400",
  PENDING: "bg-ink-700 text-slate-400",
  SUBMITTING: "bg-amber-500/15 text-amber-300",
};
