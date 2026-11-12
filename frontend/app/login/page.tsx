"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { auth } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const { user, refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (user) router.replace("/dashboard");
  }, [user, router]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await auth.login(email, password);
      await refresh();
      router.push("/dashboard");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Sign in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-md">
        <Link href="/" className="mb-8 flex items-center justify-center gap-2.5">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-ember-500 text-xl font-black text-ink-950">S</span>
          <span className="font-display text-xl tracking-wide text-foreground">StoryForge AI</span>
        </Link>
        <form onSubmit={submit} className="card card-hl p-7">
          <h1 className="font-display text-2xl text-foreground">Welcome back</h1>
          <p className="mt-1 text-sm text-slate-400">Sign in to continue your productions.</p>
          <div className="mt-6 space-y-4">
            <div>
              <label className="label" htmlFor="email">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                className="input"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>
            <div>
              <label className="label" htmlFor="password">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                className="input"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>
          </div>
          {error ? <p className="mt-4 rounded-xl bg-rose-500/10 px-3 py-2 text-sm text-rose-300">{error}</p> : null}
          <button type="submit" disabled={busy} className="btn-primary mt-6 w-full py-3">
            {busy ? "Signing in…" : "Sign in"}
          </button>
          <p className="mt-5 text-center text-sm text-slate-400">
            New here?{" "}
            <Link href="/register" className="link">
              Create an account
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
