"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { API_BASE, api } from "@/lib/api";
import { formatBytes, formatDate, titleCase } from "@/lib/format";
import type {
  ExecutionStatus,
  LocalToken,
  LocalTokenCreated,
  Provider,
  PublicConfig,
  Usage,
} from "@/lib/types";
import { Reveal } from "@/components/motion/Reveal";

export default function SettingsPage() {
  const router = useRouter();
  const { user, setUser, logout } = useAuth();
  const [usage, setUsage] = useState<Usage | null>(null);
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [execution, setExecution] = useState<ExecutionStatus | null>(null);
  const [tokens, setTokens] = useState<LocalToken[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [createdToken, setCreatedToken] = useState<LocalTokenCreated | null>(null);
  const [displayName, setDisplayName] = useState(user?.display_name || "");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [deletePassword, setDeletePassword] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [usageData, configData, executionData, tokensData, providersData] = await Promise.all([
        api<Usage>("/api/usage"),
        api<PublicConfig>("/api/config"),
        api<ExecutionStatus>("/api/execution/status"),
        api<LocalToken[]>("/api/execution/tokens"),
        api<Provider[]>("/api/providers"),
      ]);
      setUsage(usageData);
      setConfig(configData);
      setExecution(executionData);
      setTokens(tokensData);
      setProviders(providersData);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load settings");
    }
  }, []);

  useEffect(() => {
    if (user) setDisplayName(user.display_name);
  }, [user]);

  useEffect(() => {
    void load();
  }, [load]);

  async function run(name: string, task: () => Promise<void>, success: string) {
    setBusy(name);
    setError(null);
    setNotice(null);
    try {
      await task();
      setNotice(success);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Action failed");
    } finally {
      setBusy(null);
    }
  }

  async function saveProfile(event: React.FormEvent) {
    event.preventDefault();
    await run(
      "profile",
      async () => {
        const updated = await api<{ id: string }>("/api/auth/profile", {
          method: "PATCH",
          body: JSON.stringify({ display_name: displayName }),
        });
        if (user) setUser({ ...user, display_name: (updated as { display_name?: string }).display_name || displayName });
      },
      "Profile updated",
    );
  }

  async function changePassword(event: React.FormEvent) {
    event.preventDefault();
    await run(
      "password",
      async () => {
        await api("/api/auth/password", {
          method: "POST",
          body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
        });
        setCurrentPassword("");
        setNewPassword("");
      },
      "Password updated. Other sessions were signed out.",
    );
  }

  async function createToken() {
    await run(
      "token",
      async () => {
        const created = await api<LocalTokenCreated>("/api/execution/token", {
          method: "POST",
          body: JSON.stringify({ label: "Local worker" }),
        });
        setCreatedToken(created);
        setTokens((items) => [created, ...items]);
      },
      "Local execution token created",
    );
  }

  async function revokeToken(id: string) {
    await run(
      "revoke",
      async () => {
        await api(`/api/execution/tokens/${id}`, { method: "DELETE" });
        setTokens((items) => items.filter((item) => item.id !== id));
        if (createdToken?.id === id) setCreatedToken(null);
      },
      "Token revoked",
    );
  }

  async function connectProvider(provider: string) {
    await run(
      `provider-${provider}`,
      async () => {
        await api(`/api/providers/${provider}/connect`, {
          method: "POST",
          body: JSON.stringify({ accept_terms: true }),
        });
        await load();
      },
      "Provider connected",
    );
  }

  async function verifyProvider(provider: string) {
    await run(
      `verify-${provider}`,
      async () => {
        await api(`/api/providers/${provider}/verify`, { method: "POST" });
        await load();
      },
      "Provider verified",
    );
  }

  async function deleteAccount() {
    if (!window.confirm("Permanently delete your account, projects and media?")) return;
    await run(
      "delete-account",
      async () => {
        await api("/api/auth/account", { method: "DELETE", body: JSON.stringify({ password: deletePassword }) });
        await logout();
        router.push("/");
      },
      "Account deleted",
    );
  }

  const command = createdToken
    ? `python -m local_agent --api-url ${API_BASE} --token ${createdToken.token}`
    : `python -m local_agent --api-url ${API_BASE}`;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl text-foreground">Settings</h1>
        <p className="mt-1 text-sm text-slate-400">Account, execution mode, provider accounts and data usage.</p>
      </div>

      {error ? <div className="rounded-xl bg-rose-500/10 px-4 py-3 text-sm text-rose-300">{error}</div> : null}
      {notice ? <div className="rounded-xl bg-mint-500/10 px-4 py-3 text-sm text-mint-400">{notice}</div> : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <Reveal>
        <section className="card p-5">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500">Profile</h2>
          <form onSubmit={saveProfile} className="mt-4 space-y-3">
            <div>
              <label className="label">Display name</label>
              <input className="input" value={displayName} onChange={(event) => setDisplayName(event.target.value)} required />
            </div>
            <div>
              <label className="label">Email</label>
              <input className="input opacity-70" value={user?.email || ""} readOnly />
            </div>
            <button type="submit" className="btn-primary" disabled={busy !== null}>
              {busy === "profile" ? "Saving…" : "Save profile"}
            </button>
          </form>
        </section>
        </Reveal>

        <Reveal delay={0.08}>
        <section className="card p-5">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500">Usage</h2>
          <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
            {[
              ["Projects", usage?.projects_total ?? "—"],
              ["Videos", usage?.videos_total ?? "—"],
              ["Scenes generated", usage?.scenes_generated ?? "—"],
              ["Generations this month", usage?.generations_this_month ?? "—"],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-xl bg-ink-850/80 p-3">
                <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
                <div className="mt-1 font-display text-xl text-foreground">{value}</div>
              </div>
            ))}
          </div>
          <div className="mt-4">
            <div className="flex justify-between text-xs text-slate-400">
              <span>Storage</span>
              <span>
                {usage ? formatBytes(usage.storage_used_bytes) : "—"} /{" "}
                {usage ? formatBytes(usage.storage_quota_bytes) : "—"}
              </span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-foreground/[0.08]">
              <div
                className="h-full bg-ember-500"
                style={{
                  width: usage ? `${Math.min(100, (usage.storage_used_bytes / Math.max(1, usage.storage_quota_bytes)) * 100)}%` : "0%",
                }}
              />
            </div>
          </div>
        </section>
        </Reveal>
      </div>

      <section className="card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500">Execution</h2>
            <p className="mt-1 text-sm text-slate-300">
              Active mode:{" "}
              <span className="font-semibold text-ember-400">{execution?.execution_mode ?? "…"}</span>
              {config?.taaft_enabled ? null : " · real TAAFT automation disabled"}
            </p>
          </div>
          <button className="btn-secondary" onClick={createToken} disabled={busy !== null || !execution?.local_workers_enabled}>
            Create local token
          </button>
        </div>

        {execution ? (
          <p className="mt-3 rounded-xl bg-foreground/[0.04] px-3 py-2 text-xs leading-relaxed text-slate-400">
            {execution.instructions}
          </p>
        ) : null}

        {createdToken ? (
          <div className="mt-4 rounded-xl border border-mint-500/25 bg-mint-500/5 p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-mint-400">
              Copy this token now — it is only shown once
            </div>
            <code className="mt-2 block break-all rounded-lg bg-foreground/[0.06] px-3 py-2 text-xs text-slate-200">
              {createdToken.token}
            </code>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <code className="min-w-0 flex-1 break-all rounded-lg bg-foreground/[0.06] px-3 py-2 text-[11px] text-slate-300">
                {command}
              </code>
              <button
                className="btn-secondary px-3 py-1.5 text-xs"
                onClick={() => void navigator.clipboard?.writeText(command)}
              >
                Copy command
              </button>
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
              Keep the machine on while jobs run. Set <code>EXECUTION_MODE=local</code> on the backend and start the
              local agent from the project root.
            </p>
          </div>
        ) : null}

        <div className="mt-4 space-y-2">
          {tokens.length === 0 ? (
            <p className="text-sm text-slate-500">No active local execution tokens.</p>
          ) : (
            tokens.map((token) => (
              <div key={token.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-foreground/10 bg-ink-850/70 px-3 py-2 text-sm">
                <span className="font-medium text-slate-200">{token.label}</span>
                <span className="text-[11px] text-slate-500">
                  created {formatDate(token.created_at)} · last used {formatDate(token.last_used_at)}
                </span>
                <button
                  className="ml-auto text-xs text-rose-300 hover:underline"
                  disabled={busy !== null}
                  onClick={() => revokeToken(token.id)}
                >
                  Revoke
                </button>
              </div>
            ))
          )}
        </div>
      </section>

      <section className="card p-5">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500">Providers</h2>
        <div className="mt-4 space-y-3">
          {providers.map((provider) => (
            <div key={provider.provider} className="rounded-xl border border-foreground/10 bg-ink-850/70 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-foreground">{provider.display_name}</span>
                <span className={`chip ${provider.connected ? "bg-mint-500/15 text-mint-400" : "bg-foreground/[0.04] text-slate-400"}`}>
                  {provider.connected ? "Connected" : titleCase(provider.status)}
                </span>
                {provider.requires_consent ? <span className="chip bg-amber-500/10 text-amber-300">Gated</span> : null}
                <div className="ml-auto flex gap-2">
                  {provider.connectable ? (
                    <button
                      className="btn-secondary px-3 py-1.5 text-xs"
                      disabled={busy !== null}
                      onClick={() => connectProvider(provider.provider)}
                    >
                      {provider.connected ? "Reconnect" : "Connect"}
                    </button>
                  ) : null}
                  {provider.connected ? (
                    <button
                      className="btn-ghost px-3 py-1.5 text-xs"
                      disabled={busy !== null}
                      onClick={() => verifyProvider(provider.provider)}
                    >
                      Verify
                    </button>
                  ) : null}
                </div>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-slate-400">{provider.description}</p>
              {provider.notes ? <p className="mt-1 text-[11px] leading-relaxed text-amber-200/70">{provider.notes}</p> : null}
              {provider.usage ? (
                <p className="mt-1 text-[11px] text-slate-500">Usage: {JSON.stringify(provider.usage)}</p>
              ) : null}
            </div>
          ))}
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card p-5">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500">Change password</h2>
          <form onSubmit={changePassword} className="mt-4 space-y-3">
            <div>
              <label className="label">Current password</label>
              <input
                type="password"
                className="input"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                required
              />
            </div>
            <div>
              <label className="label">New password</label>
              <input
                type="password"
                minLength={8}
                className="input"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                required
              />
            </div>
            <button type="submit" className="btn-secondary" disabled={busy !== null}>
              {busy === "password" ? "Updating…" : "Update password"}
            </button>
          </form>
        </section>

        <section className="card border-rose-500/15 p-5">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-rose-300">Danger zone</h2>
          <p className="mt-2 text-xs leading-relaxed text-slate-400">
            Deleting your account removes projects, generated media, sessions and provider credentials. This cannot be
            undone.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <input
              type="password"
              className="input max-w-xs"
              placeholder="Confirm with password"
              value={deletePassword}
              onChange={(event) => setDeletePassword(event.target.value)}
            />
            <button className="btn-danger" disabled={busy !== null || !deletePassword} onClick={deleteAccount}>
              {busy === "delete-account" ? "Deleting…" : "Delete account"}
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
