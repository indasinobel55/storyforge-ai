"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ProjectCard } from "@/components/ProjectCard";
import { api } from "@/lib/api";
import { ACTIVE_STATUSES, formatBytes } from "@/lib/format";
import type { ProjectList, Usage } from "@/lib/types";
import { Reveal } from "@/components/motion/Reveal";

export default function DashboardPage() {
  const [projects, setProjects] = useState<ProjectList | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [projectResponse, usageResponse] = await Promise.all([
        api<ProjectList>("/api/projects?limit=50"),
        api<Usage>("/api/usage"),
      ]);
      setProjects(projectResponse);
      setUsage(usageResponse);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load projects");
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => {
      if (projects?.items.some((project) => ACTIVE_STATUSES.has(project.status))) void load();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [load, projects?.items]);

  const active = projects?.items.filter((project) => ACTIVE_STATUSES.has(project.status)) ?? [];

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl text-foreground">Your productions</h1>
          <p className="mt-1 text-sm text-slate-400">Plan, generate and assemble multi-scene videos.</p>
        </div>
        <Link href="/projects/new" className="btn-primary">
          New project
        </Link>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ["Projects", usage?.projects_total ?? "—"],
          ["Active", usage?.projects_active ?? "—"],
          ["Videos", usage?.videos_total ?? "—"],
          ["Storage", usage ? formatBytes(usage.storage_used_bytes) : "—"],
        ].map(([label, value], index) => (
          <Reveal key={String(label)} delay={index * 0.06} y={16}>
            <div className="card p-4 transition-transform duration-300 hover:-translate-y-0.5">
              <div className="text-[11px] uppercase tracking-widest text-slate-500">{label}</div>
              <div className="mt-1 font-display text-2xl text-foreground">{value}</div>
            </div>
          </Reveal>
        ))}
      </div>

      {error ? (
        <div className="rounded-xl border border-rose-500/20 bg-rose-500/5 px-4 py-3 text-sm text-rose-300">{error}</div>
      ) : null}

      {active.length > 0 ? (
        <section>
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-500">In progress</h2>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {active.map((project, index) => (
              <Reveal key={project.id} delay={index * 0.05} y={20}>
                <ProjectCard project={project} />
              </Reveal>
            ))}
          </div>
        </section>
      ) : null}

      <section>
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-500">All projects</h2>
        {projects === null ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {[0, 1, 2].map((index) => (
              <div key={index} className="card h-44 animate-pulse bg-ink-850" />
            ))}
          </div>
        ) : projects.items.length === 0 ? (
          <div className="card flex flex-col items-center justify-center gap-4 px-6 py-16 text-center">
            <div className="grid h-14 w-14 place-items-center rounded-2xl bg-ember-500/10 text-2xl">🎬</div>
            <div>
              <h3 className="font-display text-xl text-foreground">No projects yet</h3>
              <p className="mt-1 text-sm text-slate-400">Paste a script and StoryForge will plan the scenes for you.</p>
            </div>
            <Link href="/projects/new" className="btn-primary">
              Create your first project
            </Link>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {projects.items.map((project, index) => (
              <Reveal key={project.id} delay={index * 0.04} y={20}>
                <ProjectCard project={project} />
              </Reveal>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
