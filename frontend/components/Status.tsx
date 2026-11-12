import { STATUS_STYLES, titleCase } from "@/lib/format";

export function StatusPill({ status }: { status: string }) {
  return <span className={`chip ${STATUS_STYLES[status] || "bg-ink-700 text-slate-300"}`}>{titleCase(status)}</span>;
}

export function ProgressBar({ value, className = "" }: { value: number; className?: string }) {
  const safe = Math.max(0, Math.min(100, value));
  return (
    <div className={`h-1.5 w-full overflow-hidden rounded-full bg-foreground/[0.08] ${className}`}>
      <div
        className="h-full rounded-full bg-gradient-to-r from-ember-600 via-ember-500 to-mint-400 transition-all duration-500"
        style={{ width: `${safe}%` }}
      />
    </div>
  );
}
