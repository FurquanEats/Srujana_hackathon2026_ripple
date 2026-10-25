import localFont from "next/font/local";

/**
 * Pixel Operator by Jayvee Enaguas, dedicated to the public domain under CC0 1.0 (see ./fonts/PixelOperator-LICENSE.txt).
 * Downloaded from its DaFont page and converted to WOFF2 unchanged. It has no rupee sign, so pixel figures use "Rs".
 */
export const pixelOperator = localFont({
  src: [
    { path: "./fonts/PixelOperator.woff2", weight: "400", style: "normal" },
    { path: "./fonts/PixelOperator-Bold.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-pixel-operator",
  display: "swap",
});
