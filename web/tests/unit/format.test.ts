import { describe, expect, it } from "vitest";

import { formatInr, formatIst } from "@/lib/format";

describe("formatInr", () => {
  it("groups digits the Indian way", () => {
    expect(formatInr(80_000_000)).toBe("₹8,00,000");
    expect(formatInr(2_500_000_000)).toBe("₹2,50,00,000");
    expect(formatInr(99_900)).toBe("₹999");
  });
  it("shows paise only when there are any, and signs negatives", () => {
    expect(formatInr(12_345)).toBe("₹123.45");
    expect(formatInr(-5_000_000)).toBe("-₹50,000");
  });
  it("writes Rs for the pixel face, which has no rupee sign", () => {
    expect(formatInr(80_000_000, "Rs")).toBe("Rs 8,00,000");
  });
});

describe("formatIst", () => {
  it("shows UTC times in IST with the date", () => {
    expect(formatIst("2026-10-25T18:30:00Z")).toBe("26 Oct 2026, 00:00 IST");
  });
});
