"use client";

import { useEffect, useState } from "react";

import { getHealth } from "@/services/api";

export type BackendStatus = "checking" | "online" | "offline";

export function useBackendHealth(): BackendStatus {
  const [status, setStatus] = useState<BackendStatus>("checking");

  useEffect(() => {
    const controller = new AbortController();
    getHealth({ signal: controller.signal, cache: "no-store" })
      .then((health) => setStatus(health.status === "ok" ? "online" : "offline"))
      .catch(() => {
        if (!controller.signal.aborted) setStatus("offline");
      });
    return () => controller.abort();
  }, []);

  return status;
}
