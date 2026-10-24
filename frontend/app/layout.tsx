import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";

import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Ripple",
  description: "Stop the scam, then follow the money: scam interception and golden-hour tracing for Indian payments",
};

const nav = [
  ["/", "Command centre"],
  ["/trace", "Report a scam"],
  ["/eval", "Evaluation"],
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en-IN" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full bg-slate-950 text-slate-100">
        <header className="sticky top-0 z-40 border-b border-slate-800 bg-slate-950/90 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3">
            <Link href="/" className="flex items-baseline gap-2">
              <span className="text-lg font-bold tracking-tight">Ripple</span>
              <span className="hidden text-xs text-slate-500 sm:inline">stop the scam, then follow the money</span>
            </Link>
            <nav className="flex gap-1 text-sm">
              {nav.map(([href, label]) => (
                <Link key={href} href={href} className="rounded-md px-3 py-1.5 text-slate-300 hover:bg-slate-800 hover:text-white">
                  {label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
        <footer className="mx-auto max-w-7xl px-4 pb-8 text-xs text-slate-600">
          Risk indicators and drafts for a human officer to review. Ripple does not decide that anyone committed fraud,
          does not file reports and uses only synthetic and public data.
        </footer>
      </body>
    </html>
  );
}
