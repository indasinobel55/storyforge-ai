"use client";

import Link from "next/link";
import { motion, useMotionValue, useReducedMotion, useScroll, useSpring, useTransform } from "framer-motion";
import { useEffect, useRef } from "react";
import { Reveal } from "@/components/motion/Reveal";
import { ScrollProgress } from "@/components/motion/ScrollProgress";
import { TiltCard } from "@/components/motion/TiltCard";
import { Parallax } from "@/components/motion/Parallax";
import { Marquee } from "@/components/motion/Marquee";
import { Counter } from "@/components/motion/Counter";

const FEATURES = [
  {
    number: "01",
    tag: "PLANNER",
    title: "Script to scene plan",
    body: "A deterministic planner turns your story into a consistent shot list — characters, prompts, camera, lighting and continuity notes for every 8-second scene.",
  },
  {
    number: "02",
    tag: "CONTINUITY",
    title: "Frame-true continuity",
    body: "The last frame of every scene is analyzed by a vision model. A continuation passage is written and injected into the next prompt, so scenes flow like one film.",
  },
  {
    number: "03",
    tag: "EXECUTION",
    title: "Durable, resumable jobs",
    body: "Planning, generation, download, assembly and validation run as leased jobs. A crashed worker resumes from the last checkpoint instead of starting over.",
  },
  {
    number: "04",
    tag: "VALIDATION",
    title: "Real validation",
    body: "Every clip and the final cut are probed server-side for decodability, duration and resolution before a project is ever marked complete.",
  },
];

const PIPELINE = [
  { id: "PLAN", body: "Script → shot list, character bible, continuity map", x: "18%", z: "translateZ(60px)" },
  { id: "GENERATE", body: "Scene loop: render → download → probe → analyze last frame → continue", x: "34%", z: "translateZ(120px)" },
  { id: "ASSEMBLE", body: "Crossfades, music and voiceover mix, final validation", x: "50%", z: "translateZ(180px)" },
];

const MARQUEE_A = [
  "FASTAPI",
  "NEXT.JS 14 PWA",
  "SQLALCHEMY 2.0",
  "FFMPEG PIPELINE",
  "WEBSOCKET EVENTS",
  "SIGNED MEDIA URLS",
];

const MARQUEE_B = [
  "CSRF DOUBLE-SUBMIT",
  "BCRYPT SESSIONS",
  "IDEMPOTENCY KEYS",
  "WORKER HEARTBEATS",
  "PER-USER ISOLATION",
  "RANGE STREAMING",
];

const STATS = [
  { to: 8, suffix: "s", label: "Scene cadence" },
  { to: 16, suffix: "", label: "DB tables, zero Redis" },
  { to: 3, suffix: "", label: "Job stages" },
  { to: 100, suffix: "%", label: "Server-verified output" },
];

