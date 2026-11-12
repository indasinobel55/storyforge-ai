import Link from "next/link";
import { formatDate, formatDuration, ACTIVE_STATUSES } from "@/lib/format";
import type { Project } from "@/lib/types";
import { ProgressBar, StatusPill } from "./Status";

export function ProjectCard({ project }: { project: Project }) {
  return (
    <Link
      href={`/projects/${project.id}`}
      className="card group block p-5 transition hover:border-ember-500/30 hover:shadow-glow"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate font-display text-lg text-foreground group-hover:text-ember-400">{project.title}</h3>
          <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-slate-500">
            {project.logline || project.script}
          </p>
        </div>
        <StatusPill status={project.status} />
      </div>
      <div className="mt-4 flex items-center gap-3 text-[11px] uppercase tracking-wide text-slate-500">
        <span>{project.target_scene_count} scenes</span>
        <span className="h-1 w-1 rounded-full bg-slate-600" />
        <span>{formatDuration(project.target_duration_seconds)}</span>
        <span className="h-1 w-1 rounded-full bg-slate-600" />
        <span>{project.orientation}</span>
        <span className="ml-auto chip bg-foreground/[0.04] text-slate-400">{project.execution_mode}</span>
      </div>
      <div className="mt-4">
        <ProgressBar value={project.progress} />
        <div className="mt-2 flex items-center justify-between text-[11px] text-slate-500">
          <span>{ACTIVE_STATUSES.has(project.status) ? "In progress" : `Updated ${formatDate(project.updated_at)}`}</span>
          <span>{project.progress}%</span>
        </div>
      </div>
    </Link>
  );
}
