"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, apiUrl } from "@/lib/api";
import { ACTIVE_STATUSES, formatDate, formatDuration, titleCase } from "@/lib/format";
import type { Project, Scene, Video, VideoList } from "@/lib/types";
import { ProgressBar, StatusPill } from "@/components/Status";

type Busy = string | null;

export default function ProjectDetailPage({ params }: { params: { id: string } }) {
  const router = useRouter();
  const [project, setProject] = useState<Project | null>(null);
  const [videos, setVideos] = useState<Video[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<Busy>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [draftPrompt, setDraftPrompt] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const fileInputs = useRef<Record<string, HTMLInputElement | null>>({});

  const load = useCallback(
    async (quiet = false) => {
      try {
        const [detail, videoList] = await Promise.all([
          api<Project>(`/api/projects/${params.id}`),
          api<VideoList>(`/api/videos?project_id=${params.id}&limit=200`).catch(() => ({ items: [], total: 0 })),
        ]);
        setProject(detail);
        setVideos(videoList.items);
        if (!quiet) setError(null);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Could not load this project");
      }
    },
    [params.id],
  );

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!project || !ACTIVE_STATUSES.has(project.status)) return;
    const timer = window.setInterval(() => void load(true), 2500);
    return () => window.clearInterval(timer);
  }, [project?.status, load, project]);

  const sceneVideoByScene = useMemo(() => {
    const map = new Map<string, Video>();
    for (const video of videos) {
      if (video.kind === "scene" && video.scene_id) map.set(video.scene_id, video);
    }
    return map;
  }, [videos]);

  const finalVideo = videos.find((video) => video.kind === "final") || null;
  const canEdit = project && !ACTIVE_STATUSES.has(project.status) && project.status !== "COMPLETED";

  async function action(name: string, path: string, success: string) {
    setBusy(name);
    setNotice(null);
    try {
      await api<Project>(`/api/projects/${params.id}${path}`, { method: "POST" });
      await load();
      setNotice(success);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Action failed");
    } finally {
      setBusy(null);
    }
  }

  async function remove() {
    if (!window.confirm("Delete this project and all of its media? This cannot be undone.")) return;
    setBusy("delete");
    try {
      await api(`/api/projects/${params.id}`, { method: "DELETE" });
      router.push("/dashboard");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Delete failed");
      setBusy(null);
    }
  }

  async function saveScene(scene: Scene) {
    setBusy(`scene-${scene.id}`);
    try {
      await api<Scene>(`/api/projects/${params.id}/scenes/${scene.id}`, {
        method: "PATCH",
        body: JSON.stringify({ prompt: draftPrompt }),
      });
      setEditing(null);
      await load(true);
      setNotice(`Scene ${scene.scene_number} prompt saved`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save the scene");
    } finally {
      setBusy(null);
    }
  }

  async function regeneratePrompt(scene: Scene) {
    setBusy(`regen-${scene.id}`);
    try {
      const updated = await api<Scene>(`/api/projects/${params.id}/scenes/${scene.id}/regenerate-prompt`, {
        method: "POST",
      });
      setDraftPrompt(updated.prompt);
      await load(true);
      setNotice(`Scene ${scene.scene_number} prompt regenerated`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not regenerate the prompt");
    } finally {
      setBusy(null);
    }
  }

  async function uploadAsset(kind: "reference" | "music" | "voiceover", file: File) {
    setBusy(`upload-${kind}`);
    try {
      const body = new FormData();
      body.append("file", file);
      await api(`/api/projects/${params.id}/assets?kind=${kind}`, { method: "POST", body });
      await load(true);
      setNotice(`${titleCase(kind)} asset uploaded`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Upload failed");
    } finally {
      setBusy(null);
      const input = fileInputs.current[kind];
      if (input) input.value = "";
    }
  }

  if (!project) {
    return error ? (
      <div className="rounded-xl border border-rose-500/20 bg-rose-500/5 px-4 py-3 text-sm text-rose-300">{error}</div>
    ) : (
      <div className="card h-64 animate-pulse bg-ink-850" />
    );
  }

  const running = ACTIVE_STATUSES.has(project.status);
  const succeeded = project.scenes.filter((scene) => scene.status === "SUCCEEDED").length;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <Link href="/dashboard" className="text-xs text-slate-500 hover:text-slate-300">
            ← Projects
          </Link>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <h1 className="font-display text-3xl text-foreground">{project.title}</h1>
            <StatusPill status={project.status} />
            <span className="chip bg-foreground/[0.04] text-slate-400">{project.execution_mode} execution</span>
          </div>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-400">
            {project.logline || "Planning the story into scenes."}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {project.status === "DRAFT" || project.status === "CANCELLED" ? (
            <button className="btn-primary" disabled={busy !== null} onClick={() => action("plan", "/plan", "Planning started")}>
              {busy === "plan" ? "Starting…" : "Start planning"}
            </button>
          ) : null}
          {project.status === "AWAITING_APPROVAL" ? (
            <>
              <button
                className="btn-primary"
                disabled={busy !== null}
                onClick={() => action("approve", "/approve", "Generation queued")}
              >
                {busy === "approve" ? "Approving…" : "Approve & generate"}
              </button>
              <button className="btn-secondary" disabled={busy !== null} onClick={() => action("replan", "/plan", "Replanning")}>
                Replan
              </button>
            </>
          ) : null}
          {running ? (
            <>
              <button className="btn-secondary" disabled={busy !== null} onClick={() => action("pause", "/pause", "Pausing after current scene")}>
                Pause
              </button>
              <button className="btn-danger" disabled={busy !== null} onClick={() => action("cancel", "/cancel", "Cancelled")}>
                Cancel
              </button>
            </>
          ) : null}
          {project.status === "PAUSED" ? (
            <button className="btn-primary" disabled={busy !== null} onClick={() => action("resume", "/resume", "Resumed")}>
              Resume
            </button>
          ) : null}
          {project.status === "FAILED" || project.status === "CANCELLED" || project.status === "PAUSED" ? (
            <button className="btn-secondary" disabled={busy !== null} onClick={() => action("retry", "/retry", "Retry queued")}>
              Retry
            </button>
          ) : null}
          {project.status === "COMPLETED" && finalVideo?.download_url ? (
            <a className="btn-primary" href={apiUrl(finalVideo.download_url)}>
              Download MP4
            </a>
          ) : null}
          <button className="btn-ghost text-rose-300" disabled={busy !== null || running} onClick={remove}>
            Delete
          </button>
        </div>
      </div>

      {error ? (
        <div className="rounded-xl border border-rose-500/20 bg-rose-500/5 px-4 py-3 text-sm text-rose-300">
          {error}
          <button className="ml-3 text-xs underline" onClick={() => setError(null)}>
            dismiss
          </button>
        </div>
      ) : null}
      {notice ? <div className="rounded-xl border border-mint-500/20 bg-mint-500/5 px-4 py-3 text-sm text-mint-400">{notice}</div> : null}
      {project.error ? (
        <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-sm text-amber-200">
          {project.error}
        </div>
      ) : null}

      <div className="card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-sm text-slate-300">
            {succeeded} / {project.scenes.length || project.target_scene_count} scenes · {formatDuration(project.target_duration_seconds)}{" "}
            target · {project.resolution}
          </div>
          <div className="text-sm font-semibold text-foreground">{project.progress}%</div>
        </div>
        <ProgressBar value={project.progress} className="mt-3 h-2" />
        <div className="mt-3 flex flex-wrap gap-4 text-[11px] uppercase tracking-wide text-slate-500">
          <span>Provider: {project.provider}</span>
          <span>Executor: {project.executor || "auto"}</span>
          <span>Created {formatDate(project.created_at)}</span>
          {project.completed_at ? <span>Completed {formatDate(project.completed_at)}</span> : null}
        </div>
      </div>

      {finalVideo ? (
        <div className="card overflow-hidden">
          <div className="flex items-center justify-between border-b border-foreground/10 px-5 py-3">
            <div>
              <h2 className="font-display text-lg text-foreground">Final video</h2>
              <p className="text-xs text-slate-500">
                {finalVideo.width}×{finalVideo.height} · {formatDuration(finalVideo.duration_seconds)} ·{" "}
                {finalVideo.has_audio ? "with audio" : "silent"}
              </p>
            </div>
            <div className="flex gap-2">
              <a href={apiUrl(finalVideo.download_url)} className="btn-secondary px-3 py-1.5 text-xs" download>
                Download
              </a>
            </div>
          </div>
          <video
            className="max-h-[70vh] w-full bg-black"
            controls
            playsInline
            preload="metadata"
            poster={apiUrl(finalVideo.thumbnail_url)}
            src={apiUrl(finalVideo.stream_url)}
          />
        </div>
      ) : null}

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500">Scene plan</h2>
          {canEdit ? <span className="text-[11px] text-slate-500">Prompts are editable before generation</span> : null}
        </div>
        {project.scenes.length === 0 ? (
          <div className="card px-5 py-10 text-center text-sm text-slate-500">
            {project.status === "PLANNING" ? "The planner is building the scene list…" : "No scenes yet."}
          </div>
        ) : (
          <div className="space-y-3">
            {project.scenes.map((scene) => {
              const clip = sceneVideoByScene.get(scene.id);
              const isEditing = editing === scene.id;
              return (
                <div key={scene.id} className="card p-4">
                  <div className="flex flex-wrap items-start gap-4">
                    {clip?.thumbnail_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={apiUrl(clip.thumbnail_url)}
                        alt={`Scene ${scene.scene_number}`}
                        className="h-20 w-32 rounded-lg object-cover"
                      />
                    ) : (
                      <div className="grid h-20 w-32 place-items-center rounded-lg bg-ink-850 text-xs text-slate-600">
                        {scene.status === "GENERATING" ? "Rendering…" : "No clip"}
                      </div>
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                          Scene {scene.scene_number}
                        </span>
                        <StatusPill status={scene.status} />
                        <span className="text-xs text-slate-500">{scene.duration}s</span>
                        {scene.attempt_count > 0 ? (
                          <span className="text-[11px] text-slate-500">attempt {scene.attempt_count}</span>
                        ) : null}
                      </div>
                      <h3 className="mt-1 text-sm font-semibold text-foreground">{scene.title}</h3>
                      {isEditing ? (
                        <div className="mt-2 space-y-2">
                          <textarea
                            rows={5}
                            className="input resize-y text-xs leading-relaxed"
                            value={draftPrompt}
                            onChange={(event) => setDraftPrompt(event.target.value)}
                          />
                          <div className="flex flex-wrap gap-2">
                            <button
                              className="btn-primary px-3 py-1.5 text-xs"
                              disabled={busy !== null}
                              onClick={() => saveScene(scene)}
                            >
                              {busy === `scene-${scene.id}` ? "Saving…" : "Save prompt"}
                            </button>
                            <button className="btn-secondary px-3 py-1.5 text-xs" onClick={() => setEditing(null)}>
                              Cancel
                            </button>
                            <button
                              className="btn-ghost px-3 py-1.5 text-xs"
                              disabled={busy !== null}
                              onClick={() => regeneratePrompt(scene)}
                            >
                              Regenerate prompt
                            </button>
                          </div>
                        </div>
                      ) : (
                        <p className="mt-1 line-clamp-3 text-xs leading-relaxed text-slate-400">{scene.prompt}</p>
                      )}
                      {scene.error ? <p className="mt-2 text-xs text-rose-300">{scene.error}</p> : null}
                    </div>
                    <div className="flex flex-col items-end gap-2">
                      {clip?.stream_url ? (
                        <a className="btn-secondary px-3 py-1.5 text-xs" href={apiUrl(clip.stream_url)} target="_blank" rel="noreferrer">
                          Open clip
                        </a>
                      ) : null}
                      {canEdit && scene.status === "FAILED" ? (
                        <button
                          className="btn-secondary px-3 py-1.5 text-xs"
                          disabled={busy !== null}
                          onClick={() => action(`scene-retry-${scene.id}`, `/scenes/${scene.id}/retry`, "Scene retry queued")}
                        >
                          Retry scene
                        </button>
                      ) : null}
                      {canEdit && !isEditing ? (
                        <button
                          className="btn-ghost px-3 py-1.5 text-xs"
                          onClick={() => {
                            setEditing(scene.id);
                            setDraftPrompt(scene.prompt);
                          }}
                        >
                          Edit prompt
                        </button>
                      ) : null}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {canEdit ? (
        <section className="card p-5">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500">Project assets</h2>
          <p className="mt-1 text-xs text-slate-500">
            Music and voiceover are mixed during cloud/local assembly. Reference images guide scene prompts.
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            {(["reference", "music", "voiceover"] as const).map((kind) => (
              <div key={kind} className="rounded-xl border border-foreground/10 bg-ink-850/70 p-3">
                <div className="text-sm text-slate-200">{titleCase(kind)}</div>
                <div className="mt-1 text-[11px] text-slate-500">
                  {kind === "reference" ? "JPG, PNG or WebP" : "MP3, WAV, M4A or OGG"}
                </div>
                <input
                  ref={(element) => {
                    fileInputs.current[kind] = element;
                  }}
                  type="file"
                  className="mt-2 block w-full text-xs text-slate-400 file:mr-2 file:rounded-lg file:border-0 file:bg-foreground/[0.08] file:px-2.5 file:py-1.5 file:text-xs file:text-slate-200"
                  accept={kind === "reference" ? "image/jpeg,image/png,image/webp" : "audio/mpeg,audio/wav,audio/mp4,audio/ogg"}
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void uploadAsset(kind, file);
                  }}
                />
                {busy === `upload-${kind}` ? <div className="mt-2 text-[11px] text-ember-400">Uploading…</div> : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
