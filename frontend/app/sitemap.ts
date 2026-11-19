import type { MetadataRoute } from "next";

import { siteUrl } from "@/lib/site/url";

export default function sitemap(): MetadataRoute.Sitemap {
  const base = siteUrl();
  return ["", "/projects", "/about"].map((path) => ({ url: `${base}${path}` }));
}
