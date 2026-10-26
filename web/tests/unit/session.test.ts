import { describe, expect, it } from "vitest";

import { encodeSession, parseSession } from "@/lib/session";

describe("the demo session cookie", () => {
  it("round-trips every role's session", () => {
    for (const s of [
      { role: "nodal_officer", member: "bank-b" },
      { role: "police_officer", member: null },
      { role: "account_holder", member: "bank-d", subject: "7846077002" },
      { role: "victim", member: null, subject: "37456153881292" },
    ] as const)
      expect(parseSession(encodeSession(s))).toEqual(s);
  });
  it("refuses what the sign-in page would never set", () => {
    const bad = (v: unknown) => parseSession(Buffer.from(JSON.stringify(v)).toString("base64url"));
    expect(bad({ role: "nodal_officer", member: "cfcfrms" })).toBeNull();
    expect(bad({ role: "admin", member: null })).toBeNull();
    expect(bad({ role: "victim", subject: "12345" })).toBeNull();
    expect(bad({ role: "account_holder", member: "bank-d", subject: "../etc" })).toBeNull();
    expect(parseSession("%%%")).toBeNull();
    expect(parseSession(undefined)).toBeNull();
  });
});
