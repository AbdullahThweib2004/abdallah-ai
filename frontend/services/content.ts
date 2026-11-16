import "server-only";

import { cacheLife, cacheTag } from "next/cache";
import { connection } from "next/server";

import type { ContactResponse, Profile, ProjectDetail, ProjectSummary } from "./types";

// Server-side base URL (may be an internal address); falls back to the public one.
const API_BASE_URL = (
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000"
).replace(/\/+$/, "");

const TIMEOUT_MS = 5000;

/**
 * Cached GET against the backend. Returns `null` for a 404 (a real answer, safe to cache).
 * Any other failure throws, so outages are never cached; callers turn them into
 * "content unavailable".
 */
async function getJson<T>(path: string): Promise<T | null> {
  "use cache";
  cacheLife("minutes");
  cacheTag("content");

  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Accept: "application/json" },
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`GET ${path} failed with ${response.status}`);
  return (await response.json()) as T;
}

async function getOrNull<T>(path: string): Promise<T | null> {
  // Content is fetched at request time only, so `next build` never depends on the backend.
  await connection();
  try {
    return await getJson<T>(path);
  } catch {
    return null;
  }
}

export function getProfile(): Promise<Profile | null> {
  return getOrNull<Profile>("/api/v1/profile");
}

export function getProjects(): Promise<ProjectSummary[] | null> {
  return getOrNull<ProjectSummary[]>("/api/v1/projects");
}

export function getContact(): Promise<ContactResponse | null> {
  return getOrNull<ContactResponse>("/api/v1/contact");
}

export type ProjectResult =
  | { status: "ok"; project: ProjectDetail }
  | { status: "not_found" }
  | { status: "unavailable" };

export async function getProject(id: string): Promise<ProjectResult> {
  await connection();
  try {
    const project = await getJson<ProjectDetail>(`/api/v1/projects/${encodeURIComponent(id)}`);
    return project ? { status: "ok", project } : { status: "not_found" };
  } catch {
    return { status: "unavailable" };
  }
}
