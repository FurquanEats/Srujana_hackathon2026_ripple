import localFont from "next/font/local";

/** Silkscreen by Jason Kottke, SIL Open Font License 1.1 (see ./fonts/OFL.txt). Latin subset; it has no rupee sign. */
export const silkscreen = localFont({
  src: [
    { path: "./fonts/Silkscreen-Regular.woff2", weight: "400", style: "normal" },
    { path: "./fonts/Silkscreen-Bold.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-silkscreen",
  display: "swap",
});
