import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
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
