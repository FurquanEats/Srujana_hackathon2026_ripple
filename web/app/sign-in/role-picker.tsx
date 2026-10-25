"use client";

import { useState } from "react";

type RoleOption = { role: string; label: string; duty: string; bank: boolean };
type Institution = { id: string; name: string };

/** The formal selector: a role, and the institution when the role belongs to one. */
export function RolePicker({
  roles,
  institutions,
}: {
  roles: readonly RoleOption[];
  institutions: readonly Institution[];
}) {
  const [role, setRole] = useState(roles[0]?.role ?? "");
  const chosen = roles.find((r) => r.role === role);
  return (
    <>
      <fieldset>
        <legend className="label">Role</legend>
        <div className="grid gap-2">
          {roles.map((r) => (
            <label
              key={r.role}
              className={`flex cursor-pointer gap-3 border p-3 text-sm ${role === r.role ? "border-[var(--fg)]" : "border-line"}`}
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
                <span className="text-muted block text-[13px]">{r.duty}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      {chosen?.bank && (
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
    </>
  );
}
