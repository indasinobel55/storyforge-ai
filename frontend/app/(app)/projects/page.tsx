"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import ProjectDetail from "./ProjectDetail";

function ProjectRoute() {
  const searchParams = useSearchParams();
  const id = searchParams.get("id");
  if (!id) {
    return (
      <div className="card flex flex-col items-center gap-4 px-6 py-16 text-center">
        <div>
          <h1 className="font-display text-xl text-foreground">No project selected</h1>
          <p className="mt-1 text-sm text-slate-400">Open a project from your dashboard.</p>
        </div>
        <Link href="/dashboard" className="btn-primary">
          Go to dashboard
        </Link>
      </div>
    );
  }
  return <ProjectDetail projectId={id} />;
}

export default function ProjectsPage() {
  return (
    <Suspense fallback={<div className="card h-64 animate-pulse bg-ink-850" />}>
      <ProjectRoute />
    </Suspense>
  );
}
