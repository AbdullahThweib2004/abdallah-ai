"use client";

import { type BackendStatus, useBackendHealth } from "@/hooks/useBackendHealth";

const STYLES: Record<BackendStatus, { label: string; badge: string; dot: string }> = {
  checking: {
    label: "Checking backend…",
    badge: "border-zinc-300 bg-zinc-100 text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300",
    dot: "bg-zinc-400 animate-pulse",
  },
  online: {
    label: "Backend online",
    badge: "border-green-300 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-950 dark:text-green-300",
    dot: "bg-green-500",
  },
  offline: {
    label: "Backend offline",
    badge: "border-red-300 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-300",
    dot: "bg-red-500",
  },
};

export function BackendStatusBadge() {
  const status = useBackendHealth();
  const style = STYLES[status];

  return (
    <span
      role="status"
      aria-live="polite"
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm font-medium ${style.badge}`}
    >
      <span aria-hidden="true" className={`size-2 rounded-full ${style.dot}`} />
      {style.label}
    </span>
  );
}
