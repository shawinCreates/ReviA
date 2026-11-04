import { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/config";

const base = SITE_URL ? SITE_URL.replace(/\/$/, "") : "";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/"],
        disallow: ["/chat", "/pipeline", "/login", "/auth", "/api"],
      },
    ],
    ...(base ? { sitemap: `${base}/sitemap.xml` } : {}),
  };
}
