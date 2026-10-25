import type { FlowNode } from "@/components/workspace/flow-graph";
import { accountText, EXIT, RAIL } from "@/lib/accounts";
import type { AccountLine, AccountView, NoticeDetail } from "@/lib/gateway/types";

const DAY = 86_400_000;
const MAX_ROWS = 6;

function party(line: AccountLine): string {
  if (line.exit) return `${EXIT[line.exit.mode] ?? line.exit.mode} ${line.exit.identifier}`;
  return accountText(line.counterparty);
}

/** Group lines by counterparty, largest first, folding the tail into one "others" row. */
function grouped(lines: AccountLine[], kind: (l: AccountLine) => FlowNode["kind"]): FlowNode[] {
  const by = new Map<string, FlowNode & { count: number }>();
  for (const l of lines) {
    const key = party(l);
    const node = by.get(key) ?? { label: key, amount: 0, kind: kind(l), count: 0 };
    node.amount += l.amount;
    node.count += 1;
    by.set(key, node);
  }
  const all = [...by.values()].sort((a, b) => b.amount - a.amount);
  const head = all.slice(0, MAX_ROWS - 1);
  const tail = all.slice(MAX_ROWS - 1);
  const rows: FlowNode[] = head.map((n) => ({ ...n, sub: `${n.count} payment${n.count === 1 ? "" : "s"}` }));
  if (tail.length)
    rows.push({
      label: `${tail.length} others`,
      amount: tail.reduce((s, n) => s + n.amount, 0),
      kind: "plain",
    });
  return rows;
}

/** A notice: the victim's credit in; onward hops, cash-outs and the lien out. */
export function noticeFlow(n: NoticeDetail) {
  const s = n.summary;
  const credit = n.statement.find((l) => l.direction === "credit" && (l.victim_money[s.ack_number] ?? 0) > 0);
  const inflows: FlowNode[] = [
    {
      label: credit ? accountText(credit.counterparty) : "The payment named in the notice",
      sub: `${RAIL[n.credit.rail]} ${n.credit.reference}`,
      amount: s.traced_in,
      kind: "victim",
    },
  ];
  const outflows: FlowNode[] = [
    ...n.onward.map((h) => ({
      label: accountText(h.to),
      sub: `${RAIL[h.payment.rail]} onward`,
      amount: h.traced_amount,
      kind: "victim" as const,
    })),
    ...n.exits.map((e) => ({
      label: `${EXIT[e.mode] ?? e.mode} ${e.identifier}`,
      sub: e.location ?? "cash out",
      amount: e.traced_amount,
      kind: "exit" as const,
    })),
  ];
  if (s.held > 0)
    outflows.unshift({ label: "Still here, under lien", sub: "held", amount: s.held, kind: "held" });
  return { inflows, outflows: outflows.filter((o) => o.amount > 0) };
}

/** An account's last 30 days: who paid in, and where the money went. */
export function accountFlow(a: AccountView, now: string) {
  const since = new Date(now).getTime() - 30 * DAY;
  const recent = a.statement.filter((l) => new Date(l.at).getTime() >= since);
  const lines = recent.length ? recent : a.statement;
  return {
    inflows: grouped(
      lines.filter((l) => l.direction === "credit"),
      () => "plain",
    ),
    outflows: grouped(
      lines.filter((l) => l.direction === "debit"),
      (l) => (l.exit ? "exit" : "plain"),
    ),
    windowed: recent.length > 0,
  };
}

/** Flagged or held credits in, and what left the account in the two days after the first of them. */
export function creditsFlow(a: AccountView, creditTxns: string[]) {
  const credits = a.statement.filter((l) => creditTxns.includes(l.txn_id));
  const first = Math.min(...credits.map((c) => new Date(c.at).getTime()));
  const after = a.statement.filter(
    (l) =>
      l.direction === "debit" &&
      new Date(l.at).getTime() >= first &&
      new Date(l.at).getTime() <= first + 2 * DAY,
  );
  return {
    inflows: credits.map((c) => ({
      label: party(c),
      sub: `${RAIL[c.rail]} ${c.reference}`,
      amount: c.amount,
      kind: "victim" as const,
    })),
    outflows: grouped(after, (l) => (l.exit ? "exit" : "plain")),
  };
}
