"use client";

import { useState } from "react";

type RoleOption = { role: string; label: string; duty: string; pick: "bank" | "holder" | "complaint" | null };
type Institution = { id: string; name: string };
type Choice = { value: string; label: string };

/** The formal selector: a role, then the institution, account or complaint it signs in as. */
export function RolePicker({
  roles,
  institutions,
  holders,
  complaints,
}: {
  roles: readonly RoleOption[];
  institutions: readonly Institution[];
  holders: Choice[];
  complaints: Choice[];
}) {
  const [role, setRole] = useState(roles[0]?.role ?? "");
  const chosen = roles.find((r) => r.role === role);
  return (
    <>
      <fieldset>
        <legend className="label">Who are you?</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {roles.map((r) => (
            <label
              key={r.role}
              className={`flex cursor-pointer gap-3 border p-3 text-sm transition-colors hover:border-[var(--fg)] ${role === r.role ? "border-[var(--fg)] bg-[var(--hover)]" : "border-line"}`}
            >
              <input
                type="radio"
                name="role"
                value={r.role}
                checked={role === r.role}
                onChange={() => setRole(r.role)}
                className="mt-1 accent-[var(--color-accent)]"
              />
              <span>
                <span className="block font-normal">{r.label}</span>
                <span className="text-muted block text-[12.5px] leading-snug">{r.duty}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      {chosen?.pick === "bank" && (
        <div className="mt-5">
          <label htmlFor="member" className="label">
            Institution
          </label>
          <select id="member" name="member" className="field" defaultValue="bank-b">
            {institutions.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name}
              </option>
            ))}
          </select>
        </div>
      )}
      {chosen?.pick === "holder" && (
        <div className="mt-5">
          <label htmlFor="holder" className="label">
            Whose account
          </label>
          <select id="holder" name="holder" className="field">
            {holders.map((h) => (
              <option key={h.value} value={h.value}>
                {h.label}
              </option>
            ))}
          </select>
        </div>
      )}
      {chosen?.pick === "complaint" && (
        <div className="mt-5">
          <label htmlFor="complaint" className="label">
            Your complaint
          </label>
          <select id="complaint" name="complaint" className="field">
            {complaints.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </div>
      )}
    </>
  );
}
