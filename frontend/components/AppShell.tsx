"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "./AuthProvider";
import { ModeBadge } from "./ModeBadge";
import { ThemeToggle } from "./ThemeToggle";
import { PageTransition } from "./motion/PageTransition";
import { ScrollProgress } from "./motion/ScrollProgress";

const NAV = [
  { href: "/dashboard", label: "Projects" },
  { href: "/videos", label: "Videos" },
  { href: "/settings", label: "Settings" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.replace(`/login?next=${encodeURIComponent(pathname || "/dashboard")}`);
  }, [loading, user, router, pathname]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="flex items-center gap-3 text-sm text-slate-400">
          <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-ember-500" />
          Loading studio…
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-foreground/10 bg-canvas/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3 sm:px-6">
          <Link href="/dashboard" className="flex items-center gap-2.5">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-accent text-lg font-black text-accent-ink shadow-glow-sm">
              S
            </span>
            <span className="hidden font-display text-lg tracking-wide text-foreground sm:block">StoryForge</span>
          </Link>
          <nav className="ml-2 hidden items-center gap-1 md:flex">
            {NAV.map((item) => {
              const active = pathname?.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`rounded-lg px-3 py-2 text-sm transition ${
                    active
                      ? "bg-accent/15 font-semibold text-foreground shadow-[inset_0_-2px_0_0_rgb(var(--cv-accent))]"
                      : "text-muted hover:bg-foreground/[0.05] hover:text-foreground"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <ThemeToggle />
            <ModeBadge />
            <div className="hidden text-right sm:block">
              <div className="text-sm font-medium text-foreground">{user.display_name}</div>
              <div className="text-[11px] text-muted">{user.email}</div>
            </div>
            <button className="btn-ghost px-3 py-2 text-xs" onClick={() => void logout().then(() => router.push("/"))}>
              Sign out
            </button>
            <button
              className="btn-ghost px-2 py-2 md:hidden"
              aria-label="Toggle navigation"
              onClick={() => setMenuOpen((value) => !value)}
            >
              ☰
            </button>
          </div>
        </div>
        {menuOpen ? (
          <nav className="flex border-t border-foreground/10 px-4 py-2 md:hidden">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMenuOpen(false)}
                className="flex-1 rounded-lg px-3 py-2 text-center text-sm text-muted hover:bg-foreground/[0.05] hover:text-foreground"
              >
                {item.label}
              </Link>
            ))}
          </nav>
        ) : null}
      </header>
      <ScrollProgress />
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <PageTransition key={pathname}>{children}</PageTransition>
      </main>
    </div>
  );
}
