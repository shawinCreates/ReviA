import type { Metadata } from "next";
import { Orbitron, Geist, JetBrains_Mono } from "next/font/google";

import { APP_NAME, APP_TAGLINE, SITE_URL } from "@/lib/config";

import "./globals.css";

import { AuthWatcher } from "@/components/auth-watcher";

const orbitron = Orbitron({
  subsets: ["latin"],
  variable: "--font-orbitron",
  display: "swap",
});

const geist = Geist({
  subsets: ["latin"],
  variable: "--font-geist",
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap",
});

const siteUrl = SITE_URL ? new URL(SITE_URL) : undefined;

const PAGE_DESCRIPTION =
  "Upload your lecture slides, papers and notes. Ask a question and get an answer built only from what you uploaded, with the page cited for every claim.";

export const metadata: Metadata = {
  metadataBase: siteUrl,
  title: {
    default: `${APP_NAME}: ${APP_TAGLINE}`,
    template: `%s | ${APP_NAME}`,
  },
  description: PAGE_DESCRIPTION,
  robots: { index: true, follow: true },
  openGraph: {
    siteName: APP_NAME,
    title: `${APP_NAME}: ${APP_TAGLINE}`,
    description: PAGE_DESCRIPTION,
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: `${APP_NAME}: ${APP_TAGLINE}`,
    description: PAGE_DESCRIPTION,
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      data-scroll-behavior="smooth"
      className={`${orbitron.variable} ${geist.variable} ${jetbrains.variable}`}
    >
      <head>
        <noscript>
          <style>{`.reveal{opacity:1;transform:none}`}</style>
        </noscript>
      </head>
      <body>
        <a
          href="#main"
          className="sr-only fixed top-6 left-6 z-50 px-4 py-2 bg-ink text-surface rounded-none focus:outline-none"
        >
          Skip to content
        </a>
        <AuthWatcher />
        {children}
      </body>
    </html>
  );
}
