"use client";

import { type BackendStatus, useBackendHealth } from "@/hooks/useBackendHealth";

const DOT: Record<BackendStatus, string> = {
  checking: "bg-mist-400 animate-pulse motion-reduce:animate-none",
  online: "bg-ok",
  offline: "bg-red-400",
};

export function BackendStatusBadge({ labels }: { labels: Record<BackendStatus, string> }) {
  const status = useBackendHealth();

  return (
    <span role="status" aria-live="polite" className="inline-flex items-center gap-2 text-xs text-mist-400">
      <span aria-hidden="true" className={`size-2 rounded-full ${DOT[status]}`} />
      {labels[status]}
    </span>
  );
}
