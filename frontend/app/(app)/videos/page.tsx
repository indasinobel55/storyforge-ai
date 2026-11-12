"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, apiUrl } from "@/lib/api";
import { formatBytes, formatDate, formatDuration } from "@/lib/format";
import type { Video, VideoList } from "@/lib/types";
import { StatusPill } from "@/components/Status";
import { Reveal } from "@/components/motion/Reveal";

export default function VideosPage() {
  const [videos, setVideos] = useState<VideoList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Video | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setVideos(await api<VideoList>("/api/videos?limit=200"));
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load videos");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function remove(video: Video) {
    if (!window.confirm(`Delete ${video.filename}?`)) return;
    setBusy(video.id);
    try {
      await api(`/api/videos/${video.id}`, { method: "DELETE" });
      if (selected?.id === video.id) setSelected(null);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Delete failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl text-foreground">Videos</h1>
          <p className="mt-1 text-sm text-slate-400">Final films and individual scene clips from your projects.</p>
        </div>
        <Link href="/projects/new" className="btn-primary">
          New project
        </Link>
      </div>

      {error ? <div className="rounded-xl bg-rose-500/10 px-4 py-3 text-sm text-rose-300">{error}</div> : null}

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-3">
          {videos === null ? (
            <div className="card h-64 animate-pulse bg-ink-850" />
          ) : videos.items.length === 0 ? (
            <div className="card px-6 py-16 text-center text-sm text-slate-400">No videos yet. Create a project to get started.</div>
          ) : (
            videos.items.map((video, index) => (
              <Reveal key={video.id} delay={index * 0.04} y={18}>
                <div
                  className={`card flex flex-wrap items-center gap-4 p-4 transition ${
                    selected?.id === video.id ? "border-ember-500/40" : ""
                  }`}
                >
                {video.thumbnail_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={apiUrl(video.thumbnail_url)} alt="" className="h-16 w-28 rounded-lg object-cover" />
                ) : (
                  <div className="grid h-16 w-28 place-items-center rounded-lg bg-ink-850 text-[10px] uppercase tracking-wide text-slate-600">
                    {video.kind}
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-semibold text-foreground">{video.filename}</span>
                    <StatusPill status={video.kind === "final" ? "COMPLETED" : "SUCCEEDED"} />
                  </div>
                  <div className="mt-1 text-[11px] text-slate-500">
                    {video.width}×{video.height} · {formatDuration(video.duration_seconds)} ·{" "}
                    {formatBytes(video.size_bytes)} · {formatDate(video.created_at)}
                  </div>
                </div>
                <div className="flex gap-2">
                  <button className="btn-secondary px-3 py-1.5 text-xs" onClick={() => setSelected(video)}>
                    Preview
                  </button>
                  <a className="btn-ghost px-3 py-1.5 text-xs" href={apiUrl(video.download_url)} download>
                    Download
                  </a>
                  <button
                    className="btn-ghost px-2 py-1.5 text-xs text-rose-300"
                    disabled={busy === video.id}
                    onClick={() => remove(video)}
                  >
                    Delete
                  </button>
                </div>
              </div>
                </Reveal>
              ))
          )}
        </div>

        <div className="card h-fit overflow-hidden lg:sticky lg:top-24">
          {selected ? (
            <>
              <div className="flex items-center justify-between border-b border-foreground/10 px-4 py-3">
                <span className="truncate text-sm font-medium text-foreground">{selected.filename}</span>
                <a className="text-xs text-ember-400" href={apiUrl(selected.download_url)} download>
                  Download
                </a>
              </div>
              <video
                key={selected.id}
                className="aspect-video w-full bg-black"
                controls
                playsInline
                preload="metadata"
                poster={apiUrl(selected.thumbnail_url)}
                src={apiUrl(selected.stream_url)}
              />
              <div className="space-y-1 px-4 py-3 text-[11px] text-slate-500">
                <div>
                  {selected.width}×{selected.height} · {formatDuration(selected.duration_seconds)} ·{" "}
                  {selected.has_audio ? "audio" : "no audio"}
                </div>
                <div className="break-all">SHA-256: {selected.checksum_sha256 || "—"}</div>
              </div>
            </>
          ) : (
            <div className="px-6 py-16 text-center text-sm text-slate-500">Select a video to preview it here.</div>
          )}
        </div>
      </div>
    </div>
  );
}
