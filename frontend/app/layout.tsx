import type { Metadata, Viewport } from "next";

// Self-hosted so the app builds and renders on networks without Google Fonts access (bank intranets, CI sandboxes).
import "@fontsource-variable/ibm-plex-sans";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";

import { AppShell } from "@/components/AppShell";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Ripple", template: "%s · Ripple" },
  description: "Stop the scam. Follow the money. Scam interception and golden-hour tracing for Indian banks.",
};

export const viewport: Viewport = {
  themeColor: "#f6f5f1",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en-IN" className="h-full antialiased">
      <body className="min-h-full bg-canvas text-ink">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
