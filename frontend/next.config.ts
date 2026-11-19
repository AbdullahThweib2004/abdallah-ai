import type { NextConfig } from "next";

// Content Security Policy (production builds; `next dev` needs eval for fast refresh).
// Everything is same-origin: the API (/api/v1, incl. the streamed ElevenLabs audio, which our
// backend proxies) and the self-hosted fonts. `blob:` media = streamed speech (MediaSource).
// WebGL (the robot) needs no CSP source. Next.js inlines its bootstrap scripts, hence
// 'unsafe-inline' for scripts (nonces would force every page to render dynamically).
// A separate API origin (local `next build && next start` against :8000) is allowed too.
const apiOrigin = (() => {
  try {
    return new URL(process.env.NEXT_PUBLIC_API_BASE_URL ?? "").origin;
  } catch {
    return "";
  }
})();

const csp = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self'",
  `connect-src 'self'${apiOrigin ? ` ${apiOrigin}` : ""}`,
  `media-src 'self' blob:${apiOrigin ? ` ${apiOrigin}` : ""}`,
  "worker-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
  // Not when testing a production build against a plain-http local API.
  ...(apiOrigin.startsWith("http:") ? [] : ["upgrade-insecure-requests"]),
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // The microphone is used by this site only; nothing else is requested.
  { key: "Permissions-Policy", value: "microphone=(self), camera=(), geolocation=(), payment=(), usb=()" },
];

const nextConfig: NextConfig = {
  poweredByHeader: false,
  async headers() {
    if (process.env.NODE_ENV !== "production") return [];
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  cacheComponents: true,
  partialPrefetching: true,
  // Dev-only pages (/dev/avatar) are real 404s in production. The page also calls notFound(),
  // but under the dynamic root layout that would stream with status 200.
  async rewrites() {
    if (process.env.NODE_ENV !== "production") return [];
    return { beforeFiles: [{ source: "/dev/:path*", destination: "/_dev-only-not-found" }], afterFiles: [], fallback: [] };
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
