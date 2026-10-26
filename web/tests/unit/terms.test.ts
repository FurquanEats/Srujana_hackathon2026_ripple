import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { TERMS } from "@/lib/terms";

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    return statSync(full).isDirectory() ? files(full) : full.endsWith(".tsx") ? [full] : [];
  });
}

describe("terms", () => {
  it("explains every term in a full sentence", () => {
    for (const term of Object.values(TERMS)) {
      expect(term.label.length).toBeGreaterThan(1);
      expect(term.text).toMatch(/^[A-Z].+\.$/);
    }
  });
  it("has an explanation for every <Term name=...> the site uses", () => {
    const root = path.resolve(__dirname, "../..");
    const used = new Set(
      [...files(path.join(root, "app")), ...files(path.join(root, "components"))].flatMap((f) =>
        [...readFileSync(f, "utf8").matchAll(/<Term name="(\w+)"/g)].map((m) => m[1]),
      ),
    );
    for (const name of used) expect(Object.keys(TERMS)).toContain(name);
  });
});
