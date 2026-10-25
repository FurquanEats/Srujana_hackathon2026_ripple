import { describe, expect, it } from "vitest";

import {
  apply,
  DemoConflict,
  encodeChanges,
  parseChanges,
  workingDaysAfter,
  type Change,
} from "@/lib/gateway/demo-store";
import bankD from "@/lib/gateway/fixtures/bank.bank-d.json";
import type { Hold, MuleCase } from "@/lib/gateway/types";

const cases = bankD["/v1/mule-cases"] as unknown as MuleCase[];
const holds = bankD["/v1/holds"] as unknown as Hold[];
const open = cases.find((c) => !c.active_hold_id && c.flags.some((f) => f.status === "open"))!;
const AT = "2026-10-26T00:00:00.000Z";

function hold(extra: Partial<Extract<Change, { k: "hold" }>> = {}): Change {
  return {
    k: "hold",
    m: "bank-d",
    a: open.account_number,
    keys: open.flags.map((f) => f.key),
    c: "Fraud Risk desk",
    w: false,
    wr: null,
    id: "H0000000000000001",
    at: AT,
    ...extra,
  };
}

function step(s: Extract<Change, { k: "step" }>["s"], b: Record<string, string>, at = AT): Change {
  return { k: "step", m: "bank-d", id: "H0000000000000001", s, b, at };
}

describe("the demo store applies a visitor's changes with the node's rules", () => {
  it("places a hold with the 20, 30 and 60-day deadlines and a notice", () => {
    const { holds: after, cases: flagged } = apply("bank-d", "Sangam Bank", cases, holds, [hold()]);
    const placed = after.find((h) => h.hold_id === "H0000000000000001")!;
    expect(placed.status).toBe("awaiting_explanation");
    expect(placed.customer_notice).toContain(`Dear ${open.holder_name}`);
    const due = Object.fromEntries(placed.deadlines.map((d) => [d.name, d.due.slice(0, 10)]));
    expect(due["Customer explanation"]).toBe("2026-11-15");
    expect(due["Bank decision"]).toBe("2026-11-25");
    expect(due["Maximum duration"]).toBe("2026-12-25");
    expect(flagged.find((c) => c.account_number === open.account_number)?.active_hold_id).toBe(
      "H0000000000000001",
    );
  });

  it("refuses to report before the customer's 20 days unless they explained", () => {
    expect(() =>
      apply("bank-d", "Sangam Bank", cases, holds, [
        hold(),
        step("decision", { decision: "report", reason: "x" }),
      ]),
    ).toThrow(DemoConflict);
    const { holds: after } = apply("bank-d", "Sangam Bank", cases, holds, [
      hold(),
      step("explanation", { summary: "No documents" }),
      step("decision", { decision: "report", reason: "No fit" }),
      step("police-instruction", { instruction: "continue", authority: "Cyber PS" }),
    ]);
    expect(after.find((h) => h.hold_id === "H0000000000000001")?.status).toBe("held_on_police_instruction");
  });

  it("drafts an STR due 7 working days after a mule is confirmed", () => {
    expect(workingDaysAfter("2026-10-23T10:00:00Z", 7).slice(0, 10)).toBe("2026-11-03"); // a Friday
    const { holds: after } = apply("bank-d", "Sangam Bank", cases, holds, [
      hold(),
      step("confirm-mule", { grounds: "Notice" }),
    ]);
    expect(after.find((h) => h.hold_id === "H0000000000000001")?.str_due?.slice(0, 10)).toBe("2026-11-04"); // Monday 26 Oct plus 7 working days
  });

  it("ignores another bank's changes and malformed cookie entries", () => {
    const other = apply("bank-d", "Sangam Bank", cases, holds, [{ ...hold(), m: "bank-a" }]);
    expect(other.holds).toHaveLength(holds.length);
    const encoded = Buffer.from(JSON.stringify([{ k: "hold" }, { nonsense: true }, hold()])).toString(
      "base64url",
    );
    expect(parseChanges(encoded)).toHaveLength(1);
    expect(parseChanges(encodeChanges([hold()]))).toEqual([hold()]);
    expect(parseChanges("not base64 json")).toEqual([]);
  });
});
