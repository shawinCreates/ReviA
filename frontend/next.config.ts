import type { NextConfig } from "next";

const isProd = process.env.NODE_ENV === "production";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  ...(isProd
    ? {
        async headers() {
          const origins = new Set<string>(["self"]);

          const addOrigin = (value: string | undefined) => {
            if (!value) return;
            try {
              origins.add(new URL(value.replace(/\/$/, "")).origin);
            } catch {
              // Ignore malformed origins; the app cannot reach a malformed API anyway.
            }
          };

          addOrigin(process.env.NEXT_PUBLIC_API_BASE_URL);
          addOrigin(process.env.NEXT_PUBLIC_SUPABASE_URL);

          const connectSrc = [...origins].join(" ");

          return [
            {
              source: "/(.*)",
              headers: [
                {
                  key: "X-Content-Type-Options",
                  value: "nosniff",
                },
                {
                  key: "X-Frame-Options",
                  value: "DENY",
                },
                {
                  key: "Referrer-Policy",
                  value: "strict-origin-when-cross-origin",
                },
                {
                  key: "Strict-Transport-Security",
                  value: "max-age=31536000",
                },
                {
                  key: "Content-Security-Policy",
                  value: [
                    "default-src 'self'",
                    "script-src 'self' 'unsafe-inline'",
                    "style-src 'self' 'unsafe-inline'",
                    "img-src 'self' data: https:",
                    "font-src 'self'",
                    `connect-src ${connectSrc}`,
                    "base-uri 'self'",
                    "form-action 'self'",
                    "frame-ancestors 'none'",
                  ].join("; "),
                },
              ],
            },
          ];
        },
      }
    : {}),
};

export default nextConfig;
