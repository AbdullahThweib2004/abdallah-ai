import type { HealthResponse } from "./types";

// Browser-side base URL. Server components use services/content.ts instead.
export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(
  /\/+$/,
  "",
);

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...init?.headers },
    });
  } catch (error) {
    throw new ApiError(error instanceof Error ? error.message : "Network error", null);
  }

  if (!response.ok) {
    throw new ApiError(`Request to ${path} failed`, response.status);
  }
  return (await response.json()) as T;
}

export function getHealth(init?: RequestInit): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/api/v1/health", init);
}
