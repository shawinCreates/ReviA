import type { Metadata } from "next";
import { Orbitron, Geist, JetBrains_Mono } from "next/font/google";

import { APP_NAME, APP_TAGLINE } from "@/lib/config";

import "./globals.css";

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

export const metadata: Metadata = {
  title: {
    default: `${APP_NAME}: ${APP_TAGLINE}`,
    template: `%s | ${APP_NAME}`,
  },
  description:
    "Upload your lecture slides, papers and notes. Ask a question and get an answer built only from what you uploaded, with the page cited for every claim.",
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
      <body>{children}</body>
    </html>
  );
}
