"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, meta } from "@/lib/api";
import type { Project, PublicConfig } from "@/lib/types";

interface CharacterDraft {
  name: string;
  description: string;
  age_range: string;
}

const ORIENTATIONS = [
  { value: "landscape", label: "Landscape · 16:9", ratio: "16:9", resolution: "1280x720" },
  { value: "portrait", label: "Portrait · 9:16", ratio: "9:16", resolution: "720x1280" },
  { value: "square", label: "Square · 1:1", ratio: "1:1", resolution: "720x720" },
];

export default function NewProjectPage() {
  const router = useRouter();
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [title, setTitle] = useState("");
  const [script, setScript] = useState("");
  const [genre, setGenre] = useState("");
  const [style, setStyle] = useState("cinematic photorealistic short film");
  const [orientation, setOrientation] = useState("landscape");
  const [sceneCount, setSceneCount] = useState(6);
  const [sceneSeconds, setSceneSeconds] = useState(8);
  const [autoStart, setAutoStart] = useState(false);
  const [voiceover, setVoiceover] = useState("");
  const [music, setMusic] = useState("");
  const [characters, setCharacters] = useState<CharacterDraft[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    meta
      .config()
      .then(setConfig)
      .catch(() => undefined);
  }, []);

  const orientationMeta = ORIENTATIONS.find((item) => item.value === orientation) || ORIENTATIONS[0];
  const targetDuration = sceneCount * sceneSeconds;

  function updateCharacter(index: number, patch: Partial<CharacterDraft>) {
    setCharacters((items) => items.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const project = await api<Project>("/api/projects", {
        method: "POST",
        body: JSON.stringify({
          title: title.trim(),
          script,
          genre: genre.trim() || null,
          style,
          orientation,
          aspect_ratio: orientationMeta.ratio,
          resolution: orientationMeta.resolution,
          target_scene_count: sceneCount,
          scene_seconds: sceneSeconds,
          target_duration_seconds: targetDuration,
          auto_start: autoStart,
          start_planning: true,
          provider: "simulated",
          voiceover_instructions: voiceover.trim() || null,
          music_instructions: music.trim() || null,
          characters: characters
            .filter((character) => character.name.trim())
            .map((character) => ({
              name: character.name.trim(),
              description: character.description.trim(),
              age_range: character.age_range.trim() || null,
            })),
        }),
      });
      router.push(`/projects/${project.id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create the project");
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <Link href="/dashboard" className="text-xs text-slate-500 hover:text-slate-300">
          ← Back to projects
        </Link>
        <h1 className="mt-2 font-display text-3xl text-foreground">New project</h1>
        <p className="mt-1 text-sm text-slate-400">
          Execution mode: <span className="text-ember-400">{config?.execution_mode ?? "…"}</span>. The planner runs
          first; you can approve the scene list before generation.
        </p>
      </div>

      <form onSubmit={submit} className="space-y-6">
        <section className="card card-hl space-y-4 p-5">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500">Story</h2>
          <div>
            <label className="label" htmlFor="title">
              Title
            </label>
            <input id="title" required maxLength={200} className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="script">
              Script or story
            </label>
            <textarea
              id="script"
              required
              minLength={20}
              rows={9}
              className="input resize-y leading-relaxed"
              placeholder="Paste the full story, narration or screenplay. The planner will break it into scenes."
              value={script}
              onChange={(e) => setScript(e.target.value)}
            />
            <div className="mt-1 text-right text-[11px] text-slate-500">{script.length} characters</div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label" htmlFor="genre">
                Genre (optional)
              </label>
              <input id="genre" className="input" value={genre} onChange={(e) => setGenre(e.target.value)} />
            </div>
            <div>
              <label className="label" htmlFor="style">
                Visual style
              </label>
              <input id="style" className="input" value={style} onChange={(e) => setStyle(e.target.value)} />
            </div>
          </div>
        </section>

        <section className="card space-y-4 p-5">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500">Timeline</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label">Orientation</label>
              <select className="input" value={orientation} onChange={(e) => setOrientation(e.target.value)}>
                {ORIENTATIONS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Resolution</label>
              <input className="input opacity-70" value={orientationMeta.resolution} readOnly />
            </div>
            <div>
              <label className="label" htmlFor="scenes">
                Scenes: {sceneCount}
              </label>
              <input
                id="scenes"
                type="range"
                min={1}
                max={config?.max_scenes_per_project ?? 20}
                value={sceneCount}
                onChange={(e) => setSceneCount(Number(e.target.value))}
                className="w-full accent-ember-500"
              />
            </div>
            <div>
              <label className="label">Seconds per scene: {sceneSeconds}s</label>
              <input
                type="range"
                min={1}
                max={config?.max_scene_seconds ?? 10}
                value={sceneSeconds}
                onChange={(e) => setSceneSeconds(Number(e.target.value))}
                className="w-full accent-ember-500"
              />
            </div>
          </div>
          <div className="flex items-center justify-between rounded-xl bg-foreground/[0.04] px-3 py-2 text-sm">
            <span className="text-slate-400">Target duration</span>
            <span className="font-semibold text-foreground">{targetDuration}s</span>
          </div>
        </section>

        <section className="card space-y-4 p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500">Characters</h2>
            <button
              type="button"
              className="btn-secondary px-3 py-1.5 text-xs"
              onClick={() => setCharacters((items) => [...items, { name: "", description: "", age_range: "" }])}
            >
              Add character
            </button>
          </div>
          {characters.length === 0 ? (
            <p className="text-sm text-slate-500">
              Optional. Add characters to improve visual consistency and the story bible.
            </p>
          ) : (
            <div className="space-y-3">
              {characters.map((character, index) => (
                <div key={index} className="grid gap-3 rounded-xl border border-foreground/10 bg-ink-850/70 p-3 sm:grid-cols-[1fr_1.6fr_auto]">
                  <input
                    className="input"
                    placeholder="Name"
                    value={character.name}
                    onChange={(e) => updateCharacter(index, { name: e.target.value })}
                  />
                  <input
                    className="input"
                    placeholder="Description / appearance"
                    value={character.description}
                    onChange={(e) => updateCharacter(index, { description: e.target.value })}
                  />
                  <button
                    type="button"
                    className="btn-ghost px-3 text-rose-300"
                    onClick={() => setCharacters((items) => items.filter((_, i) => i !== index))}
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="card space-y-4 p-5">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500">Audio and workflow</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label">Voiceover notes</label>
              <textarea rows={3} className="input resize-y" value={voiceover} onChange={(e) => setVoiceover(e.target.value)} />
            </div>
            <div>
              <label className="label">Music notes</label>
              <textarea rows={3} className="input resize-y" value={music} onChange={(e) => setMusic(e.target.value)} />
            </div>
          </div>
          <label className="flex items-start gap-3 rounded-xl border border-foreground/10 bg-ink-850/70 p-3">
            <input
              type="checkbox"
              checked={autoStart}
              onChange={(e) => setAutoStart(e.target.checked)}
              className="mt-0.5 h-4 w-4 accent-ember-500"
            />
            <span className="text-sm text-slate-300">
              Start generating immediately after planning
              <span className="mt-0.5 block text-xs text-slate-500">
                Leave unchecked to review and edit the scene list first. Approval starts generation.
              </span>
            </span>
          </label>
          <p className="rounded-xl bg-amber-500/5 px-3 py-2 text-xs leading-relaxed text-amber-200/80">
            Development provider: <strong>simulated</strong>. It renders real MP4 test clips. TAAFT automation remains
            disabled pending written provider authorization.
          </p>
        </section>

        {error ? <p className="rounded-xl bg-rose-500/10 px-4 py-3 text-sm text-rose-300">{error}</p> : null}

        <div className="flex items-center justify-end gap-3">
          <Link href="/dashboard" className="btn-secondary">
            Cancel
          </Link>
          <button type="submit" disabled={busy} className="btn-primary px-6">
            {busy ? "Creating…" : "Create and plan"}
          </button>
        </div>
      </form>
    </div>
  );
}
