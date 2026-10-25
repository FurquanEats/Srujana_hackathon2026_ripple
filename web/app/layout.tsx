import type { Metadata, Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";

import { silkscreen } from "./fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Ripple: cross-bank fraud tracing", template: "%s | Ripple" },
  description:
    "Ripple answers cyber-fraud notices for banks in seconds, tracing a victim's money across institutions and placing liens on the traced amount only.",
};

export const viewport: Viewport = {
  themeColor: "#121212",
  colorScheme: "dark",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en-IN" className={`${GeistSans.variable} ${GeistMono.variable} ${silkscreen.variable}`}>
      <body>{children}</body>
    </html>
  );
}
