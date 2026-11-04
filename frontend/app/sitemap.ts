import { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/config";

const base = SITE_URL ? SITE_URL.replace(/\/$/, "") : "";

export default function sitemap(): MetadataRoute.Sitemap {
  const entries: MetadataRoute.Sitemap = [];

  if (base) {
    entries.push({
      url: `${base}/`,
      lastModified: new Date(),
      changeFrequency: "monthly",
      priority: 1,
    });
  }

  return entries;
}
