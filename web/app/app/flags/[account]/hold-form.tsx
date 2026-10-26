"use client";

import { useState } from "react";

type Flag = { key: string; title: string; reason: string; amount: number; label: string };

const DAY = 86_400_000;
const longDate = (d: Date) =>
  new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(d);

/** The hold form, with the customer notice previewed exactly as it will be sent. */
export function HoldForm({
  action,
  account,
  holder,
  bank,
  flags,
  today: todayIso,
}: {
  action: (form: FormData) => Promise<void>;
  account: string;
  holder: string;
  bank: string;
  flags: Flag[];
  today: string;
}) {
  const [chosen, setChosen] = useState(() => new Set(flags.map((f) => f.key)));
  const [contact, setContact] = useState("SMS and email to the registered mobile number and email");
  const [whole, setWhole] = useState(false);
  const picked = flags.filter((f) => chosen.has(f.key));
  const largest = picked.reduce((m, f) => (f.amount > m.amount ? f : m), picked[0] ?? flags[0]!);
  const today = new Date(todayIso);
  const toggle = (key: string) =>
    setChosen((s) => {
      const next = new Set(s);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return (
    <form action={action} className="grid gap-4">
      <input type="hidden" name="account" value={account} />
      <fieldset className="grid gap-2">
        <legend className="label">Flags to hold</legend>
        {flags.map((f) => (
          <label key={f.key} className="flex gap-2 text-[13px]">
            <input
              type="checkbox"
              name="flag"
              value={f.key}
              checked={chosen.has(f.key)}
              onChange={() => toggle(f.key)}
              className="mt-0.5 accent-[var(--color-accent)]"
            />
            <span>
              {f.title} <span className="text-faint font-mono">{f.label}</span>
            </span>
          </label>
        ))}
      </fieldset>
      <div>
        <label htmlFor="contact" className="label">
          How the customer is told
        </label>
        <input
          id="contact"
          name="contact"
          value={contact}
          onChange={(e) => setContact(e.target.value)}
          required
          minLength={5}
          maxLength={200}
          className="field"
        />
      </div>
      <label className="flex gap-2 text-[13px]">
        <input
          type="checkbox"
          name="whole"
          checked={whole}
          onChange={(e) => setWhole(e.target.checked)}
          className="mt-0.5 accent-[var(--color-accent)]"
        />
        Hold the whole account instead of the flagged amount
      </label>
      {whole && (
        <div>
          <label htmlFor="whole_reason" className="label">
            Why the whole account (at least 30 characters)
          </label>
          <textarea
            id="whole_reason"
            name="whole_reason"
            rows={3}
            minLength={30}
            maxLength={2000}
            required
            className="field"
          />
        </div>
      )}
      <div>
        <p className="label">Customer notice, as it will be sent</p>
        <pre className="bg-panel border-line max-h-72 overflow-y-auto border p-3 font-sans text-[12.5px] leading-relaxed whitespace-pre-wrap">
          {`Dear ${holder},\n\n${bank} has placed a temporary hold on debits of ${whole ? "your account" : (largest?.label ?? "")} from your account ending ${account.slice(-4)}, from ${longDate(today)}. The bank has done this under the Reserve Bank of India's directions on suspected money mule accounts, because of these transactions: ${picked.map((f) => f.reason).join(" ")}\n\nYou can still receive money, and you can use any balance that is not on hold.\n\nTo have the hold removed, send the bank an explanation of these transactions, with any documents that support it, such as invoices, agreements or salary slips, by ${longDate(new Date(today.getTime() + 20 * DAY))}. The bank will decide within 10 days of receiving your explanation.\n\nContact: ${contact}`}
        </pre>
      </div>
      <button className="button button-solid justify-self-start" disabled={picked.length === 0}>
        Place hold and send notice
      </button>
    </form>
  );
}
