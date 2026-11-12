"use client";

import { useEffect, useState } from "react";
import { meta } from "@/lib/api";
import type { PublicConfig } from "@/lib/types";

export function ModeBadge() {
  const [config, setConfig] = useState<PublicConfig | null>(null);

  useEffect(() => {
    let active = true;
    meta
      .config()
      .then((value) => active && setConfig(value))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  if (!config) {
    return <span className="chip bg-ink-700 text-slate-400">Mode…</span>;
  }
  const local = config.execution_mode === "local";
  return (
    <span
      className={`chip ${local ? "bg-mint-500/15 text-mint-400" : "bg-sky-500/15 text-sky-300"}`}
      title={
        local
          ? "Jobs are executed on a connected local worker. Keep that computer awake."
          : "Jobs are executed by the cloud worker service."
      }
    >
      <span className={`h-1.5 w-1.5 rounded-full ${local ? "bg-mint-400" : "bg-sky-400"}`} />
      {local ? "Local execution" : "Cloud execution"}
    </span>
  );
}