function HeroScene() {
  return (
    <TiltCard max={9} className="hidden lg:block">
      <div className="card card-hl relative p-6 [transform-style:preserve-3d]">
        <div className="flex items-center justify-between">
          <div>
            <div className="panel-tag">Project</div>
            <div className="mt-1 font-display text-xl text-foreground">
              The Boy Who Belonged to the Jungle
            </div>
          </div>
          <span className="chip chip-accent">
            <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-accent" />
            Completed
          </span>
        </div>
        <div className="mt-6 space-y-3">
          {[
            ["01", "The firefly", 100],
            ["02", "The hidden village", 100],
            ["03", "Kindness lights the way", 100],
            ["04", "Assembly + validation", 100],
          ].map(([number, title, progress], index) => (
            <motion.div
              key={String(number)}
              className="flex items-center gap-3 rounded-xl border border-foreground/10 bg-canvas/70 p-3"
              style={{ transform: `translateZ(${index * 24}px)` }}
              initial={{ opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.35 + index * 0.14, duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
            >
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-foreground/[0.06] font-mono text-[11px] font-semibold text-muted">
                {number}
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm text-foreground">{title}</div>
                <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-foreground/10">
                  <motion.div
                    className="h-full bg-accent"
                    initial={{ width: "0%" }}
                    animate={{ width: `${progress}%` }}
                    transition={{ delay: 0.6 + index * 0.14, duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
                  />
                </div>
              </div>
              <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-foreground">
                {index === 3 ? "Passed" : "Succeeded"}
              </span>
            </motion.div>
          ))}
        </div>
        <div className="mt-5 flex items-center justify-between text-xs text-muted">
          <span>Local execution · this computer</span>
          <span className="font-mono text-accent">100%</span>
        </div>
      </div>
    </TiltCard>
  );
}

function FloatingChips() {
  const mx = useMotionValue(0);
  const my = useMotionValue(0);
  const reduce = useReducedMotion();
  const tx = useSpring(useTransform(mx, [-0.5, 0.5], [-18, 18]), { stiffness: 60, damping: 20 });
  const ty = useSpring(useTransform(my, [-0.5, 0.5], [-12, 12]), { stiffness: 60, damping: 20 });
  const tx2 = useSpring(useTransform(mx, [-0.5, 0.5], [24, -24]), { stiffness: 50, damping: 22 });
  const ty2 = useSpring(useTransform(my, [-0.5, 0.5], [16, -16]), { stiffness: 50, damping: 22 });

  useEffect(() => {
    if (reduce) return;
    const onMove = (event: MouseEvent) => {
      mx.set(event.clientX / window.innerWidth - 0.5);
      my.set(event.clientY / window.innerHeight - 0.5);
    };
    window.addEventListener("mousemove", onMove);
    return () => window.removeEventListener("mousemove", onMove);
  }, [mx, my, reduce]);

  return (
    <div className="pointer-events-none absolute inset-0 hidden lg:block" aria-hidden>
      <motion.div style={{ x: tx, y: ty }} className="absolute right-[6%] top-[18%]">
        <span className="chip bg-accent text-accent-ink shadow-glow-sm">VISION CONTINUITY</span>
      </motion.div>
      <motion.div style={{ x: tx2, y: ty2 }} className="absolute bottom-[16%] left-[4%]">
        <span className="chip border-accent/40 bg-accent/10">FFMPEG ASSEMBLY</span>
      </motion.div>
      <motion.div style={{ x: tx, y: ty2 }} className="absolute left-[8%] top-[12%]">
        <span className="chip">8-SECOND SCENES</span>
      </motion.div>
    </div>
  );
}

function Hero() {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const y = useTransform(scrollYProgress, [0, 1], [0, 140]);
  const opacity = useTransform(scrollYProgress, [0, 0.8], [1, 0.15]);
  const scale = useTransform(scrollYProgress, [0, 1], [1, 0.94]);

  return (
    <section ref={ref} className="relative overflow-hidden">
      <FloatingChips />
      <motion.div style={{ y, opacity, scale }} className="relative mx-auto max-w-7xl px-4 pb-24 pt-14 sm:px-6 sm:pt-24">
        <div className="grid items-center gap-14 lg:grid-cols-[1.05fr_0.95fr]">
          <div>
            <Reveal>
              <span className="chip chip-accent">Multi-user AI video studio</span>
            </Reveal>
            <Reveal delay={0.08}>
              <h1 className="mt-6 font-display text-[2.6rem] leading-[1.05] text-foreground sm:text-6xl lg:text-7xl">
                From a script
                <br />
                to a finished film,
                <span className="relative ml-3 inline-block text-accent">
                  scene by scene.
                  <motion.span
                    aria-hidden
                    className="absolute -bottom-2 left-0 h-[3px] w-full bg-accent"
                    initial={{ scaleX: 0 }}
                    animate={{ scaleX: 1 }}
                    transition={{ delay: 0.9, duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
                  />
                </span>
              </h1>
            </Reveal>
            <Reveal delay={0.16}>
              <p className="mt-7 max-w-xl text-base leading-relaxed text-muted">
                Plan characters, approve the shot list, generate every scene with
                frame-true continuity, assemble the timeline and validate the
                result. Each account has isolated projects, storage, provider
                sessions and usage tracking.
              </p>
            </Reveal>
            <Reveal delay={0.24}>
              <div className="mt-9 flex flex-wrap items-center gap-3">
                <Link href="/register" className="btn-primary px-7 py-3.5 text-base">
                  Create your studio
                  <motion.span aria-hidden className="inline-block" whileHover={{ x: 4 }}>
                    →
                  </motion.span>
                </Link>
                <Link href="/login" className="btn-secondary px-7 py-3.5 text-base">
                  I already have an account
                </Link>
              </div>
            </Reveal>
            <Reveal delay={0.3}>
              <p className="mt-6 max-w-lg text-xs leading-relaxed text-muted">
                Development builds use a clearly labelled simulated provider that
                renders real MP4 clips. Real TAAFT automation stays disabled
                pending written provider authorization.
              </p>
            </Reveal>
          </div>
          <motion.div
            initial={{ opacity: 0, y: 40, rotateY: -8 }}
            animate={{ opacity: 1, y: 0, rotateY: 0 }}
            transition={{ duration: 0.9, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
          >
            <HeroScene />
          </motion.div>
        </div>
      </motion.div>
    </section>
  );
}

function MarqueeStrip() {
  return (
    <section className="border-y border-foreground/10 bg-structural/60">
      <Marquee items={MARQUEE_A} className="py-4" />
      <div className="h-px bg-foreground/[0.06]" />
      <Marquee items={MARQUEE_B} reverse className="py-4" />
    </section>
  );
}

function StructuralSection() {
  return (
    <section className="relative mx-auto max-w-7xl px-4 py-24 sm:px-6">
      <div className="grid gap-12 lg:grid-cols-[0.38fr_0.62fr]">
        <div className="lg:sticky lg:top-28 lg:h-fit">
          <Reveal>
            <div className="panel-tag">/ SYSTEM CAPABILITIES</div>
            <h2 className="mt-4 font-display text-4xl leading-tight text-foreground lg:text-5xl">
              Built like a machine, not a mockup.
            </h2>
            <p className="mt-5 max-w-sm text-sm leading-relaxed text-muted">
              Every stage of the studio is a real, verified component — from the
              planner to the final checksum. Nothing decorative, nothing fake.
            </p>
            <div className="mt-8 h-px w-24 bg-accent" />
          </Reveal>
        </div>
        <div className="space-y-4">
          {FEATURES.map((feature, index) => (
            <Reveal key={feature.number} delay={index * 0.05}>
              <article className="card group relative overflow-hidden p-7 transition-transform duration-300 hover:-translate-y-1">
                <span className="pointer-events-none absolute right-6 top-6 font-display text-5xl text-foreground/[0.06] transition-colors group-hover:text-accent/25">
                  {feature.number}
                </span>
                <div className="chip">{feature.tag}</div>
                <h3 className="mt-4 font-display text-2xl text-foreground">{feature.title}</h3>
                <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted">{feature.body}</p>
                <span className="pointer-events-none absolute inset-x-0 bottom-0 h-[2px] origin-left scale-x-0 bg-accent transition-transform duration-500 group-hover:scale-x-100" />
              </article>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

function PipelineSection() {
  return (
    <section className="relative overflow-hidden border-y border-foreground/10 bg-structural/50 py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <Reveal>
          <div className="panel-tag">/ THE PIPELINE</div>
          <h2 className="mt-4 max-w-2xl font-display text-4xl leading-tight text-foreground lg:text-5xl">
            One click. Three stages. A finished MP4 with a verified checksum.
          </h2>
        </Reveal>
        <Parallax distance={40} className="mt-16">
          <div className="relative [perspective:1400px]">
            {PIPELINE.map((stage, index) => (
              <Reveal key={stage.id} delay={index * 0.12}>
                <div
                  className="card card-hl relative mb-6 flex items-center gap-6 p-7 transition-transform duration-500 hover:[transform:perspective(1400px)_rotateX(2deg)]"
                  style={{ marginLeft: stage.x }}
                >
                  <span
                    className="absolute left-5 top-1/2 hidden h-10 w-10 -translate-y-1/2 place-items-center rounded-xl bg-accent font-mono text-[11px] font-black text-accent-ink shadow-glow-sm sm:grid"
                    style={{ transform: `translateY(-50%) ${stage.z}` }}
                  >
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <div className="pl-0 sm:pl-14">
                    <div className="font-mono text-xs font-bold uppercase tracking-[0.3em] text-accent">
                      {stage.id}
                    </div>
                    <div className="mt-2 max-w-xl text-sm leading-relaxed text-muted">{stage.body}</div>
                  </div>
                  <motion.span
                    aria-hidden
                    className="pointer-events-none absolute inset-y-0 right-0 w-24 bg-gradient-to-l from-accent/[0.06] to-transparent"
                    animate={{ opacity: [0.4, 1, 0.4] }}
                    transition={{ duration: 2.4, repeat: Infinity, delay: index * 0.5 }}
                  />
                </div>
              </Reveal>
            ))}
          </div>
        </Parallax>
      </div>
    </section>
  );
}

function StatsSection() {
  return (
    <section className="mx-auto max-w-7xl px-4 py-24 sm:px-6">
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {STATS.map((stat, index) => (
          <Reveal key={stat.label} delay={index * 0.07}>
            <div className="card relative p-7 text-center">
              <div className="font-display text-5xl text-foreground">
                <Counter to={stat.to} suffix={stat.suffix} />
              </div>
              <div className="mt-3 font-mono text-[10px] uppercase tracking-[0.2em] text-muted">
                {stat.label}
              </div>
              <span className="absolute inset-x-8 bottom-0 h-px bg-gradient-to-r from-transparent via-accent/60 to-transparent" />
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

function CtaSection() {
  return (
    <section className="relative overflow-hidden border-t border-foreground/10 py-28">
      <div className="pointer-events-none absolute inset-0" aria-hidden>
        <div className="absolute left-1/2 top-1/2 h-[520px] w-[820px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent/[0.07] blur-3xl" />
      </div>
      <div className="relative mx-auto max-w-3xl px-4 text-center sm:px-6">
        <Reveal>
          <div className="panel-tag justify-center">/ READY</div>
          <h2 className="mt-5 font-display text-4xl leading-tight text-foreground sm:text-6xl">
            Your next film is one script away.
          </h2>
          <p className="mx-auto mt-6 max-w-xl text-sm leading-relaxed text-muted">
            Register, paste the story, approve the shot list — the studio runs
            the rest autonomously, scene by connected scene.
          </p>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Link href="/register" className="btn-primary px-8 py-4 text-base">
              Start creating
            </Link>
            <Link href="/login" className="btn-secondary px-8 py-4 text-base">
              Sign in
            </Link>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

export default function LandingPage() {
  return (
    <div className="min-h-screen">
      <ScrollProgress />
      <header className="sticky top-0 z-50 border-b border-foreground/10 bg-canvas/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-4 sm:px-6">
          <Link href="/" className="flex items-center gap-2.5">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-accent text-lg font-black text-accent-ink shadow-glow-sm">
              S
            </span>
            <span className="font-display text-lg tracking-wide text-foreground">StoryForge AI</span>
          </Link>
          <div className="ml-auto flex items-center gap-2">
            <Link href="/login" className="btn-ghost">
              Sign in
            </Link>
            <Link href="/register" className="btn-primary">
              Start creating
            </Link>
          </div>
        </div>
      </header>

      <Hero />
      <MarqueeStrip />
      <StructuralSection />
      <PipelineSection />
      <StatsSection />
      <CtaSection />

      <footer className="border-t border-foreground/10">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-10 text-xs text-muted sm:px-6">
          <span className="flex items-center gap-2.5">
            <span className="grid h-6 w-6 place-items-center rounded-lg bg-accent text-[11px] font-black text-accent-ink">
              S
            </span>
            StoryForge AI · cloud-first with local fallback
          </span>
          <span>No paid services are activated by default.</span>
        </div>
      </footer>
    </div>
  );
}
